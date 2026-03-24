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
    ip_address = Column(String(255), nullable=True)
    
    __table_args__ = (
        Index('idx_suffix', 'suffix'),
        Index('idx_expires_at', 'expires_at'),
        Index('idx_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Link(suffix={self.suffix}, destination={self.destination[:50]}...)>"



