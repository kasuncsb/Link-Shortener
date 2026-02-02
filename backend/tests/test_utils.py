"""
Unit tests for utility functions.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils import (
    generate_short_code,
    is_valid_url,
    extract_domain,
    is_reserved_code,
    format_short_url,
    utc_now
)


class TestGenerateShortCode:
    """Tests for generate_short_code function."""
    
    def test_generates_correct_length(self):
        """Generated codes should have the configured length."""
        code = generate_short_code()
        assert len(code) >= 6  # Default minimum length
    
    def test_generates_unique_codes(self):
        """Generated codes should be unique."""
        codes = [generate_short_code() for _ in range(100)]
        assert len(set(codes)) == 100
    
    def test_codes_are_lowercase(self):
        """Generated codes should be lowercase."""
        code = generate_short_code()
        assert code == code.lower()
    
    def test_codes_are_alphanumeric(self):
        """Generated codes should only contain alphanumeric characters."""
        for _ in range(10):
            code = generate_short_code()
            assert code.isalnum() or "-" in code


class TestIsValidUrl:
    """Tests for is_valid_url function."""
    
    def test_valid_http_url(self):
        """HTTP URLs should be valid."""
        assert is_valid_url("http://example.com") is True
    
    def test_valid_https_url(self):
        """HTTPS URLs should be valid."""
        assert is_valid_url("https://example.com") is True
    
    def test_valid_url_with_path(self):
        """URLs with paths should be valid."""
        assert is_valid_url("https://example.com/path/to/page") is True
    
    def test_valid_url_with_query(self):
        """URLs with query strings should be valid."""
        assert is_valid_url("https://example.com?query=value") is True
    
    def test_invalid_url_no_scheme(self):
        """URLs without scheme should be invalid."""
        assert is_valid_url("example.com") is False
    
    def test_invalid_url_ftp(self):
        """FTP URLs should be invalid."""
        assert is_valid_url("ftp://example.com") is False
    
    def test_empty_string(self):
        """Empty string should be invalid."""
        assert is_valid_url("") is False


class TestExtractDomain:
    """Tests for extract_domain function."""
    
    def test_simple_domain(self):
        """Should extract domain from simple URL."""
        assert extract_domain("https://example.com") == "example.com"
    
    def test_domain_with_subdomain(self):
        """Should extract domain including subdomain."""
        result = extract_domain("https://www.example.com")
        assert "example.com" in result
    
    def test_domain_with_path(self):
        """Should extract domain ignoring path."""
        assert extract_domain("https://example.com/path") == "example.com"


class TestIsReservedCode:
    """Tests for is_reserved_code function."""
    
    def test_api_is_reserved(self):
        """'api' should be reserved."""
        assert is_reserved_code("api") is True
    
    def test_admin_is_reserved(self):
        """'admin' should be reserved."""
        assert is_reserved_code("admin") is True
    
    def test_regular_code_not_reserved(self):
        """Regular codes should not be reserved."""
        assert is_reserved_code("abc123") is False


class TestFormatShortUrl:
    """Tests for format_short_url function."""
    
    def test_formats_with_base_url(self):
        """Should format code with base URL."""
        result = format_short_url("abc123")
        assert "abc123" in result
        assert result.startswith("http")


class TestUtcNow:
    """Tests for utc_now function."""
    
    def test_returns_datetime(self):
        """Should return a datetime object."""
        from datetime import datetime
        result = utc_now()
        assert isinstance(result, datetime)
    
    def test_has_timezone(self):
        """Should have UTC timezone."""
        result = utc_now()
        assert result.tzinfo is not None
