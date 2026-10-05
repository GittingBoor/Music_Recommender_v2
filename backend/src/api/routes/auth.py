"""Site login with one shared password (no user accounts).

nginx asks GET /auth/check (via auth_request) before serving anything; the
login page posts to /auth/login. Every attempt lands in ``login_events``.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.auth.password import verify_password
from src.auth.session import SessionSigner
from src.core.config import settings
from src.db.models.login_event import LoginEvent

logger = logging.getLogger(__name__)

router = APIRouter()

SESSION_COOKIE = "mr_session"
DEVICE_COOKIE = "mr_device"
_DEVICE_COOKIE_MAX_AGE = 2 * 365 * 24 * 3600
_MAX_PASSWORD_LENGTH = 256
_MAX_USER_AGENT_LENGTH = 512


class LoginRequest(BaseModel):
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)


def _is_configured() -> bool:
    return bool(settings.site_password_hash and settings.session_secret)


def _signer() -> SessionSigner:
    # The key depends on the password hash, so a new password logs everyone out.
    key = hmac.new(
        settings.session_secret.encode(),
        settings.site_password_hash.encode(),
        hashlib.sha256,
    ).digest()
    return SessionSigner(key, timedelta(days=settings.session_days))


def _client_ip(request: Request) -> str | None:
    # cloudflared sets CF-Connecting-IP; the nginx in front only adds X-Real-IP
    # (= the cloudflared container), so that is just the fallback.
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else None)
    )


def _device_id(request: Request) -> str:
    existing = request.cookies.get(DEVICE_COOKIE, "")
    if len(existing) == 32 and all(c in "0123456789abcdef" for c in existing):
        return existing
    return secrets.token_hex(16)


@router.get("/auth/check", status_code=204)
async def check(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE, "")
    if _is_configured() and token and _signer().is_valid(token, datetime.now(timezone.utc)):
        return Response(status_code=204)
    return Response(status_code=401)


@router.post("/auth/login", status_code=204)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Response:
    if not _is_configured():
        raise HTTPException(
            status_code=503,
            detail="Login is not configured: set SITE_PASSWORD_HASH and SESSION_SECRET in .env.prod.",
        )
    success = verify_password(body.password, settings.site_password_hash)
    device_id = _device_id(request)
    db.add(LoginEvent(
        success=success,
        ip=_client_ip(request),
        country=request.headers.get("cf-ipcountry"),
        user_agent=(request.headers.get("user-agent") or "")[:_MAX_USER_AGENT_LENGTH] or None,
        device_id=device_id,
    ))
    db.commit()
    logger.info("Login %s from %s (device %s)", "ok" if success else "failed", _client_ip(request), device_id)

    response = Response(status_code=204 if success else 401)
    response.set_cookie(
        DEVICE_COOKIE, device_id, max_age=_DEVICE_COOKIE_MAX_AGE,
        httponly=True, secure=settings.session_cookie_secure, samesite="lax",
    )
    if success:
        response.set_cookie(
            SESSION_COOKIE, _signer().issue(datetime.now(timezone.utc)),
            max_age=settings.session_days * 24 * 3600,
            httponly=True, secure=settings.session_cookie_secure, samesite="lax",
        )
    return response


@router.post("/auth/logout", status_code=204)
def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=settings.session_cookie_secure, samesite="lax")
    return response
