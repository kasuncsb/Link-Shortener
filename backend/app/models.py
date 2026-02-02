from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, BigInteger, Index
from sqlalchemy.sql import func
from .database import Base


class Link(Base):
    """Model for storing shortened links."""
    
    __tablename__ = "links"
    
    # Use Integer for primary key so SQLite ``AUTOINCREMENT`` works predictably
    id = Column(Integer, primary_key=True, autoincrement=True)
    suffix = Column(String(64), unique=True, nullable=False, index=True)
    destination = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.utc_timestamp())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length is 45 chars
    
    # Password protection
    password_hash = Column(String(64), nullable=True)
    
    # One-time/click-limited links
    max_clicks = Column(Integer, nullable=True)  # None = unlimited
    click_count = Column(Integer, default=0, nullable=False)
    
    # OpenGraph preview data
    og_title = Column(String(255), nullable=True)
    og_description = Column(Text, nullable=True)
    og_image = Column(String(500), nullable=True)
    
    __table_args__ = (
        Index('idx_suffix', 'suffix'),
        Index('idx_expires_at', 'expires_at'),
        Index('idx_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Link(suffix={self.suffix}, destination={self.destination[:50]}...)>"


class ApiKey(Base):
    """Model for storing API keys for optional authentication."""
    
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)  # Optional friendly name
    created_at = Column(DateTime(timezone=True), server_default=func.utc_timestamp())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    rate_limit = Column(Integer, default=1000)  # Requests per hour
    is_active = Column(Boolean, default=True, nullable=False)
    
    __table_args__ = (
        Index('idx_key_hash', 'key_hash'),
    )
    
    def __repr__(self):
        return f"<ApiKey(name={self.name}, active={self.is_active})>"
