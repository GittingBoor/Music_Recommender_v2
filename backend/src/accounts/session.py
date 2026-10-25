"""Signed login tokens for personal accounts: ``<user_id>.<expiry unix>.<hmac>``."""
import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime, timedelta


class UserSessionSigner:
    """Issues and checks expiring login tokens bound to the user's password hash.

    The HMAC key is derived from the stored password hash, so changing the
    password (e.g. via a reset link) invalidates every older token.
    """

    def __init__(self, secret: bytes, lifetime: timedelta) -> None:
        self._secret = secret
        self._lifetime = lifetime

    def _sign(self, user_id: int, expires: int, password_hash: str) -> str:
        key = hmac.new(self._secret, password_hash.encode(), hashlib.sha256).digest()
        return hmac.new(key, f"{user_id}.{expires}".encode(), hashlib.sha256).hexdigest()

    def issue(self, user_id: int, password_hash: str, now: datetime) -> str:
        """Return a token for ``user_id`` that is valid until ``now + lifetime``."""
        expires = int((now + self._lifetime).timestamp())
        return f"{user_id}.{expires}.{self._sign(user_id, expires, password_hash)}"

    def user_id(self, token: str, password_hash_of: Callable[[int], str | None], now: datetime) -> int | None:
        """The user the token belongs to, or None if it is forged, expired or outdated."""
        parts = token.split(".")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        user_id, expires = int(parts[0]), int(parts[1])
        if now.timestamp() >= expires:
            return None
        password_hash = password_hash_of(user_id)
        if password_hash is None:
            return None
        if not hmac.compare_digest(self._sign(user_id, expires, password_hash), parts[2]):
            return None
        return user_id
