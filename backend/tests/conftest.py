"""
Pytest fixtures for Link Shortener tests.
Provides test database, mock Redis, and FastAPI test client.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient


# Mock Redis before importing app modules
class MockRedisService:
    """Mock Redis service for testing."""
    
    _cache = {}
    _codes_set = set()
    _rate_limits = {}
    
    @classmethod
    def reset(cls):
        cls._cache = {}
        cls._codes_set = set()
        cls._rate_limits = {}
    
    @staticmethod
    def cache_link(code: str, url: str, expires_at=None) -> bool:
        MockRedisService._cache[code] = {"url": url, "expires_at": expires_at}
        return True
    
    @staticmethod
    def get_cached_link(code: str):
        data = MockRedisService._cache.get(code)
        return data.get("url") if data else None
    
    @staticmethod
    def delete_cached_link(code: str) -> bool:
        MockRedisService._cache.pop(code, None)
        return True
    
    @staticmethod
    def add_code_to_set(code: str) -> bool:
        MockRedisService._codes_set.add(code)
        return True
    
    @staticmethod
    def code_exists(code: str) -> bool:
        return code in MockRedisService._codes_set
    
    @staticmethod
    def remove_code_from_set(code: str) -> bool:
        MockRedisService._codes_set.discard(code)
        return True
    
    @staticmethod
    def check_rate_limit(ip: str, limit=None) -> tuple:
        count = MockRedisService._rate_limits.get(ip, 0)
        limit = limit or 30
        if count >= limit:
            return False, 0
        MockRedisService._rate_limits[ip] = count + 1
        return True, limit - count - 1
    
    @staticmethod
    def sync_codes_from_db(codes) -> bool:
        MockRedisService._codes_set = set(codes)
        return True
    
    @staticmethod
    def health_check() -> bool:
        return True


# Patch RedisService before importing other modules
@pytest.fixture(autouse=True)
def mock_redis():
    """Automatically mock Redis for all tests."""
    MockRedisService.reset()
    with patch("app.redis_client.RedisService", MockRedisService):
        with patch("app.services.RedisService", MockRedisService):
            with patch("app.routes.RedisService", MockRedisService):
                yield MockRedisService


@pytest.fixture(scope="function")
def test_db():
    """Create a test database using SQLite in-memory."""
    from app.database import Base
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db, mock_redis):
    """Create a FastAPI test client with mocked dependencies."""
    from app.main import app
    from app.database import get_db
    
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_url():
    """Sample URL for testing."""
    return "https://example.com/some/long/path?query=value"


@pytest.fixture
def sample_link_data(sample_url):
    """Sample link creation data."""
    return {
        "url": sample_url,
        "custom_code": None,
        "expires_in_days": 30
    }
