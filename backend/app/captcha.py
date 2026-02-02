"""
Cloudflare Turnstile CAPTCHA verification.
Provides CAPTCHA verification for anonymous link creation.
"""

import httpx
from typing import Optional

from .env import get_env_optional, get_bool_optional
from .logging_config import get_logger

logger = get_logger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def is_turnstile_enabled() -> bool:
    """Check if Turnstile CAPTCHA is enabled."""
    return get_bool_optional("TURNSTILE_ENABLED", False)


def get_site_key() -> Optional[str]:
    """Get the Turnstile site key for frontend."""
    return get_env_optional("TURNSTILE_SITE_KEY") or None


def get_secret_key() -> Optional[str]:
    """Get the Turnstile secret key for backend verification."""
    return get_env_optional("TURNSTILE_SECRET_KEY") or None


async def verify_turnstile(token: str, ip_address: Optional[str] = None) -> bool:
    """
    Verify a Turnstile CAPTCHA token.
    
    Args:
        token: The cf-turnstile-response token from frontend
        ip_address: Optional IP address of the user
        
    Returns:
        True if verification successful, False otherwise
    """
    if not is_turnstile_enabled():
        # CAPTCHA disabled - allow all requests
        return True
    
    secret_key = get_secret_key()
    if not secret_key:
        logger.warning("Turnstile enabled but secret key not configured")
        return True  # Fail open if misconfigured
    
    if not token:
        logger.warning("Turnstile verification failed: no token provided")
        return False
    
    try:
        data = {
            "secret": secret_key,
            "response": token,
        }
        
        if ip_address:
            data["remoteip"] = ip_address
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TURNSTILE_VERIFY_URL, data=data)
            result = response.json()
        
        success = result.get("success", False)
        
        if not success:
            error_codes = result.get("error-codes", [])
            logger.warning(f"Turnstile verification failed: {error_codes}")
        else:
            logger.debug("Turnstile verification successful")
        
        return success
        
    except httpx.TimeoutException:
        logger.error("Turnstile verification timed out")
        return True  # Fail open on timeout
    except httpx.RequestError as e:
        logger.error(f"Turnstile verification request error: {e}")
        return True  # Fail open on network error
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return True  # Fail open on unexpected error
