"""Re-export database utilities from core for backward compatibility."""

from app.core.database import (
    Base,
    SessionLocal,
    engine,
    get_db,
    _normalize_database_url,
)

__all__ = ["Base", "SessionLocal", "engine", "get_db", "_normalize_database_url"]
