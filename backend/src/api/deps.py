"""Shared FastAPI dependencies for all route modules."""
from collections.abc import Generator

from sqlalchemy.orm import Session

from src.db.session import get_session


def get_db() -> Generator[Session, None, None]:
    """Yield a database session that is closed after the request."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()
