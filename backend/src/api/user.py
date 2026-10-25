"""Who is logged in with a personal account (cookie ``mr_user``), as FastAPI dependencies."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from src.accounts.session import UserSessionSigner
from src.api.deps import get_db
from src.core.config import settings
from src.db.models import User

USER_COOKIE = "mr_user"


def _signer() -> UserSessionSigner:
    if not settings.session_secret:
        raise HTTPException(
            status_code=503,
            detail="Accounts are not configured: set SESSION_SECRET in the backend .env.",
        )
    # Own key, so a site-password token can never pass as a user token.
    key = hmac.new(settings.session_secret.encode(), b"user-accounts", hashlib.sha256).digest()
    return UserSessionSigner(key, timedelta(days=settings.user_session_days))


def ensure_accounts_configured() -> None:
    """Raise 503 when SESSION_SECRET is missing (no account could stay logged in)."""
    _signer()


def set_user_cookie(response: Response, user: User) -> None:
    token = _signer().issue(user.id, user.password_hash, datetime.now(timezone.utc))
    response.set_cookie(
        USER_COOKIE, token, max_age=settings.user_session_days * 24 * 3600,
        httponly=True, secure=settings.session_cookie_secure, samesite="lax",
    )


def clear_user_cookie(response: Response) -> None:
    response.delete_cookie(USER_COOKIE, httponly=True, secure=settings.session_cookie_secure, samesite="lax")


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """The logged-in user, or None (no cookie, expired, or password changed since)."""
    token = request.cookies.get(USER_COOKIE, "")
    if not token or not settings.session_secret:
        return None
    found: dict[int, User] = {}

    def password_hash_of(user_id: int) -> str | None:
        user = db.get(User, user_id)
        if user is None:
            return None
        found[user_id] = user
        return user.password_hash

    user_id = _signer().user_id(token, password_hash_of, datetime.now(timezone.utc))
    return found.get(user_id) if user_id is not None else None


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user
