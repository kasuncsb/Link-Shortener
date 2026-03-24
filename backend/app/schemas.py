from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime, timezone
import re
from urllib.parse import urlparse
from .utils import utc_now, normalize_utc
from .env import get_env, get_int


class ShortenRequest(BaseModel):
    """Request schema for creating a short link."""
    model_config = {"extra": "allow"}
    
    url: str = Field(..., description="The URL to shorten")
    custom_code: Optional[str] = Field(
        None,
        description="Custom short code (optional)"
    )
    expires_in_days: Optional[int] = Field(
        None,
        ge=0,
        le=365,
        description="Days until link expires (optional)"
    )
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        value = str(v).strip()
        if not value:
            raise ValueError("Please enter a link.")

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Your link must start with http:// or https://.")
        if not parsed.netloc:
            raise ValueError("Please enter a complete link, including the website address.")

        if len(value) > 2048:
            raise ValueError("That link is too long. Please use a shorter URL.")

        # Long-link guard: input should be longer than a typical generated short URL.
        # This avoids shortening links that already look short without hardcoding providers.
        try:
            base = get_env("BASE_URL").rstrip("/")
            default_len = max(1, get_int("DEFAULT_CODE_LENGTH"))
            typical_short = len(f"{base}/{'x' * default_len}")
            if len(value) <= typical_short:
                raise ValueError("That link is already very short. Please enter the original long link.")
        except RuntimeError:
            # If env values are unavailable here, keep validation resilient.
            if len(value) <= 16:
                raise ValueError("That link is already very short. Please enter the original long link.")

        return value
    
    @field_validator('custom_code')
    @classmethod
    def validate_custom_code(cls, v):
        if v is None:
            return v

        min_len = get_int("MIN_CUSTOM_CODE_LENGTH")
        max_len = get_int("MAX_CUSTOM_CODE_LENGTH")
        if len(v) < min_len:
            raise ValueError(f"Your custom short link needs at least {min_len} characters.")
        if len(v) > max_len:
            raise ValueError(f"Your custom short link can be at most {max_len} characters.")
        
        # Only allow alphanumeric and hyphens
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$', v):
            raise ValueError(
                'Custom code must contain only letters, numbers, and hyphens. '
                'Cannot start or end with a hyphen.'
            )
        
        return v.lower()

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
                    if diff_days < 0:
                        diff_days = 0
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
