from collections.abc import Generator, Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import user as user_deps
from src.api.deps import get_db
from src.api.routes import account as account_route
from src.core.config import settings
from src.db.models import Base, PasswordResetToken, SpotifyConnection, User

_PASSWORD = "geheim-genug-123"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))


def account_tables() -> list:
    return [User.__table__, PasswordResetToken.__table__, SpotifyConnection.__table__]


@pytest.fixture
def db_factory() -> Iterator[sessionmaker]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=account_tables())
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def client(db_factory: sessionmaker, mailer: FakeMailer, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "session_secret", "test-secret")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "public_base_url", "https://music.example.de")

    def override_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(account_route.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[account_route.get_mailer] = lambda: mailer
    return TestClient(app)


def _register(client: TestClient, email: str = "Benni@Example.de") -> None:
    resp = client.post("/api/account/register", json={"email": email, "password": _PASSWORD})
    assert resp.status_code == 201, resp.text


def _reset_token_from_mail(mailer: FakeMailer) -> str:
    text = mailer.sent[-1][2]
    marker = "https://music.example.de/reset-password/"
    start = text.index(marker) + len(marker)
    return text[start:].split()[0]


def test_register_then_me(client: TestClient) -> None:
    _register(client)
    resp = client.get("/api/account/me")
    assert resp.status_code == 200
    assert resp.json() == {"email": "benni@example.de", "spotify": None}


def test_me_without_login_401(client: TestClient) -> None:
    assert client.get("/api/account/me").status_code == 401


def test_register_duplicate_email_409(client: TestClient) -> None:
    _register(client)
    resp = client.post("/api/account/register", json={"email": " benni@example.DE", "password": _PASSWORD})
    assert resp.status_code == 409


def test_register_rejects_bad_email_and_short_password(client: TestClient) -> None:
    assert client.post("/api/account/register", json={"email": "kaputt", "password": _PASSWORD}).status_code == 422
    assert client.post("/api/account/register", json={"email": "a@b.de", "password": "kurz"}).status_code == 422


def test_login_with_other_case_email(client: TestClient) -> None:
    _register(client)
    client.post("/api/account/logout")
    assert client.get("/api/account/me").status_code == 401
    resp = client.post("/api/account/login", json={"email": "BENNI@example.de ", "password": _PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["email"] == "benni@example.de"
    assert client.get("/api/account/me").status_code == 200


def test_login_wrong_password_401(client: TestClient) -> None:
    _register(client)
    client.post("/api/account/logout")
    resp = client.post("/api/account/login", json={"email": "benni@example.de", "password": "falsch-falsch"})
    assert resp.status_code == 401
    assert client.post("/api/account/login", json={"email": "nobody@x.de", "password": _PASSWORD}).status_code == 401


def test_forgot_unknown_email_still_204_no_mail(client: TestClient, mailer: FakeMailer) -> None:
    resp = client.post("/api/account/forgot-password", json={"email": "nobody@example.de"})
    assert resp.status_code == 204
    assert mailer.sent == []


def test_reset_flow_changes_password_and_invalidates_old_cookie(client: TestClient, mailer: FakeMailer) -> None:
    _register(client)
    old_cookie = client.cookies.get(user_deps.USER_COOKIE)
    assert client.post("/api/account/forgot-password", json={"email": "BENNI@example.de"}).status_code == 204
    assert mailer.sent[0][0] == "benni@example.de"
    token = _reset_token_from_mail(mailer)

    resp = client.post("/api/account/reset-password", json={"token": token, "password": "ganz-neues-pw"})
    assert resp.status_code == 204
    assert client.get("/api/account/me").status_code == 200  # new cookie set by the reset

    client.cookies.set(user_deps.USER_COOKIE, old_cookie)
    assert client.get("/api/account/me").status_code == 401
    client.cookies.clear()
    ok = client.post("/api/account/login", json={"email": "benni@example.de", "password": "ganz-neues-pw"})
    assert ok.status_code == 200
    old = client.post("/api/account/login", json={"email": "benni@example.de", "password": _PASSWORD})
    assert old.status_code == 401


def test_reset_token_single_use(client: TestClient, mailer: FakeMailer) -> None:
    _register(client)
    client.post("/api/account/forgot-password", json={"email": "benni@example.de"})
    token = _reset_token_from_mail(mailer)
    assert client.post("/api/account/reset-password", json={"token": token, "password": "pw-nummer-eins"}).status_code == 204
    again = client.post("/api/account/reset-password", json={"token": token, "password": "pw-nummer-zwei"})
    assert again.status_code == 400


def test_reset_token_expired(client: TestClient, mailer: FakeMailer, db_factory: sessionmaker) -> None:
    _register(client)
    client.post("/api/account/forgot-password", json={"email": "benni@example.de"})
    token = _reset_token_from_mail(mailer)
    db = db_factory()
    row = db.query(PasswordResetToken).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()
    assert client.post("/api/account/reset-password", json={"token": token, "password": "pw-nummer-eins"}).status_code == 400


def test_accounts_unconfigured_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "session_secret", "")
    resp = client.post("/api/account/register", json={"email": "a@b.de", "password": _PASSWORD})
    assert resp.status_code == 503
    assert "SESSION_SECRET" in resp.json()["detail"]


# --- follow-up fixes ----------------------------------------------------------------

def test_login_unknown_email_still_checks_a_hash(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    real = account_route.verify_password
    monkeypatch.setattr(account_route, "verify_password", lambda pw, stored: checked.append(stored) or real(pw, stored))
    assert client.post("/api/account/login", json={"email": "nobody@x.de", "password": _PASSWORD}).status_code == 401
    assert len(checked) == 1


def test_register_race_returns_409(client: TestClient, db_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    # Another request created the account between the lookup and the insert.
    monkeypatch.setattr(account_route, "_find_user", lambda db, email: None)
    _register(client)
    resp = client.post("/api/account/register", json={"email": "benni@example.de", "password": _PASSWORD})
    assert resp.status_code == 409


def test_reset_invalidates_other_open_links(client: TestClient, mailer: FakeMailer) -> None:
    _register(client)
    client.post("/api/account/forgot-password", json={"email": "benni@example.de"})
    first = _reset_token_from_mail(mailer)
    client.post("/api/account/forgot-password", json={"email": "benni@example.de"})
    second = _reset_token_from_mail(mailer)
    assert client.post("/api/account/reset-password", json={"token": second, "password": "pw-nummer-eins"}).status_code == 204
    assert client.post("/api/account/reset-password", json={"token": first, "password": "pw-nummer-zwei"}).status_code == 400
