from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator
from typing import Optional, List, Union
from datetime import datetime, timezone
import re
from .utils import utc_now, normalize_utc
from .security import validate_url_security, sanitize_custom_code


class ShortenRequest(BaseModel):
    """Request schema for creating a short link."""
    model_config = {"extra": "allow"}
    
    url: str = Field(..., description="The URL to shorten")
    custom_code: Optional[str] = Field(
        None,
        min_length=3,
        max_length=20,
        description="Custom short code (optional)"
    )
    expires_in_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Days until link expires (optional)"
    )
    password: Optional[str] = Field(
        None,
        min_length=4,
        max_length=64,
        description="Password to protect the link (optional)"
    )
    max_clicks: Optional[int] = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of clicks before link expires (optional)"
    )
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        # Basic URL format validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError('Invalid URL format. Must start with http:// or https://')
        
        if len(v) > 2048:
            raise ValueError('URL too long. Maximum 2048 characters.')
        
        # Security validation - block private IPs, localhost, dangerous URLs
        is_safe, error = validate_url_security(v)
        if not is_safe:
            raise ValueError(error or 'URL failed security validation')
        
        return v
    
    @field_validator('custom_code')
    @classmethod
    def validate_custom_code(cls, v):
        if v is None:
            return v
        
        # Use security module for validation and sanitization
        is_valid, sanitized, error = sanitize_custom_code(v)
        if not is_valid:
            raise ValueError(error or 'Invalid custom code')
        
        return sanitized

    @model_validator(mode='before')
    @classmethod
    def map_legacy_fields(cls, values):
        # Allow frontend to send older keys: `custom_suffix` and `expires_at`.
        # Map them to `custom_code` and `expires_in_days` respectively.
        if not isinstance(values, dict):
            return values

        # Map custom_suffix -> custom_code
        if 'custom_suffix' in values and 'custom_code' not in values:
            try:
                values['custom_code'] = values.pop('custom_suffix')
            except Exception:
                pass

        # Map expires_at (ISO date) -> expires_in_days
        if 'expires_at' in values and 'expires_in_days' not in values:
            try:
                raw = values.get('expires_at')
                # Accept date-only like YYYY-MM-DD or full ISO
                if isinstance(raw, str):
                    # If only date provided, append time to parse
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
                        selected = datetime.fromisoformat(raw + 'T00:00:00').replace(tzinfo=timezone.utc)
                    else:
                        selected = datetime.fromisoformat(raw)
                        selected = normalize_utc(selected)
                    today = utc_now()
                    diff = (selected or today) - today
                    diff_days = int(diff.total_seconds() // 86400)
                    if diff_days < 1:
                        diff_days = 1
                    values['expires_in_days'] = min(diff_days, 365)
            except Exception:
                # If parsing fails, ignore and let validation handle it
                pass

        return values


class ShortenResponse(BaseModel):
    """Response schema for created short link."""
    
    short_url: str
    suffix: str
    original_url: str
    expires_at: Optional[datetime]
    created_at: datetime
    requires_password: bool = False
    max_clicks: Optional[int] = None
    
    class Config:
        from_attributes = True


class LinkStatsResponse(BaseModel):
    """Response schema for link statistics."""
    
    suffix: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class LinkPreviewResponse(BaseModel):
    """Response schema for link preview."""
    
    suffix: str
    original_url: str
    is_safe: bool = True
    warning: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    database: bool
    redis: bool
    version: str


class PasswordUnlockRequest(BaseModel):
    """Request to unlock a password-protected link."""
    password: str = Field(..., min_length=1)


class PasswordUnlockResponse(BaseModel):
    """Response after successful password unlock."""
    redirect_url: str


class BulkShortenItem(BaseModel):
    """Single item for bulk shorten request."""
    url: str
    custom_code: Optional[str] = None
    expires_in_days: Optional[int] = None


class BulkShortenRequest(BaseModel):
    """Request schema for bulk link shortening."""
    urls: List[BulkShortenItem] = Field(..., max_length=100)


class BulkShortenResultItem(BaseModel):
    """Result of a single bulk shorten operation."""
    success: bool
    url: Optional[str] = None
    short_url: Optional[str] = None
    suffix: Optional[str] = None
    error: Optional[str] = None


class BulkShortenResponse(BaseModel):
    """Response schema for bulk shortening."""
    results: List[BulkShortenResultItem]
    success_count: int
    error_count: int


class BulkDeleteRequest(BaseModel):
    """Request schema for bulk deletion."""
    suffixes: List[str] = Field(..., max_length=100)


class BulkDeleteResponse(BaseModel):
    """Response schema for bulk deletion."""
    deleted_count: int
    not_found: List[str]
