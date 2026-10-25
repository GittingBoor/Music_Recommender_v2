"""Password reset tokens: the link carries the token, the database only its sha256."""
import hashlib
import secrets
from datetime import timedelta

RESET_TOKEN_LIFETIME = timedelta(hours=1)
_TOKEN_BYTES = 32


def hash_reset_token(token: str) -> str:
    """sha256 hex of a reset token, as stored in ``password_reset_tokens``."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_reset_token() -> tuple[str, str]:
    """A fresh ``(token for the link, hash for the database)`` pair."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    return token, hash_reset_token(token)
