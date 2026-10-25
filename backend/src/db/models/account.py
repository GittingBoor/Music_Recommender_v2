from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.encrypted import EncryptedText
from src.db.models.base import Base


class User(Base):
    """
    A personal account (optional; the site itself only needs the shared password).

    Written by /api/account/register. email is stored lower-cased, so it is
    the unique login name; password_hash uses the scrypt format of src.auth.password.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(Base):
    """
    A single-use password reset link. Only the sha256 of the token is stored,
    so a leaked table does not hand out working links.
    """
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpotifyConnection(Base):
    """
    A user's linked Spotify account (OAuth tokens). One per user.

    The refresh token stays valid until the user revokes the app on Spotify;
    the access token is renewed from it about once an hour. Both are stored
    encrypted (src.db.encrypted).
    """
    __tablename__ = "spotify_connections"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    spotify_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    refresh_token: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
