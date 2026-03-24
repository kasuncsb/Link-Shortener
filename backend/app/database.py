from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .env import get_env, get_int

DATABASE_URL = (
    f"mysql+pymysql://{get_env('MYSQL_USER')}:{get_env('MYSQL_PASSWORD')}"
    f"@{get_env('MYSQL_HOST')}:{get_int('MYSQL_PORT')}/{get_env('MYSQL_DATABASE')}"
)
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "init_command": "SET time_zone = '+00:00'",
        "connect_timeout": 3,
        "read_timeout": 5,
        "write_timeout": 5,
    },
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=5,
    pool_size=10,
    max_overflow=20
) 

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
