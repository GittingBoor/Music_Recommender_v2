import logging

import pytest

from src.core.config import Settings, warn_local_urls


def test_warns_when_secure_cookies_meet_local_urls(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_local_urls(Settings(session_cookie_secure=True))
    assert "PUBLIC_BASE_URL" in caplog.text
    assert "SPOTIFY_REDIRECT_URI" in caplog.text


def test_quiet_for_local_dev_and_configured_prod(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_local_urls(Settings(session_cookie_secure=False))
        warn_local_urls(Settings(
            session_cookie_secure=True,
            public_base_url="https://music.gittingboor.de",
            spotify_redirect_uri="https://music.gittingboor.de/api/spotify/callback",
        ))
    assert caplog.text == ""
