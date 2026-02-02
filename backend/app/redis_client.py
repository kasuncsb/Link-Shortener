import redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from typing import Optional, Any, cast
from datetime import datetime, timezone
from .env import get_env, get_int
from .logging_config import get_logger

logger = get_logger(__name__)

# Redis is required in production; always enable the client
USE_REDIS = True

# Redis connection pool
try:
    pool = redis.ConnectionPool(
        host=get_env("REDIS_HOST"),
        port=get_int("REDIS_PORT"),
        db=get_int("REDIS_DB"),
        password=get_env("REDIS_PASSWORD") or None,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    redis_client = redis.Redis(connection_pool=pool)
except RedisError as e:
    logger.error(f"Failed to create Redis connection pool: {e}")
    raise 


class RedisService:
    """Redis service for caching and rate limiting."""
    
    LINK_CACHE_PREFIX = "link:"
    CODES_SET = "codes:used"
    RATE_LIMIT_PREFIX = "ratelimit:ip:"
    
    CACHE_TTL = 86400  # 24 hours
    RATE_LIMIT_TTL = 3600  # 1 hour
    
    @staticmethod
    def cache_link(code: str, url: str, expires_at: Optional[datetime] = None) -> bool:
        """Cache a short code to URL mapping."""
        if not USE_REDIS:
            return False
        try:
            # Store as a hash; TTL on the key enforces expiry
            key = f"{RedisService.LINK_CACHE_PREFIX}{code}"
            mapping: dict[str, str] = {"url": url}
            redis_client.hset(key, mapping=mapping)
            
            # Set TTL on the hash to match DB expiry if provided
            if expires_at:
                now = datetime.now(timezone.utc)
                # Normalize naive datetime
                if getattr(expires_at, "tzinfo", None) is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                delta = (expires_at - now).total_seconds()
                if delta > 0:
                    ttl = int(min(delta, RedisService.CACHE_TTL))
                    redis_client.expire(key, ttl)
                else:
                    # Already expired: don't cache
                    redis_client.delete(key)
                    return False
            else:
                # No DB expiry -> keep persistent in Redis
                redis_client.persist(key)
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection error caching link {code}: {e}")
            return False
        except RedisError as e:
            logger.error(f"Redis error caching link {code}: {e}")
            return False
    
    @staticmethod
    def get_cached_link(code: str) -> Optional[str]:
        """Get cached URL for a short code."""
        if not USE_REDIS:
            return None
        try:
            key = f"{RedisService.LINK_CACHE_PREFIX}{code}"
            data = cast(dict[str, str], redis_client.hgetall(key))
            if not data:
                return None
            url = data.get("url")
            return cast(Optional[str], url)
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection error getting link {code}: {e}")
            return None
        except RedisError as e:
            logger.error(f"Redis error getting link {code}: {e}")
            return None
    
    @staticmethod
    def delete_cached_link(code: str) -> bool:
        """Delete cached link."""
        if not USE_REDIS:
            return False
        try:
            redis_client.delete(f"{RedisService.LINK_CACHE_PREFIX}{code}")
            return True
        except RedisError as e:
            logger.error(f"Redis error deleting link {code}: {e}")
            return False
    
    @staticmethod
    def add_code_to_set(code: str) -> bool:
        """Add a code to the set of used codes."""
        if not USE_REDIS:
            return True
        try:
            redis_client.sadd(RedisService.CODES_SET, code)
            return True
        except RedisError as e:
            logger.error(f"Redis error adding code to set {code}: {e}")
            return False
    
    @staticmethod
    def code_exists(code: str) -> bool:
        """Check if a code exists in the set."""
        if not USE_REDIS:
            return False
        try:
            return bool(redis_client.sismember(RedisService.CODES_SET, code))
        except RedisError as e:
            logger.warning(f"Redis error checking code existence {code}: {e}")
            return False
    
    @staticmethod
    def remove_code_from_set(code: str) -> bool:
        """Remove a code from the set."""
        if not USE_REDIS:
            return True
        try:
            redis_client.srem(RedisService.CODES_SET, code)
            return True
        except RedisError as e:
            logger.error(f"Redis error removing code from set {code}: {e}")
            return False
    
    @staticmethod
    def check_rate_limit(ip: str, limit: Optional[int] = None) -> tuple[bool, int]:
        """
        Check and increment rate limit for an IP.
        Returns (is_allowed, remaining_requests).
        """
        if limit is None:
            limit = get_int("RATE_LIMIT_PER_HOUR")

        if not USE_REDIS:
            return True, limit - 1
        
        key = f"{RedisService.RATE_LIMIT_PREFIX}{ip}"
        
        try:
            current_val = redis_client.get(key)
            
            if current_val is None:
                redis_client.setex(key, RedisService.RATE_LIMIT_TTL, 1)
                return True, limit - 1
            
            current = int(str(current_val))
            
            if current >= limit:
                return False, 0
            
            redis_client.incr(key)
            return True, limit - current - 1
            
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection error in rate limit check for {ip}: {e}")
            return True, limit
        except RedisError as e:
            logger.error(f"Redis error in rate limit check for {ip}: {e}")
            return True, limit
        except ValueError as e:
            logger.error(f"Invalid rate limit value for {ip}: {e}")
            return True, limit
    

    
    @staticmethod
    def sync_codes_from_db(codes: list) -> bool:
        """Sync all codes from database to Redis set."""
        if not USE_REDIS:
            return True
        try:
            if codes:
                redis_client.delete(RedisService.CODES_SET)
                redis_client.sadd(RedisService.CODES_SET, *codes)
            return True
        except RedisError as e:
            logger.error(f"Redis error syncing codes from DB: {e}")
            return False
    
    @staticmethod
    def health_check() -> bool:
        """Check Redis connection health."""
        if not USE_REDIS:
            return True
        try:
            return bool(redis_client.ping())
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis health check failed (connection): {e}")
            return False
        except RedisError as e:
            logger.error(f"Redis health check failed: {e}")
            return False
