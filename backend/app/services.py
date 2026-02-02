from datetime import datetime, timedelta
from typing import Optional, Any, cast, List
import time
import hashlib
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from .models import Link
from .redis_client import RedisService
from .utils import (
    generate_short_code,
    is_reserved_code,
    extract_domain,
    detect_user_agent_type,
    sanitize_referer,
    format_short_url,
    utc_now,
    normalize_utc
)
from .env import get_int
from .logging_config import get_logger

logger = get_logger(__name__)

# Constants for retry logic
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.1  # seconds


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


class LinkService:
    """Service for managing shortened links."""
    
    @staticmethod
    def create_link(
        db: Session,
        original_url: str,
        custom_code: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        creator_ip: Optional[str] = None,
        password: Optional[str] = None,
        max_clicks: Optional[int] = None
    ) -> tuple[Optional[Link], Optional[str]]:
        """
        Create a new shortened link.
        Returns (link, error_message).
        Handles race conditions with retry logic.
        """
        # Generate or validate short code
        if custom_code:
            code = custom_code.lower()
            
            # Check reserved words
            if is_reserved_code(code):
                logger.warning(f"Attempted reserved code: {code}")
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
            code = None
        
        # Calculate expiry
        expires_at = None
        if expires_in_days:
            expires_at = utc_now() + timedelta(days=expires_in_days)
        else:
            default_days = get_int("DEFAULT_EXPIRY_DAYS")
            expires_at = utc_now() + timedelta(days=default_days)
        
        # Retry loop for handling race conditions
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Generate code if not custom
                if not custom_code:
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
                        logger.error("Failed to generate unique code after max attempts")
                        return None, "Failed to generate unique code. Please try again."
                
                # Create link with optional password and max_clicks
                password_hash = hash_password(password) if password else None
                
                link = Link(
                    suffix=code,
                    destination=original_url,
                    expires_at=expires_at,
                    ip_address=creator_ip,
                    password_hash=password_hash,
                    max_clicks=max_clicks,
                    click_count=0
                )
                
                db.add(link)
                db.commit()
                db.refresh(link)
                
                # Cache in Redis
                RedisService.cache_link(code, original_url, expires_at=expires_at)
                RedisService.add_code_to_set(code)
                
                logger.info(f"Created link: {code} -> {original_url[:50]}...")
                return link, None
                
            except IntegrityError as e:
                db.rollback()
                
                if custom_code:
                    # Custom code collision - no retry
                    logger.warning(f"Race condition: custom code already taken: {code}")
                    return None, "This short code is already taken"
                
                # Random code collision - retry with new code
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Code collision, retrying in {delay}s (attempt {attempt + 1})")
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to create link after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return None, "Failed to create link due to high traffic. Please try again."
        
        return None, "Failed to create link. Please try again."
    
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
        cached = RedisService.get_cached_link(code)
        if cached:
            return cached, False

        # Check database
        link = db.query(Link).filter(Link.suffix == code).first()

        if not link:
            return None, False

        # Check expiry
        expires_at_val = normalize_utc(cast(Optional[datetime], link.expires_at))
        if expires_at_val and expires_at_val < utc_now():
            # Ensure Redis doesn't have the expired key
            RedisService.delete_cached_link(code)
            RedisService.remove_code_from_set(code)
            return None, True

        # Cache for future requests (set TTL based on DB expiry)
        destination = cast(str, link.destination)
        RedisService.cache_link(code, destination, expires_at=expires_at_val)

        return destination, False
    
    @staticmethod
    # Click recording removed per user's request
    
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
        """Remove expired entries from Redis. Returns number removed from Redis."""
        now = utc_now()
        expired_links = db.query(Link).filter(Link.expires_at != None).filter(Link.expires_at < now).all()
        count = 0
        for link in expired_links:
            suffix = getattr(link, 'suffix', None)
            if not suffix:
                continue
            try:
                RedisService.delete_cached_link(suffix)
                RedisService.remove_code_from_set(suffix)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to cleanup expired link {suffix}: {e}")
                continue
        
        if count > 0:
            logger.info(f"Cleaned up {count} expired links from Redis")
        return count
    
    @staticmethod
    def increment_click_count(db: Session, code: str) -> tuple[bool, bool]:
        """
        Increment click count for a link.
        Returns (success, max_reached).
        """
        link = db.query(Link).filter(Link.suffix == code).first()
        if not link:
            return False, False
        
        # Increment click count
        link.click_count = (link.click_count or 0) + 1
        db.commit()
        
        # Check if max clicks reached
        if link.max_clicks and link.click_count >= link.max_clicks:
            logger.info(f"Link {code} reached max clicks ({link.max_clicks})")
            return True, True
        
        return True, False
    
    @staticmethod
    def verify_link_password(db: Session, code: str, password: str) -> tuple[bool, Optional[str]]:
        """
        Verify password for a password-protected link.
        Returns (success, original_url or None).
        """
        link = db.query(Link).filter(Link.suffix == code).first()
        if not link:
            return False, None
        
        if not link.password_hash:
            # Link is not password protected
            return True, link.destination
        
        if verify_password(password, link.password_hash):
            return True, link.destination
        
        return False, None
    
    @staticmethod
    def bulk_delete_links(db: Session, suffixes: List[str]) -> tuple[int, List[str]]:
        """
        Delete multiple links by their suffixes.
        Returns (deleted_count, not_found_list).
        """
        deleted_count = 0
        not_found = []
        
        for suffix in suffixes:
            suffix_lower = suffix.lower()
            link = db.query(Link).filter(Link.suffix == suffix_lower).first()
            
            if link:
                db.delete(link)
                RedisService.delete_cached_link(suffix_lower)
                RedisService.remove_code_from_set(suffix_lower)
                deleted_count += 1
            else:
                not_found.append(suffix)
        
        db.commit()
        logger.info(f"Bulk deleted {deleted_count} links")
        return deleted_count, not_found

