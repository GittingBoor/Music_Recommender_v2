"""Personal accounts: register, log in, reset a forgotten password.

Independent of the shared site password (routes/auth.py), which still guards
the whole site. An account is only needed for the Spotify connection.
"""
import logging
from datetime import datetime, timezone
from functools import cache

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.accounts.mailer import Mailer, MailDeliveryError, get_mailer
from src.accounts.reset import RESET_TOKEN_LIFETIME, hash_reset_token, new_reset_token
from src.accounts.validation import is_valid_email, normalise_email
from src.api.deps import get_db
from src.api.user import clear_user_cookie, ensure_accounts_configured, require_user, set_user_cookie
from src.auth.password import hash_password, verify_password
from src.core.config import settings
from src.db.models import PasswordResetToken, SpotifyConnection, User

logger = logging.getLogger(__name__)
router = APIRouter()

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 256
_MAX_TOKEN_LENGTH = 128


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=_MAX_PASSWORD_LENGTH)


class NewAccount(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=_MAX_PASSWORD_LENGTH)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=320)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=_MAX_TOKEN_LENGTH)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=_MAX_PASSWORD_LENGTH)


class SpotifyStatusOut(BaseModel):
    spotify_user_id: str
    display_name: str | None


class AccountOut(BaseModel):
    email: str
    spotify: SpotifyStatusOut | None


def _as_utc(moment: datetime) -> datetime:
    # SQLite (tests) hands back naive datetimes; Postgres aware ones.
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def account_out(user: User, db: Session) -> AccountOut:
    connection = db.get(SpotifyConnection, user.id)
    spotify = (
        SpotifyStatusOut(spotify_user_id=connection.spotify_user_id, display_name=connection.display_name)
        if connection else None
    )
    return AccountOut(email=user.email, spotify=spotify)


@cache
def _dummy_hash() -> str:
    """Checked against for unknown addresses, so login takes as long as for real ones."""
    return hash_password("no account has this password")


def _find_user(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalise_email(email)).first()


@router.post("/account/register", response_model=AccountOut, status_code=201)
def register(body: NewAccount, response: Response, db: Session = Depends(get_db)) -> AccountOut:
    ensure_accounts_configured()
    email = normalise_email(body.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="Bitte eine gültige E-Mail-Adresse eingeben.")
    if _find_user(db, email) is not None:
        raise HTTPException(status_code=409, detail="Zu dieser E-Mail gibt es schon einen Account.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # A parallel request registered the same address first.
        db.rollback()
        raise HTTPException(status_code=409, detail="Zu dieser E-Mail gibt es schon einen Account.")
    db.refresh(user)
    logger.info("[Account] Registered user %d", user.id)
    set_user_cookie(response, user)
    return account_out(user, db)


@router.post("/account/login", response_model=AccountOut)
def login(body: Credentials, response: Response, db: Session = Depends(get_db)) -> AccountOut:
    ensure_accounts_configured()
    user = _find_user(db, body.email)
    stored = user.password_hash if user is not None else _dummy_hash()
    if not verify_password(body.password, stored) or user is None:
        raise HTTPException(status_code=401, detail="E-Mail oder Passwort falsch.")
    set_user_cookie(response, user)
    return account_out(user, db)


@router.post("/account/logout", status_code=204)
def logout() -> Response:
    response = Response(status_code=204)
    clear_user_cookie(response)
    return response


@router.get("/account/me", response_model=AccountOut)
def me(user: User = Depends(require_user), db: Session = Depends(get_db)) -> AccountOut:
    return account_out(user, db)


@router.post("/account/forgot-password", status_code=204)
def forgot_password(
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
) -> Response:
    """Mail a reset link. Always 204, so the answer does not reveal which addresses exist.

    The mail goes out after the response, so a known address is not given away
    by the seconds the mail provider takes either.
    """
    user = _find_user(db, body.email)
    if user is not None:
        token, digest = new_reset_token()
        db.add(PasswordResetToken(
            token_hash=digest, user_id=user.id,
            expires_at=datetime.now(timezone.utc) + RESET_TOKEN_LIFETIME,
        ))
        db.commit()
        link = f"{settings.public_base_url.rstrip('/')}/reset-password/{token}"
        background.add_task(_send_reset_mail, mailer, user.id, user.email, link)
    return Response(status_code=204)


def _send_reset_mail(mailer: Mailer, user_id: int, email: str, link: str) -> None:
    try:
        mailer.send(email, "Passwort zurücksetzen – Music Recommender", _reset_mail_text(link))
    except MailDeliveryError as exc:
        logger.error("[Account] Reset mail to user %d failed: %s", user_id, exc)


def _reset_mail_text(link: str) -> str:
    return (
        "Hallo,\n\n"
        "für deinen Music-Recommender-Account wurde ein neues Passwort angefordert.\n"
        f"Über diesen Link kannst du es innerhalb einer Stunde festlegen:\n\n{link}\n\n"
        "Wenn du das nicht warst, ignoriere diese Mail einfach – dein Passwort bleibt dann unverändert.\n"
    )


@router.post("/account/reset-password", status_code=204)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)) -> Response:
    now = datetime.now(timezone.utc)
    row = db.get(PasswordResetToken, hash_reset_token(body.token))
    if row is None or row.used_at is not None or _as_utc(row.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Der Link ist ungültig oder abgelaufen. Fordere einen neuen an.")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Der Link ist ungültig oder abgelaufen. Fordere einen neuen an.")
    user.password_hash = hash_password(body.password)
    # Every open link of this user dies with the reset, not only the one used.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now})
    db.commit()
    logger.info("[Account] Password reset for user %d", user.id)
    response = Response(status_code=204)
    set_user_cookie(response, user)
    return response

