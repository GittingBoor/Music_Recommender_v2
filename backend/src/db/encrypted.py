"""A text column stored Fernet-encrypted, keyed from SESSION_SECRET (used for OAuth tokens)."""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from src.core.config import settings

logger = logging.getLogger(__name__)

_KEY_CONTEXT = b"music-recommender stored tokens"


def _fernet() -> Fernet:
    if not settings.session_secret:
        raise ValueError("SESSION_SECRET is empty; it is needed to encrypt stored Spotify tokens.")
    digest = hashlib.sha256(_KEY_CONTEXT + settings.session_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedText(TypeDecorator[str]):
    """Encrypts on write, decrypts on read. A value written under another secret reads as ""."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else _fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # SESSION_SECRET changed: the token is useless, Spotify asks for a reconnect.
            logger.warning("[DB] Stored token cannot be decrypted (SESSION_SECRET changed?)")
            return ""
