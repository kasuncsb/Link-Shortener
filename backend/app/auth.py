"""
Authentication utilities for API key management.
Provides optional API key authentication for link creation.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .models import ApiKey
from .logging_config import get_logger

logger = get_logger(__name__)


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> Tuple[str, str]:
    """
    Generate a new API key.
    Returns (plaintext_key, hashed_key).
    The plaintext key should only be shown once to the user.
    """
    # Generate a secure random key with prefix for easy identification
    key = f"lks_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(key)
    return key, key_hash


def validate_api_key(db: Session, key: str) -> Optional[ApiKey]:
    """
    Validate an API key and return the ApiKey model if valid.
    Returns None if the key is invalid or inactive.
    """
    if not key:
        return None
    
    # Remove any whitespace
    key = key.strip()
    
    # Check for valid prefix
    if not key.startswith("lks_"):
        return None
    
    key_hash = hash_api_key(key)
    
    api_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True
    ).first()
    
    if api_key:
        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"API key used: {api_key.name or 'unnamed'}")
    
    return api_key


def get_optional_api_key(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[ApiKey]:
    """
    FastAPI dependency to optionally extract and validate an API key.
    Returns the ApiKey if valid, None otherwise.
    Does not raise an error if no key is provided.
    """
    # Check header first
    auth_header = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    
    if auth_header:
        # Handle Bearer token format
        if auth_header.startswith("Bearer "):
            auth_header = auth_header[7:]
        
        api_key = validate_api_key(db, auth_header)
        return api_key
    
    return None


def require_api_key(
    request: Request,
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    FastAPI dependency to require a valid API key.
    Raises HTTPException if no valid key is provided.
    """
    api_key = get_optional_api_key(request, db)
    
    if not api_key:
        logger.warning(f"Unauthorized API access attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=401,
            detail="Valid API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return api_key


def create_api_key(db: Session, name: Optional[str] = None, rate_limit: int = 1000) -> Tuple[str, ApiKey]:
    """
    Create a new API key and store it in the database.
    Returns (plaintext_key, ApiKey model).
    """
    from .utils import utc_now
    
    key, key_hash = generate_api_key()
    
    api_key = ApiKey(
        key_hash=key_hash,
        name=name,
        created_at=utc_now(),
        rate_limit=rate_limit,
        is_active=True
    )
    
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    logger.info(f"Created new API key: {name or 'unnamed'}")
    
    return key, api_key


def deactivate_api_key(db: Session, key_id: int) -> bool:
    """Deactivate an API key by ID."""
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not api_key:
        return False
    
    api_key.is_active = False
    db.commit()
    
    logger.info(f"Deactivated API key: {api_key.name or 'unnamed'} (ID: {key_id})")
    return True
