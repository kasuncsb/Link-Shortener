"""
Integration tests for API endpoints.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestShortenEndpoint:
    """Tests for POST /api/shorten."""
    
    def test_shorten_valid_url(self, client, sample_url):
        """Should create a short link for a valid URL."""
        response = client.post("/api/shorten", json={"url": sample_url})
        assert response.status_code == 200
        data = response.json()
        assert "short_url" in data
        assert "suffix" in data
        assert data["original_url"] == sample_url
    
    def test_shorten_with_custom_code(self, client, sample_url):
        """Should create a short link with custom code."""
        response = client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "mycode"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["suffix"] == "mycode"
    
    def test_shorten_with_expiry(self, client, sample_url):
        """Should create a short link with expiry."""
        response = client.post("/api/shorten", json={
            "url": sample_url,
            "expires_in_days": 7
        })
        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None
    
    def test_shorten_invalid_url(self, client):
        """Should reject invalid URLs."""
        response = client.post("/api/shorten", json={"url": "not-a-url"})
        assert response.status_code == 422  # Validation error
    
    def test_shorten_duplicate_custom_code(self, client, sample_url):
        """Should reject duplicate custom codes."""
        # Create first link
        client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "duplicate"
        })
        # Try to create with same code
        response = client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "duplicate"
        })
        assert response.status_code == 400
        assert "taken" in response.json()["detail"].lower()


class TestCheckEndpoint:
    """Tests for GET /api/check/{code}."""
    
    def test_check_available_code(self, client):
        """Should report available codes."""
        response = client.get("/api/check/newcode")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
    
    def test_check_taken_code(self, client, sample_url):
        """Should report taken codes."""
        # Create a link first
        client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "takencode"
        })
        
        response = client.get("/api/check/takencode")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["reason"] == "taken"
    
    def test_check_reserved_code(self, client):
        """Should report reserved codes."""
        response = client.get("/api/check/api")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["reason"] == "reserved"


class TestPreviewEndpoint:
    """Tests for GET /api/preview/{code}."""
    
    def test_preview_existing_link(self, client, sample_url):
        """Should return preview for existing link."""
        # Create link
        create_response = client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "preview"
        })
        
        response = client.get("/api/preview/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["original_url"] == sample_url
    
    def test_preview_nonexistent_link(self, client):
        """Should return 404 for nonexistent link."""
        response = client.get("/api/preview/doesnotexist")
        assert response.status_code == 404


class TestStatsEndpoint:
    """Tests for GET /api/stats/{code}."""
    
    def test_stats_existing_link(self, client, sample_url):
        """Should return stats for existing link."""
        # Create link
        client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "stats"
        })
        
        response = client.get("/api/stats/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["suffix"] == "stats"
        assert data["original_url"] == sample_url
    
    def test_stats_nonexistent_link(self, client):
        """Should return 404 for nonexistent link."""
        response = client.get("/api/stats/doesnotexist")
        assert response.status_code == 404


class TestPasswordProtectedLinks:
    """Tests for password-protected links."""
    
    def test_create_password_protected_link(self, client, sample_url):
        """Should create a password-protected link."""
        response = client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "protected",
            "password": "secret123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["requires_password"] is True
    
    def test_unlock_with_correct_password(self, client, sample_url):
        """Should unlock link with correct password."""
        # Create protected link
        client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "unlock",
            "password": "secret123"
        })
        
        response = client.post("/api/unlock/unlock", json={
            "password": "secret123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["redirect_url"] == sample_url
    
    def test_unlock_with_wrong_password(self, client, sample_url):
        """Should reject incorrect password."""
        # Create protected link
        client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "wrongpw",
            "password": "secret123"
        })
        
        response = client.post("/api/unlock/wrongpw", json={
            "password": "wrongpassword"
        })
        assert response.status_code == 401


class TestOneTimeLinks:
    """Tests for one-time/click-limited links."""
    
    def test_create_max_clicks_link(self, client, sample_url):
        """Should create a link with max clicks."""
        response = client.post("/api/shorten", json={
            "url": sample_url,
            "custom_code": "onetime",
            "max_clicks": 1
        })
        assert response.status_code == 200
        data = response.json()
        assert data["max_clicks"] == 1


class TestHealthEndpoint:
    """Tests for GET /health."""
    
    def test_health_check(self, client):
        """Should return health status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "redis" in data
