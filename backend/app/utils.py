import secrets
import string
from typing import Optional
from datetime import datetime, timezone
from .env import get_env, get_int, get_json_list


def generate_short_code(length: Optional[int] = None) -> str:
    """Generate a random short code using nanoid-style characters."""
    if length is None:
        length = get_int("DEFAULT_CODE_LENGTH")
    
    # URL-safe characters (similar to nanoid)
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def is_reserved_code(code: str) -> bool:
    """Check if a code is reserved."""
    reserved = get_json_list("RESERVED_CODES")
    return code.lower() in [r.lower() for r in reserved]


def format_short_url(code: str) -> str:
    """Format a short code into a full URL."""
    base = get_env("BASE_URL").rstrip('/')
    return f"{base}/{code}"


def utc_now() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to timezone-aware UTC (assume naive is UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
