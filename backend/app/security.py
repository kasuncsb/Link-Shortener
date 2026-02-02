"""
Security utilities for URL validation and input sanitization.
Blocks private IPs, localhost, and dangerous URLs.
"""

import ipaddress
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from .env import get_json_list
from .logging_config import get_logger

logger = get_logger(__name__)

# Private/reserved IP ranges
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Default blocked domains (can be extended via env)
DEFAULT_BLOCKED_DOMAINS = [
    "localhost",
    "localhost.localdomain",
    "local",
]

# Blocked URL schemes
BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript", "vbscript"}


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, localhost, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in PRIVATE_IP_RANGES:
            if ip in network:
                return True
        return False
    except ValueError:
        return False


def get_blocked_domains() -> set:
    """Get the set of blocked domains from environment and defaults."""
    blocked = set(DEFAULT_BLOCKED_DOMAINS)
    try:
        env_blocked = get_json_list("BLOCKED_DOMAINS")
        blocked.update(d.lower() for d in env_blocked)
    except RuntimeError:
        pass
    return blocked


def is_domain_blocked(domain: str) -> bool:
    """Check if a domain is in the blocklist."""
    domain_lower = domain.lower()
    blocked = get_blocked_domains()
    
    # Check exact match
    if domain_lower in blocked:
        return True
    
    # Check if it's a subdomain of a blocked domain
    for blocked_domain in blocked:
        if domain_lower.endswith("." + blocked_domain):
            return True
    
    return False


def extract_host_from_url(url: str) -> Optional[str]:
    """Extract the host from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.hostname
    except Exception:
        return None


def validate_url_security(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL for security issues.
    
    Returns:
        Tuple of (is_safe, error_message)
        If is_safe is True, error_message is None
    """
    if not url:
        return False, "URL is required"
    
    url_lower = url.lower().strip()
    
    # Check URL length
    if len(url) > 2048:
        return False, "URL too long (max 2048 characters)"
    
    # Check scheme
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        
        if scheme not in ("http", "https"):
            return False, f"Invalid URL scheme '{scheme}'. Only http and https are allowed"
        
        if scheme in BLOCKED_SCHEMES:
            return False, f"URL scheme '{scheme}' is not allowed"
        
    except Exception:
        return False, "Invalid URL format"
    
    # Extract host
    host = extract_host_from_url(url)
    if not host:
        return False, "Could not extract host from URL"
    
    # Check for blocked domains
    if is_domain_blocked(host):
        logger.warning(f"Blocked domain attempted: {host}")
        return False, "This domain is not allowed"
    
    # Check if host is an IP address and if it's private
    if is_private_ip(host):
        logger.warning(f"Private IP attempted: {host}")
        return False, "URLs pointing to private/local addresses are not allowed"
    
    # Check for common bypass attempts
    bypass_patterns = [
        r"^https?://[^/]*@",  # URL with credentials
        r"^https?://.*\x00",  # Null byte injection
        r"^https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",  # Direct IP (unless allowed)
    ]
    
    for pattern in bypass_patterns[:2]:  # Skip IP pattern for now
        if re.match(pattern, url_lower):
            return False, "Invalid URL format"
    
    return True, None


def sanitize_custom_code(code: str) -> Tuple[bool, str, Optional[str]]:
    """
    Sanitize and validate a custom short code.
    
    Returns:
        Tuple of (is_valid, sanitized_code, error_message)
    """
    if not code:
        return True, "", None
    
    # Remove any whitespace
    code = code.strip()
    
    # Convert to lowercase
    code = code.lower()
    
    # Only allow alphanumeric and hyphens
    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', code):
        return False, code, "Code must contain only letters, numbers, and hyphens. Cannot start or end with hyphen."
    
    # Check for potentially dangerous patterns
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+=',
        r'<iframe',
        r'<img',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return False, code, "Invalid characters in code"
    
    return True, code, None


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return text
    
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&#x27;",
        ">": "&gt;",
        "<": "&lt;",
    }
    
    return "".join(html_escape_table.get(c, c) for c in text)
