from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base


class LoginEvent(Base):
    """
    One attempt at the site password (successful or not).

    Written by POST /api/auth/login. device_id comes from the long-lived
    ``mr_device`` cookie, so repeated logins from the same browser share it.
    """
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45))
    country: Mapped[str | None] = mapped_column(String(2))
    user_agent: Mapped[str | None] = mapped_column(Text)
    device_id: Mapped[str | None] = mapped_column(String(32), index=True)
