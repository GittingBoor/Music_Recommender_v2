"""Stateless session tokens: ``<expiry unix>.<hmac>``."""
import hashlib
import hmac
from datetime import datetime, timedelta


class SessionSigner:
    """Issues and checks expiring, HMAC-signed session tokens."""

    def __init__(self, key: bytes, lifetime: timedelta) -> None:
        self._key = key
        self._lifetime = lifetime

    def _sign(self, expires: int) -> str:
        return hmac.new(self._key, str(expires).encode(), hashlib.sha256).hexdigest()

    def issue(self, now: datetime) -> str:
        """Return a token that is valid until ``now + lifetime``."""
        expires = int((now + self._lifetime).timestamp())
        return f"{expires}.{self._sign(expires)}"

    def is_valid(self, token: str, now: datetime) -> bool:
        """True if ``token`` was signed with this key and has not expired."""
        expires_raw, _, signature = token.partition(".")
        if not expires_raw.isdigit():
            return False
        expires = int(expires_raw)
        if not hmac.compare_digest(self._sign(expires), signature):
            return False
        return now.timestamp() < expires
