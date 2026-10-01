"""
MongoDB connection for document store (AI history, audit logs, delivery logs).
Supports local MongoDB and MongoDB Atlas (mongodb+srv://...).
Includes lazy connection, connection caching, and graceful circuit breaker fallback.
"""
import logging
try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

from core.config import settings

logger = logging.getLogger("db.mongo")

_client = None
_db = None
_last_failure_time = 0.0
_COOLDOWN_SECONDS = 60.0  # Avoid blocking request threads if Mongo is offline


def get_mongo_db():
    """Get MongoDB database instance with lazy connection and circuit breaker."""
    global _client, _db, _last_failure_time
    if MongoClient is None:
        return None
    if _db is not None:
        return _db

    now = time.time()
    # If connection previously failed, wait for cooldown before retrying
    if now - _last_failure_time < _COOLDOWN_SECONDS:
        return None

    try:
        _client = MongoClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=1500,
            connectTimeoutMS=1500,
        )
        # Ping to verify
        _client.admin.command("ping")
        _db = _client[settings.MONGO_DB_NAME]
        logger.info("Connected to MongoDB successfully.")
        return _db
    except Exception as e:
        _last_failure_time = now
        logger.warning(f"MongoDB not available ({e}). Document logging will be skipped. Retrying in {_COOLDOWN_SECONDS}s.")
        return None


def log_mongo_document(collection_name: str, document: dict):
    """Safely log a document to MongoDB without throwing errors or blocking if Mongo is down."""
    try:
        db = get_mongo_db()
        if db is not None:
            db[collection_name].insert_one(document)
    except Exception as e:
        logger.debug(f"Failed to log to MongoDB collection {collection_name}: {e}")

