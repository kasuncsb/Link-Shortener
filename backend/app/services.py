from datetime import datetime, timedelta
from typing import Optional, Any, cast
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import Link
from .redis_client import RedisService
from .utils import (
    generate_short_code,
    is_reserved_code,
    format_short_url,
    utc_now,
    normalize_utc
)
from .env import get_int


class LinkService:
    """Service for managing shortened links."""
    
    @staticmethod
    def create_link(
        db: Session,
        original_url: str,
        custom_code: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        creator_ip: Optional[str] = None
    ) -> tuple[Optional[Link], Optional[str]]:
        """
        Create a new shortened link.
        Returns (link, error_message).
        """

        # Generate or validate short code
        if custom_code:
            code = custom_code.lower()
            
            # Check reserved words
            if is_reserved_code(code):
                return None, "This short code is reserved"
            
            # Check length
            min_len = get_int("MIN_CUSTOM_CODE_LENGTH")
            max_len = get_int("MAX_CUSTOM_CODE_LENGTH")
            if len(code) < min_len:
                return None, f"Code must be at least {min_len} characters"
            if len(code) > max_len:
                return None, f"Code must be at most {max_len} characters"
            
            # Check if code exists (Redis first, then DB)
            if RedisService.code_exists(code):
                return None, "This short code is already taken"

            existing = db.query(Link).filter(Link.suffix == code).first()
            if existing:
                return None, "This short code is already taken"
        else:
            # Generate random code
            max_attempts = 10
            code = None
            for _ in range(max_attempts):
                candidate = generate_short_code()
                if not RedisService.code_exists(candidate):
                    existing = db.query(Link).filter(
                        Link.suffix == candidate
                    ).first()
                    if not existing:
                        code = candidate
                        break
            
            if not code:
                return None, "Failed to generate unique code. Please try again."
        
        # Calculate expiry — None means the link never expires
        expires_at = None
        if expires_in_days is not None and expires_in_days >= 0:
            expires_at = utc_now() + timedelta(days=expires_in_days)
        
        # Create link
        link = Link(
            suffix=code,
            destination=original_url,
            expires_at=expires_at,
            ip_address=creator_ip
        )
        
        try:
            db.add(link)
            db.commit()
            db.refresh(link)
        except SQLAlchemyError:
            db.rollback()
            return None, "We could not create your short link right now. Please try again."
        
        # Cache in Redis (include expiry if set) — Redis TTL will match DB expiry
        try:
            RedisService.cache_link(code, original_url, expires_at=expires_at)
            RedisService.add_code_to_set(code)
        except Exception:
            # Cache should never block successful link creation.
            pass
        
        return link, None
    
    @staticmethod
    def get_link_by_code(db: Session, code: str) -> Optional[Link]:
        """Get a link by its suffix."""
        return db.query(Link).filter(Link.suffix == code).first()
    
    @staticmethod
    def get_original_url(db: Session, code: str) -> tuple[Optional[str], bool]:
        """
        Get original URL for a suffix.
        Returns tuple (url_or_none, expired_flag).
        Checks Redis cache first, falls back to DB. If DB row exists but is expired,
        returns (None, True). If not found, returns (None, False).
        """
        # Check cache first
        try:
            cached = RedisService.get_cached_link(code)
        except Exception:
            cached = None
        if cached:
            return cached, False

        # Check database
        try:
            link = db.query(Link).filter(Link.suffix == code).first()
        except SQLAlchemyError as exc:
            raise RuntimeError("Database lookup failed") from exc

        if not link:
            return None, False

        # Check expiry
        expires_at_val = normalize_utc(cast(Optional[datetime], link.expires_at))
        if expires_at_val and expires_at_val < utc_now():
            # Ensure Redis link cache is cleared but keep code in used set
            # so the expired suffix cannot be reused.
            try:
                RedisService.delete_cached_link(code)
            except Exception:
                pass
            return None, True

        # Cache for future requests (set TTL based on DB expiry)
        destination = cast(str, link.destination)
        try:
            RedisService.cache_link(code, destination, expires_at=expires_at_val)
        except Exception:
            pass

        return destination, False
    
    @staticmethod
    def get_link_stats(db: Session, code: str) -> Optional[dict[str, Any]]:
        """Get statistics for a link."""
        link = db.query(Link).filter(Link.suffix == code).first()
        
        if not link:
            return None
        
        suffix = cast(str, link.suffix)
        return {
            "suffix": suffix,
            "destination": cast(str, link.destination),
            "short_url": format_short_url(suffix),
            "created_at": cast(datetime, link.created_at),
            "expires_at": cast(Optional[datetime], link.expires_at),
        }
    
    @staticmethod
    def deactivate_link(db: Session, code: str) -> bool:
        """Delete a link from DB and Redis."""
        link = db.query(Link).filter(Link.suffix == code).first()
        
        if not link:
            return False
        
        db.delete(link)
        db.commit()
        
        RedisService.delete_cached_link(code)
        RedisService.remove_code_from_set(code)
        
        return True
    
    @staticmethod
    def cleanup_expired_links(db: Session) -> int:
        """Remove expired URL caches from Redis. Suffixes stay reserved to prevent reuse."""
        now = utc_now()
        expired_links = db.query(Link).filter(Link.expires_at != None).filter(Link.expires_at < now).all()
        count = 0
        for link in expired_links:
            try:
                suffix = cast(str, link.suffix)
                RedisService.delete_cached_link(suffix)
                # Do NOT call remove_code_from_set — expired suffixes must remain reserved
                count += 1
            except Exception:
                continue
        return count
