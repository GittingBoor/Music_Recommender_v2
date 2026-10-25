"""Outgoing mail (password reset links) via Brevo's transactional API.

Without ``BREVO_API_KEY`` and ``MAIL_FROM`` (local development) mails are only
written to the log, so the reset flow can still be tried out.
"""
import json
import logging
import urllib.error
import urllib.request
from typing import Protocol

from src.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT_SECONDS = 10


class MailDeliveryError(Exception):
    """The mail provider refused or could not be reached."""


class Mailer(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class BrevoMailer:
    """Sends plain-text mails through Brevo (https://developers.brevo.com/reference/sendtransacemail)."""

    def __init__(self, api_key: str, sender: str, sender_name: str) -> None:
        self._api_key = api_key
        self._sender = sender
        self._sender_name = sender_name

    def send(self, to: str, subject: str, text: str) -> None:
        payload = {
            "sender": {"email": self._sender, "name": self._sender_name},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": text,
        }
        req = urllib.request.Request(
            _BREVO_URL,
            data=json.dumps(payload).encode(),
            headers={"api-key": self._api_key, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise MailDeliveryError(f"Brevo answered HTTP {exc.code}; check BREVO_API_KEY and MAIL_FROM") from exc
        except OSError as exc:
            raise MailDeliveryError(f"Brevo not reachable: {exc}") from exc


class LogMailer:
    """Development stand-in: writes the mail to the log instead of sending it."""

    def send(self, to: str, subject: str, text: str) -> None:
        logger.warning("[Mail] BREVO_API_KEY/MAIL_FROM not set — not sent to %s: %s\n%s", to, subject, text)


def get_mailer() -> Mailer:
    if settings.brevo_api_key and settings.mail_from:
        return BrevoMailer(settings.brevo_api_key, settings.mail_from, settings.mail_from_name)
    return LogMailer()
