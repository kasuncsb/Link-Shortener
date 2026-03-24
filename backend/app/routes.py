from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import cast, Optional
from datetime import datetime

from .database import get_db
from .models import Link
from .schemas import (
    ShortenRequest,
    ShortenResponse,
    LinkStatsResponse,
    LinkPreviewResponse,
    ErrorResponse
)
from .services import LinkService
from .redis_client import RedisService
from .utils import format_short_url, is_reserved_code
from .meta_fetcher import fetch_meta
from .env import get_env

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
    db: Session = Depends(get_db)
):
    """Create a new shortened link."""
    client_ip = get_client_ip(request)
    
    allowed, remaining = RedisService.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="You're making requests too quickly. Please wait a bit and try again.",
            headers={"X-RateLimit-Remaining": "0"}
        )
    
    link, error = LinkService.create_link(
        db=db,
        original_url=data.url,
        custom_code=data.custom_code,
        expires_in_days=data.expires_in_days,
        creator_ip=client_ip
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    if link is None:
        raise HTTPException(status_code=500, detail="We could not create your short link right now. Please try again.")
    
    return ShortenResponse(
        short_url=format_short_url(cast(str, link.suffix)),
        suffix=cast(str, link.suffix),
        original_url=cast(str, link.destination),
        expires_at=cast(Optional[datetime], link.expires_at),
        created_at=cast(datetime, link.created_at)
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
        raise HTTPException(status_code=404, detail="We couldn't find that link.")
    
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
            raise HTTPException(status_code=410, detail="This link has expired.")
        raise HTTPException(status_code=404, detail="We couldn't find that link.")

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


@router.get("/meta")
async def get_link_meta(url: str):
    """
    Fetch Open Graph / meta-tag preview data for a URL.
    The frontend calls this to get preview info for the destination link.
    """
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Please enter a valid link that starts with http:// or https://.")
    meta = await fetch_meta(url)
    return meta


@router.get("/preview-debug/{code}")
async def preview_debug(
    code: str,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to verify social preview source for a short code.
    """
    url, expired = LinkService.get_original_url(db, code.lower())
    if not url:
        if expired:
            raise HTTPException(status_code=410, detail="This link has expired.")
        raise HTTPException(status_code=404, detail="We couldn't find that link.")

    base_url = get_env("BASE_URL").rstrip("/")
    source = "fallback"
    preview = {
        "title": "Link Shortener",
        "description": "TL;DR for your links. Get to the point. Fast & Secure.",
        "image": f"{base_url}/images/og-banner.jpg",
        "domain": base_url.replace("https://", "").replace("http://", ""),
    }
    try:
        dest = await fetch_meta(url)
        if dest and dest.get("title") and (dest.get("description") or dest.get("image")):
            source = "destination"
            preview = dest
    except Exception:
        pass

    return {
        "code": code.lower(),
        "short_url": f"{base_url}/{code.lower()}",
        "destination_url": url,
        "source": source,
        "preview": preview,
    }
