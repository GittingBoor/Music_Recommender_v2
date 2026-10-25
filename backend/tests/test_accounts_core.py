import json
from datetime import datetime, timedelta, timezone

import pytest

from src.accounts import mailer as mailer_module
from src.accounts.mailer import BrevoMailer, MailDeliveryError
from src.accounts.reset import hash_reset_token, new_reset_token
from src.accounts.session import UserSessionSigner
from src.accounts.validation import is_valid_email, normalise_email

_NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
_HASH = "scrypt:32768:8:1:aa:bb"


def _signer() -> UserSessionSigner:
    return UserSessionSigner(b"secret", timedelta(days=90))


# --- user session tokens ----------------------------------------------------

def test_user_token_roundtrip() -> None:
    token = _signer().issue(42, _HASH, _NOW)
    assert _signer().user_id(token, lambda uid: _HASH if uid == 42 else None, _NOW) == 42


def test_user_token_invalid_after_password_change() -> None:
    token = _signer().issue(42, _HASH, _NOW)
    assert _signer().user_id(token, lambda uid: "scrypt:new", _NOW) is None


def test_user_token_expires() -> None:
    token = _signer().issue(42, _HASH, _NOW)
    assert _signer().user_id(token, lambda uid: _HASH, _NOW + timedelta(days=91)) is None


def test_user_token_rejects_unknown_user_and_garbage() -> None:
    token = _signer().issue(42, _HASH, _NOW)
    assert _signer().user_id(token, lambda uid: None, _NOW) is None
    assert _signer().user_id("garbage", lambda uid: _HASH, _NOW) is None
    assert _signer().user_id("x.y.z", lambda uid: _HASH, _NOW) is None


def test_user_token_rejects_other_user_id() -> None:
    token = _signer().issue(42, _HASH, _NOW)
    forged = "43" + token[2:]
    assert _signer().user_id(forged, lambda uid: _HASH, _NOW) is None


# --- reset tokens -----------------------------------------------------------

def test_reset_token_hash_matches() -> None:
    plain, digest = new_reset_token()
    assert len(plain) >= 32
    assert hash_reset_token(plain) == digest
    assert new_reset_token()[0] != plain


# --- e-mail -----------------------------------------------------------------

def test_email_is_normalised() -> None:
    assert normalise_email("  Foo@Bar.DE ") == "foo@bar.de"


@pytest.mark.parametrize("email, valid", [
    ("foo@bar.de", True),
    ("a.b+c@sub.example.com", True),
    ("foo", False),
    ("foo@bar", False),
    ("@bar.de", False),
    ("foo@@bar.de", False),
    ("foo bar@baz.de", False),
    ("x" * 250 + "@a.de", False),
])
def test_email_validation(email: str, valid: bool) -> None:
    assert is_valid_email(email) is valid


class _FakeResponse:
    status = 201

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return b'{"messageId": "1"}'


def test_brevo_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list = []

    def fake_urlopen(req, timeout):  # noqa: ANN001
        sent.append(req)
        return _FakeResponse()

    monkeypatch.setattr(mailer_module.urllib.request, "urlopen", fake_urlopen)
    BrevoMailer("key-123", "noreply@example.com", "Music Recommender").send("to@example.com", "Betreff", "Text")

    req = sent[0]
    assert req.full_url == "https://api.brevo.com/v3/smtp/email"
    assert req.get_header("Api-key") == "key-123"
    body = json.loads(req.data)
    assert body["sender"] == {"email": "noreply@example.com", "name": "Music Recommender"}
    assert body["to"] == [{"email": "to@example.com"}]
    assert body["subject"] == "Betreff"
    assert body["textContent"] == "Text"


def test_brevo_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout):  # noqa: ANN001
        raise mailer_module.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(mailer_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(MailDeliveryError, match="401"):
        BrevoMailer("bad", "noreply@example.com", "MR").send("to@example.com", "S", "T")
