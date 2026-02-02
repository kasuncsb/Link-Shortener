from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import cast, Optional
from datetime import datetime

from .database import get_db
from .models import Link, ApiKey
from .schemas import (
    ShortenRequest,
    ShortenResponse,
    LinkStatsResponse,
    LinkPreviewResponse,
    ErrorResponse,
    PasswordUnlockRequest,
    PasswordUnlockResponse,
    BulkShortenRequest,
    BulkShortenResponse,
    BulkShortenResultItem,
    BulkDeleteRequest,
    BulkDeleteResponse
)
from .services import LinkService
from .redis_client import RedisService
from .utils import format_short_url, is_reserved_code
from .auth import get_optional_api_key
from .captcha import verify_turnstile, is_turnstile_enabled
from .logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def get_client_ip(request: Request) -> str:
    """Extract client IP, considering Cloudflare headers."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    return request.client.host if request.client else "unknown"


@router.post(
    "/shorten",
    response_model=ShortenResponse,
    responses={
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse}
    }
)
async def create_short_link(
    request: Request,
    data: ShortenRequest,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_optional_api_key)
):
    """Create a new shortened link."""
    client_ip = get_client_ip(request)
    
    # Check rate limit - use API key's rate limit if authenticated
    if api_key:
        rate_limit = api_key.rate_limit
        logger.debug(f"Authenticated request from API key: {api_key.name}")
    else:
        rate_limit = None  # Use default rate limit
        
        # Verify CAPTCHA for anonymous requests if enabled
        if is_turnstile_enabled():
            # Get CAPTCHA token from request body or header
            captcha_token = getattr(data, 'cf_turnstile_response', None)
            if not captcha_token:
                # Also check in extra fields
                captcha_token = getattr(data, '__pydantic_extra__', {}).get('cf_turnstile_response')
            
            if not captcha_token:
                raise HTTPException(
                    status_code=400,
                    detail="CAPTCHA verification required"
                )
            
            is_valid = await verify_turnstile(captcha_token, client_ip)
            if not is_valid:
                logger.warning(f"CAPTCHA verification failed for {client_ip}")
                raise HTTPException(
                    status_code=400,
                    detail="CAPTCHA verification failed. Please try again."
                )
    
    allowed, remaining = RedisService.check_rate_limit(client_ip, rate_limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"X-RateLimit-Remaining": "0"}
        )
    
    link, error = LinkService.create_link(
        db=db,
        original_url=data.url,
        custom_code=data.custom_code,
        expires_in_days=data.expires_in_days,
        creator_ip=client_ip,
        password=data.password,
        max_clicks=data.max_clicks
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    if link is None:
        raise HTTPException(status_code=500, detail="Failed to create link")
    
    return ShortenResponse(
        short_url=format_short_url(cast(str, link.suffix)),
        suffix=cast(str, link.suffix),
        original_url=cast(str, link.destination),
        expires_at=cast(Optional[datetime], link.expires_at),
        created_at=cast(datetime, link.created_at),
        requires_password=link.password_hash is not None,
        max_clicks=link.max_clicks
    )


@router.get(
    "/stats/{code}",
    response_model=LinkStatsResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_link_stats(
    code: str,
    db: Session = Depends(get_db)
):
    """Get statistics for a shortened link."""
    stats = LinkService.get_link_stats(db, code.lower())
    
    if not stats:
        raise HTTPException(status_code=404, detail="Link not found")
    
    destination = cast(str, stats["destination"])
    created_at = cast(datetime, stats["created_at"])
    expires_at = cast(Optional[datetime], stats["expires_at"])
    suffix = cast(str, stats.get("suffix") or code.lower())

    return LinkStatsResponse(
        suffix=suffix,
        original_url=destination,
        created_at=created_at,
        expires_at=expires_at,
    )


@router.get(
    "/preview/{code}",
    response_model=LinkPreviewResponse,
    responses={404: {"model": ErrorResponse}}
)
async def preview_link(
    code: str,
    db: Session = Depends(get_db)
):
    """Preview a link before redirecting."""
    url, expired = LinkService.get_original_url(db, code.lower())

    if not url:
        if expired:
            raise HTTPException(status_code=410, detail="Link expired")
        raise HTTPException(status_code=404, detail="Link not found")

    return LinkPreviewResponse(
        suffix=code.lower(),
        original_url=url,
        is_safe=True
    )


@router.get("/check/{code}")
async def check_code_availability(
    code: str,
    db: Session = Depends(get_db)
):
    """Check if a custom code is available."""
    code_lower = code.lower()
    
    if is_reserved_code(code_lower):
        return {"available": False, "reason": "reserved"}
    
    if RedisService.code_exists(code_lower):
        return {"available": False, "reason": "taken"}
    
    existing = db.query(Link).filter(Link.suffix == code_lower).first()
    
    if existing:
        return {"available": False, "reason": "taken"}
    
    return {"available": True}


@router.post(
    "/unlock/{code}",
    response_model=PasswordUnlockResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
async def unlock_password_link(
    code: str,
    data: PasswordUnlockRequest,
    db: Session = Depends(get_db)
):
    """Unlock a password-protected link."""
    success, url = LinkService.verify_link_password(db, code.lower(), data.password)
    
    if not success:
        if url is None:
            # Link doesn't exist
            raise HTTPException(status_code=404, detail="Link not found")
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    return PasswordUnlockResponse(redirect_url=url)


@router.post(
    "/bulk/shorten",
    response_model=BulkShortenResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
async def bulk_shorten(
    request: Request,
    data: BulkShortenRequest,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_optional_api_key)
):
    """Create multiple shortened links in a single request. Requires API key."""
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required for bulk operations"
        )
    
    client_ip = get_client_ip(request)
    results = []
    success_count = 0
    error_count = 0
    
    for item in data.urls:
        link, error = LinkService.create_link(
            db=db,
            original_url=item.url,
            custom_code=item.custom_code,
            expires_in_days=item.expires_in_days,
            creator_ip=client_ip
        )
        
        if error:
            results.append(BulkShortenResultItem(
                success=False,
                url=item.url,
                error=error
            ))
            error_count += 1
        else:
            results.append(BulkShortenResultItem(
                success=True,
                url=item.url,
                short_url=format_short_url(cast(str, link.suffix)),
                suffix=cast(str, link.suffix)
            ))
            success_count += 1
    
    logger.info(f"Bulk shorten: {success_count} success, {error_count} errors")
    return BulkShortenResponse(
        results=results,
        success_count=success_count,
        error_count=error_count
    )


@router.post(
    "/bulk/delete",
    response_model=BulkDeleteResponse,
    responses={401: {"model": ErrorResponse}}
)
async def bulk_delete(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_optional_api_key)
):
    """Delete multiple links by their suffixes. Requires API key."""
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required for bulk operations"
        )
    
    deleted_count, not_found = LinkService.bulk_delete_links(db, data.suffixes)
    
    return BulkDeleteResponse(
        deleted_count=deleted_count,
        not_found=not_found
    )
