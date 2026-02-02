"""
Logging configuration for the Link Shortener application.
Provides structured JSON logging with request IDs for tracing.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from .env import get_bool

# Context variable for request ID tracking
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set a request ID in context. Generates one if not provided."""
    rid = request_id or str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    return rid


class RequestIdFilter(logging.Filter):
    """Logging filter that adds request_id to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def setup_logging() -> None:
    """Configure application logging with structured format."""
    debug_mode = False
    try:
        debug_mode = get_bool("DEBUG")
    except RuntimeError:
        pass
    
    log_level = logging.DEBUG if debug_mode else logging.INFO
    
    # Format: timestamp - level - request_id - logger - message
    log_format = "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    console_handler.addFilter(RequestIdFilter())
    
    root_logger.addHandler(console_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the application configuration."""
    return logging.getLogger(name)
