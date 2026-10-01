"""
Database session management with PostgreSQL primary and SQLite resilient fallback.
"""
import os
from pathlib import Path
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import settings

logger = logging.getLogger("db.session")

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = (BASE_DIR / "academics_insights.db").as_posix()
database_url = settings.DATABASE_URL

# Check if PostgreSQL is specified
if "postgresql" in database_url:
    try:
        # Test connection briefly
        test_engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3}
        )
        with test_engine.connect() as conn:
            logger.info("Connected to PostgreSQL successfully.")
        engine = test_engine
    except Exception as e:
        logger.warning(
            f"PostgreSQL at {database_url} unavailable ({e}). "
            f"Falling back to local SQLite 'sqlite:///{SQLITE_PATH}' for seamless development."
        )
        engine = create_engine(
            f"sqlite:///{SQLITE_PATH}",
            connect_args={"check_same_thread": False},
        )
else:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )

from sqlalchemy import event

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Ensure SQLite enables foreign keys
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in str(engine.url):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()



def get_db():
    """FastAPI dependency for DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
