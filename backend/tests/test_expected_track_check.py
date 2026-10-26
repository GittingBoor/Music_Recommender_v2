from pathlib import Path

import pytest

from src.analysis import pipeline
from src.api.routes import admin
from src.metadata.identity import IdentityHint, MetadataSource
from src.spotify.matching import SpotifyTrack

_HELLO = SpotifyTrack(spotify_id="t1", title="Hello", artists=("Adele",), duration_ms=295_000, isrc=None)
_HINT = IdentityHint(title="Hello", artist="Adele", source=MetadataSource.SPOTIFY)


def _fake_precheck(verdict: str | None, title: str, artist: str, source: str):  # noqa: ANN202
    def precheck(audio_path: Path, hint: IdentityHint | None = None):  # noqa: ANN202
        metadata = {"title": title, "artist": artist, "metadata_source": source}
        return verdict, metadata, "song-id"
    return precheck


@pytest.fixture(autouse=True)
def _short_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "_get_duration_seconds", lambda path: 200.0)


def test_mismatch_rejected_before_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    # AcoustID heard Lionel Richie's "Hello", which is already in the library.
    monkeypatch.setattr(pipeline, "precheck_skip", _fake_precheck("duplicate", "Hello", "Lionel Richie", "acoustid"))
    result = admin._identify(Path("x.mp3"), _HINT, _HELLO)
    assert result["status"] == "skipped"
    assert result["reason"] == "spotify_mismatch"
    assert result["song_id"] is None


def test_matching_acoustid_identity_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _fake_precheck(None, "Hello", "Adele", "acoustid"))
    assert admin._identify(Path("x.mp3"), _HINT, _HELLO) == {
        "metadata": {"title": "Hello", "artist": "Adele", "metadata_source": "acoustid"}, "song_id": "song-id",
    }


def test_matching_duplicate_stays_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _fake_precheck("duplicate", "Hello", "Adele", "acoustid"))
    assert admin._identify(Path("x.mp3"), _HINT, _HELLO)["reason"] == "duplicate"


def test_unrecognised_audio_uses_spotify_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[IdentityHint | None] = []

    def precheck(audio_path: Path, hint: IdentityHint | None = None):  # noqa: ANN202
        seen.append(hint)
        return None, {"title": hint.title, "artist": hint.artist, "metadata_source": hint.source.value}, "song-id"

    monkeypatch.setattr(pipeline, "precheck_skip", precheck)
    result = admin._identify(Path("x.mp3"), _HINT, _HELLO, trust_unrecognised=True)
    assert seen == [_HINT]
    assert result["metadata"]["metadata_source"] == "spotify"


def test_without_expected_track_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _fake_precheck(None, "Hello", "Lionel Richie", "acoustid"))
    assert "status" not in admin._identify(Path("x.mp3"), None)


# --- final review fixes -----------------------------------------------------------

def test_composer_credit_does_not_hide_cover(monkeypatch: pytest.MonkeyPatch) -> None:
    jolene = SpotifyTrack(spotify_id="j", title="Jolene", artists=("Dolly Parton",), duration_ms=160_000, isrc=None)
    hint = IdentityHint(title="Jolene", artist="Dolly Parton", source=MetadataSource.SPOTIFY)

    def precheck(audio_path: Path, hint: IdentityHint | None = None):  # noqa: ANN202
        # The extractor credited the composer; AcoustID heard a cover band.
        metadata = {"title": "Jolene", "artist": "Dolly Parton", "metadata_source": "acoustid",
                    "acoustid_performers": ["Some Cover Band"]}
        return None, metadata, "song-id"

    monkeypatch.setattr(pipeline, "precheck_skip", precheck)
    assert admin._identify(Path("x.mp3"), hint, jolene, trust_unrecognised=True)["reason"] == "spotify_mismatch"


def test_unrecognised_audio_rejected_from_untrusted_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _fake_precheck(None, "Hello", "Adele", "spotify"))
    result = admin._identify(Path("x.mp3"), _HINT, _HELLO, trust_unrecognised=False)
    assert result["status"] == "skipped"
    assert result["reason"] == "unverified"


# --- AcoustID fingerprint without linked recording (2026-10-26) --------------------

def _unlinked_precheck(score: float):  # noqa: ANN202
    def precheck(audio_path: Path, hint: IdentityHint | None = None):  # noqa: ANN202
        metadata = {"title": "Hello", "artist": "Adele", "metadata_source": "spotify", "acoustid_unlinked_score": score}
        return None, metadata, "song-id"
    return precheck


def test_known_fingerprint_from_artist_channel_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _unlinked_precheck(0.951))
    assert "status" not in admin._identify(Path("x.mp3"), _HINT, _HELLO, from_artist_channel=True)


def test_known_fingerprint_needs_artist_channel_and_high_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "precheck_skip", _unlinked_precheck(0.951))
    assert admin._identify(Path("x.mp3"), _HINT, _HELLO, from_artist_channel=False)["reason"] == "unverified"
    monkeypatch.setattr(pipeline, "precheck_skip", _unlinked_precheck(0.62))
    assert admin._identify(Path("x.mp3"), _HINT, _HELLO, from_artist_channel=True)["reason"] == "unverified"
