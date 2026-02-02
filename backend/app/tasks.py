"""
Background tasks for cleanup and maintenance.
Includes expired link cleanup and Redis synchronization.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .database import get_db, engine, Base
from .models import Link
from .redis_client import RedisService
from .services import LinkService
from .env import get_int_optional, get_bool_optional
from .logging_config import get_logger
from .utils import utc_now

logger = get_logger(__name__)


async def cleanup_expired_links():
    """
    Background task to clean up expired links from Redis.
    This keeps Redis in sync with database expiry.
    """
    db = next(get_db())
    try:
        count = LinkService.cleanup_expired_links(db)
        if count > 0:
            logger.info(f"Cleanup task removed {count} expired links from Redis")
    except Exception as e:
        logger.error(f"Error in cleanup_expired_links: {e}")
    finally:
        db.close()


async def sync_redis_codes():
    """
    Sync Redis CODES_SET with database to fix any inconsistencies.
    This helps address the Redis memory leak issue.
    """
    db = next(get_db())
    try:
        # Get all codes from database
        links = db.query(Link.suffix).all()
        codes = [link.suffix for link in links if link.suffix]
        
        # Sync with Redis
        if RedisService.sync_codes_from_db(codes):
            logger.info(f"Synced {len(codes)} codes to Redis CODES_SET")
    except Exception as e:
        logger.error(f"Error in sync_redis_codes: {e}")
    finally:
        db.close()


async def delete_expired_links_from_db():
    """
    Delete expired links from database if configured to do so.
    By default, we keep expired links to preserve suffix reservations.
    """
    if not get_bool_optional("DELETE_EXPIRED_LINKS", False):
        return
    
    db = next(get_db())
    try:
        now = utc_now()
        expired = db.query(Link).filter(
            Link.expires_at != None,
            Link.expires_at < now
        ).all()
        
        count = 0
        for link in expired:
            suffix = link.suffix
            db.delete(link)
            RedisService.delete_cached_link(suffix)
            RedisService.remove_code_from_set(suffix)
            count += 1
        
        if count > 0:
            db.commit()
            logger.info(f"Deleted {count} expired links from database")
    except Exception as e:
        logger.error(f"Error deleting expired links: {e}")
        db.rollback()
    finally:
        db.close()


class BackgroundTaskRunner:
    """Manages background cleanup tasks."""
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def _run_loop(self):
        """Main background task loop."""
        interval_hours = get_int_optional("CLEANUP_INTERVAL_HOURS", 1)
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Starting background cleanup tasks (interval: {interval_hours}h)")
        
        while self._running:
            try:
                # Run cleanup tasks
                await cleanup_expired_links()
                await sync_redis_codes()
                await delete_expired_links_from_db()
                
            except Exception as e:
                logger.error(f"Error in background task loop: {e}")
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
    
    def start(self):
        """Start the background task runner."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Background task runner started")
    
    def stop(self):
        """Stop the background task runner."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Background task runner stopped")


# Global task runner instance
task_runner = BackgroundTaskRunner()
