"""
Unit tests for security module.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.security import (
    is_private_ip,
    is_domain_blocked,
    validate_url_security,
    sanitize_custom_code,
    escape_html
)


class TestIsPrivateIp:
    """Tests for is_private_ip function."""
    
    def test_localhost_ipv4(self):
        """127.0.0.1 should be private."""
        assert is_private_ip("127.0.0.1") is True
    
    def test_private_10_range(self):
        """10.x.x.x should be private."""
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True
    
    def test_private_172_range(self):
        """172.16-31.x.x should be private."""
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True
    
    def test_private_192_range(self):
        """192.168.x.x should be private."""
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True
    
    def test_public_ip(self):
        """Public IPs should not be private."""
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False
    
    def test_invalid_ip(self):
        """Invalid IPs should return False."""
        assert is_private_ip("not-an-ip") is False
        assert is_private_ip("256.256.256.256") is False


class TestIsDomainBlocked:
    """Tests for is_domain_blocked function."""
    
    def test_localhost_blocked(self):
        """localhost should be blocked."""
        assert is_domain_blocked("localhost") is True
    
    def test_subdomain_of_blocked(self):
        """Subdomains of blocked domains should be blocked."""
        assert is_domain_blocked("api.localhost") is True
    
    def test_public_domain_not_blocked(self):
        """Public domains should not be blocked."""
        assert is_domain_blocked("example.com") is False


class TestValidateUrlSecurity:
    """Tests for validate_url_security function."""
    
    def test_valid_public_url(self):
        """Valid public URLs should pass."""
        is_safe, error = validate_url_security("https://example.com")
        assert is_safe is True
        assert error is None
    
    def test_localhost_blocked(self):
        """Localhost URLs should be blocked."""
        is_safe, error = validate_url_security("http://localhost/admin")
        assert is_safe is False
        assert error is not None
    
    def test_private_ip_blocked(self):
        """Private IP URLs should be blocked."""
        is_safe, error = validate_url_security("http://192.168.1.1")
        assert is_safe is False
    
    def test_url_too_long(self):
        """URLs over 2048 chars should be blocked."""
        long_url = "https://example.com/" + "a" * 2048
        is_safe, error = validate_url_security(long_url)
        assert is_safe is False
        assert "too long" in error.lower()
    
    def test_empty_url(self):
        """Empty URLs should fail."""
        is_safe, error = validate_url_security("")
        assert is_safe is False
    
    def test_file_scheme_blocked(self):
        """File URLs should be blocked."""
        is_safe, error = validate_url_security("file:///etc/passwd")
        assert is_safe is False


class TestSanitizeCustomCode:
    """Tests for sanitize_custom_code function."""
    
    def test_valid_code(self):
        """Valid codes should pass."""
        is_valid, sanitized, error = sanitize_custom_code("my-link")
        assert is_valid is True
        assert sanitized == "my-link"
        assert error is None
    
    def test_uppercase_to_lowercase(self):
        """Codes should be lowercased."""
        is_valid, sanitized, error = sanitize_custom_code("MyLink")
        assert is_valid is True
        assert sanitized == "mylink"
    
    def test_code_with_hyphen(self):
        """Codes with hyphens should be valid."""
        is_valid, sanitized, error = sanitize_custom_code("my-cool-link")
        assert is_valid is True
    
    def test_code_starting_with_hyphen_invalid(self):
        """Codes starting with hyphen should be invalid."""
        is_valid, sanitized, error = sanitize_custom_code("-mylink")
        assert is_valid is False
    
    def test_code_with_special_chars_invalid(self):
        """Codes with special characters should be invalid."""
        is_valid, sanitized, error = sanitize_custom_code("my@link")
        assert is_valid is False
    
    def test_empty_code(self):
        """Empty codes should be valid (treated as no custom code)."""
        is_valid, sanitized, error = sanitize_custom_code("")
        assert is_valid is True
        assert sanitized == ""


class TestEscapeHtml:
    """Tests for escape_html function."""
    
    def test_escapes_less_than(self):
        """< should be escaped."""
        assert "&lt;" in escape_html("<script>")
    
    def test_escapes_greater_than(self):
        """> should be escaped."""
        assert "&gt;" in escape_html("<script>")
    
    def test_escapes_ampersand(self):
        """& should be escaped."""
        assert "&amp;" in escape_html("AT&T")
    
    def test_escapes_quotes(self):
        """Quotes should be escaped."""
        assert "&quot;" in escape_html('say "hello"')
    
    def test_preserves_normal_text(self):
        """Normal text should be preserved."""
        assert escape_html("hello world") == "hello world"
