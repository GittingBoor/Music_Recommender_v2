import logging
import random
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlencode

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
_SEARCH_RESULTS_URL = "https://www.youtube.com/results?{query}"
# YouTube's own "Type: Playlist" search filter.
_PLAYLIST_SEARCH_FILTER = "EgIQAw=="
_MP3_QUALITY = "192"

# A single track, not a mix or a jingle. The ingest pipeline rejects anything
# longer than 10 minutes that AcoustID cannot identify anyway.
_MIN_MUSIC_SECONDS = 45
_MAX_MUSIC_SECONDS = 600

_MUSIC_CATEGORY = "Music"
# YouTube auto-generates these channels for licensed music.
_TOPIC_SUFFIX = " - topic"

# Transient failures are retried with growing pauses; YouTube throttles bursts.
_DOWNLOAD_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (2, 6)

# The embedded web player needs neither login nor PO token and serves the
# audio formats; the default clients follow for videos that forbid embedding.
# Without it, YouTube answers the server with "confirm you're not a bot" or 403.
# Requires a JS runtime (deno) and yt-dlp-ejs in the image.
_PLAYER_CLIENTS = ["web_embedded", "default"]

_CLASSIFY_WORKERS = 8
# Over-fetch so the music filter can drop hits and still fill the page.
_SEARCH_OVERFETCH = 3

_EXAMPLE_SEEDS = [
    "indie rock official music video",
    "80s synth pop official video",
    "soul classics official video",
    "electronic dance official music video",
    "hip hop official music video",
    "jazz funk official video",
    "reggae official music video",
    "alternative rock official video",
    "house music official video",
    "pop ballad official music video",
]


class YoutubeErrorKind(str, Enum):
    """Why a YouTube operation failed — drives the message shown to the user."""

    UNAVAILABLE = "unavailable"
    GEO_BLOCKED = "geo_blocked"
    AGE_RESTRICTED = "age_restricted"
    RATE_LIMITED = "rate_limited"
    BOT_CHECK = "bot_check"
    NETWORK = "network"
    UNKNOWN = "unknown"


# scope "video" = this one clip only; "global" = affects every download.
_ERROR_TABLE: dict[YoutubeErrorKind, tuple[str, str, bool, str]] = {
    YoutubeErrorKind.UNAVAILABLE: (
        "Video nicht verfügbar",
        "YouTube liefert dieses Video nicht aus — es wurde gelöscht, auf privat "
        "gestellt oder vom Uploader gesperrt. Das betrifft nur dieses eine Video, "
        "andere Downloads funktionieren weiterhin. Wiederholen hilft nicht; such "
        "dir eine andere Version des Songs.",
        False,
        "video",
    ),
    YoutubeErrorKind.GEO_BLOCKED: (
        "In dieser Region gesperrt",
        "Der Rechteinhaber hat das Video für das Land gesperrt, aus dem der Server "
        "anfragt. Nur dieses Video ist betroffen. Eine andere Aufnahme desselben "
        "Songs lässt sich meist problemlos laden.",
        False,
        "video",
    ),
    YoutubeErrorKind.AGE_RESTRICTED: (
        "Altersbeschränkt",
        "YouTube verlangt für dieses Video eine Anmeldung zur Altersprüfung. Der "
        "Server ist nicht angemeldet und kann es deshalb nicht laden. Betrifft nur "
        "dieses Video.",
        False,
        "video",
    ),
    YoutubeErrorKind.RATE_LIMITED: (
        "Von YouTube ausgebremst",
        "YouTube hat die Anfrage abgelehnt (HTTP 403), weil in kurzer Zeit zu viele "
        "Downloads von dieser IP kamen, oder weil die Medien-URL zwischen Abruf und "
        "Download abgelaufen ist. Das ist vorübergehend und liegt nicht am Video: "
        "es wurde bereits mehrfach automatisch wiederholt. Warte ein bis zwei "
        "Minuten und versuche es erneut.",
        True,
        "global",
    ),
    YoutubeErrorKind.BOT_CHECK: (
        "YouTube hält den Server für einen Bot",
        "YouTube verlangt eine Anmeldung, bevor es Videos an diesen Server "
        "ausliefert. Das liegt nicht am Video und betrifft alle Downloads. Meist "
        "ist yt-dlp veraltet oder im Container fehlt die JavaScript-Laufzeit "
        "(deno). Solange das besteht, lassen sich Songs nur per Datei-Upload "
        "hinzufügen.",
        False,
        "global",
    ),
    YoutubeErrorKind.NETWORK: (
        "Keine Verbindung zu YouTube",
        "Der Server konnte YouTube nicht erreichen. Das ist ein lokales Problem — "
        "prüfe die Internetverbindung des Docker-Containers (DNS steht in "
        "docker-compose.yml). Kein Download wird funktionieren, solange das besteht.",
        True,
        "global",
    ),
    YoutubeErrorKind.UNKNOWN: (
        "Unbekannter Fehler",
        "Der Download ist aus einem Grund fehlgeschlagen, den wir nicht zuordnen "
        "können. Die Originalmeldung von yt-dlp steht unten — wenn sie bei jedem "
        "Video auftritt, ist vermutlich yt-dlp veraltet.",
        False,
        "unknown",
    ),
}


class YoutubeError(Exception):
    """A classified YouTube failure carrying a user-readable explanation."""

    def __init__(self, kind: YoutubeErrorKind, raw_message: str) -> None:
        title, explanation, retryable, scope = _ERROR_TABLE[kind]
        super().__init__(title)
        self.kind = kind
        self.title = title
        self.explanation = explanation
        self.retryable = retryable
        self.scope = scope
        self.raw_message = raw_message

    def as_dict(self) -> dict[str, str | bool]:
        """Serialise for the API response."""
        return {
            "kind": self.kind.value,
            "title": self.title,
            "explanation": self.explanation,
            "scope": self.scope,
            "raw_message": self.raw_message,
        }


def classify_error(exc: Exception) -> YoutubeError:
    """Map a raw yt-dlp exception onto a explained :class:`YoutubeError`."""
    if isinstance(exc, YoutubeError):
        return exc

    text = str(exc).lower()
    if "403" in text or "forbidden" in text or "429" in text or "too many requests" in text:
        kind = YoutubeErrorKind.RATE_LIMITED
    elif "not available in your country" in text or "geo" in text:
        kind = YoutubeErrorKind.GEO_BLOCKED
    elif "not a bot" in text:
        kind = YoutubeErrorKind.BOT_CHECK
    elif "age" in text and ("confirm" in text or "restrict" in text or "sign in" in text):
        kind = YoutubeErrorKind.AGE_RESTRICTED
    elif "not available" in text or "private" in text or "removed" in text or "terminated" in text:
        kind = YoutubeErrorKind.UNAVAILABLE
    elif "resolve" in text or "connection" in text or "timed out" in text or "network" in text:
        kind = YoutubeErrorKind.NETWORK
    else:
        kind = YoutubeErrorKind.UNKNOWN
    return YoutubeError(kind, str(exc))


class MusicVerdict(str, Enum):
    """Outcome of asking YouTube whether a video is filed under "Music"."""

    MUSIC = "music"
    NOT_MUSIC = "not_music"
    # Lookup failed, e.g. YouTube's "confirm you're not a bot" check.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class YoutubeSearchResult:
    """A single search hit returned to the frontend."""

    video_id: str
    title: str
    uploader: str | None
    duration: int | None  # seconds
    thumbnail: str | None
    url: str


@dataclass(frozen=True)
class YoutubePlaylistHit:
    """A playlist found by search; its videos are resolved only when opened."""

    playlist_id: str
    title: str
    uploader: str | None
    thumbnail: str | None
    url: str


class YoutubeService:
    """Search YouTube and download a video's audio track via yt-dlp.

    No external API key is required: yt-dlp's built-in ``ytsearch`` query
    handles search, and its FFmpeg post-processor extracts the audio as MP3.
    Only videos YouTube itself files under the "Music" category are offered,
    so non-music clips never reach the analysis pipeline.
    """

    _FLAT_OPTS: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    _META_OPTS: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    # ── search ─────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[YoutubeSearchResult]:
        """Return up to ``limit`` music videos matching ``query``."""
        if not query.strip():
            raise ValueError("Search query must not be empty")

        entries = self._flat_entries(
            f"ytsearch{limit * _SEARCH_OVERFETCH}:{query.strip()}"
        )
        return self._keep_music(entries, limit)

    def search_candidates(self, query: str, limit: int = 10) -> list[YoutubeSearchResult]:
        """Return plausible tracks from one cheap flat search, without the category lookup.

        Over-fetches so callers can still fill ``limit`` slots after
        :meth:`verify_music` rejects some of them.

        Raises:
            ValueError: If the query is empty.
            YoutubeError: If YouTube cannot be queried.
        """
        if not query.strip():
            raise ValueError("Search query must not be empty")

        entries = self._flat_entries(f"ytsearch{limit * _SEARCH_OVERFETCH}:{query.strip()}")
        return [self._to_result(e) for e in entries if self._plausible_track(e)]

    def verify_music(self, results: list[YoutubeSearchResult]) -> Iterator[tuple[str, MusicVerdict]]:
        """Yield ``(video_id, verdict)`` for each result as soon as its lookup finishes."""
        pool = ThreadPoolExecutor(max_workers=_CLASSIFY_WORKERS)
        try:
            futures = {
                pool.submit(self._music_verdict, r.video_id, r.uploader): r.video_id
                for r in results
            }
            for future in as_completed(futures):
                yield futures[future], future.result()
        finally:
            # A closed stream must not wait for the remaining lookups.
            pool.shutdown(wait=False, cancel_futures=True)

    def search_playlists(self, query: str, limit: int = 3) -> list[YoutubePlaylistHit]:
        """Return up to ``limit`` playlists matching ``query``.

        Raises:
            ValueError: If the query is empty.
            YoutubeError: If YouTube cannot be queried.
        """
        if not query.strip():
            raise ValueError("Search query must not be empty")

        target = _SEARCH_RESULTS_URL.format(
            query=urlencode({"search_query": query.strip(), "sp": _PLAYLIST_SEARCH_FILTER})
        )
        try:
            with YoutubeDL({**self._FLAT_OPTS, "playlistend": limit}) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception as exc:
            raise classify_error(exc) from exc

        entries = [e for e in (info or {}).get("entries") or [] if e and e.get("id")]
        return [self._to_playlist_hit(e) for e in entries[:limit]]

    def examples(self, limit: int = 5) -> list[YoutubeSearchResult]:
        """Return a random sample of music videos as starting points."""
        seed = random.choice(_EXAMPLE_SEEDS)
        logger.info("[YouTube] Example seed: %s", seed)
        entries = self._flat_entries(f"ytsearch{limit * _SEARCH_OVERFETCH}:{seed}")
        random.shuffle(entries)
        return self._keep_music(entries, limit)

    def playlist_entries(
        self, url: str, limit: int = 50
    ) -> tuple[str | None, list[YoutubeSearchResult]]:
        """Return ``(playlist_title, music_videos)`` for a playlist URL.

        Raises:
            ValueError: If the URL is not a playlist.
        """
        if not url.strip():
            raise ValueError("Playlist URL must not be empty")

        try:
            with YoutubeDL({**self._FLAT_OPTS, "playlistend": limit}) as ydl:
                info = ydl.extract_info(url.strip(), download=False)
        except Exception as exc:
            raise classify_error(exc) from exc

        if not info or info.get("_type") != "playlist":
            raise ValueError(
                "Das ist keine Playlist-URL. Erwartet wird ein Link mit "
                "?list=… (z. B. https://www.youtube.com/playlist?list=PL…)"
            )

        entries = [e for e in (info.get("entries") or []) if e]
        return info.get("title"), self._keep_music(entries, limit)

    # ── download ───────────────────────────────────────────────────────────

    def download_audio(self, video_id: str, dest_dir: Path) -> Path:
        """Download the video's audio as MP3 into ``dest_dir``.

        Transient failures (throttling, expired media URLs) are retried with
        growing pauses. Permanent ones fail immediately — retrying a deleted
        video only wastes the user's time.

        Raises:
            YoutubeError: Classified failure carrying a user-readable reason.
        """
        if not video_id.strip():
            raise ValueError("video_id must not be empty")

        dest_dir.mkdir(parents=True, exist_ok=True)
        opts: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            # yt-dlp's own retry layers: HTTP errors, fragments and the extractor.
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 3,
            # Pace requests so a burst of downloads doesn't trip YouTube's limiter.
            "sleep_interval_requests": 1,
            "extractor_args": {"youtube": {"player_client": _PLAYER_CLIENTS}},
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": _MP3_QUALITY,
                }
            ],
        }

        last_error: YoutubeError | None = None
        for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
            try:
                with YoutubeDL(opts) as ydl:
                    ydl.extract_info(
                        _WATCH_URL.format(video_id=video_id), download=True
                    )
                break
            except Exception as exc:
                error = classify_error(exc)
                last_error = error
                if not error.retryable or attempt == _DOWNLOAD_ATTEMPTS:
                    logger.error(
                        "[YouTube] %s for %s (attempt %d): %s",
                        error.kind.value, video_id, attempt, error.raw_message,
                    )
                    raise error
                pause = _RETRY_BACKOFF_SECONDS[min(attempt - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning(
                    "[YouTube] %s for %s — retrying in %ds (attempt %d/%d)",
                    error.kind.value, video_id, pause, attempt, _DOWNLOAD_ATTEMPTS,
                )
                time.sleep(pause)

        result_path = dest_dir / f"{video_id}.mp3"
        if not result_path.exists():
            raise last_error or YoutubeError(
                YoutubeErrorKind.UNKNOWN,
                f"Download produced no MP3 for video {video_id}",
            )
        return result_path

    # ── internals ──────────────────────────────────────────────────────────

    def _flat_entries(self, target: str) -> list[dict]:
        """Run a cheap flat extraction and return its raw entries."""
        try:
            with YoutubeDL(self._FLAT_OPTS) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception as exc:
            raise classify_error(exc) from exc
        return [e for e in (info or {}).get("entries") or [] if e]

    def _keep_music(self, entries: list[dict], limit: int) -> list[YoutubeSearchResult]:
        """Filter ``entries`` down to actual music videos, newest logic first.

        Duration and live status come from the cheap flat listing; the
        authoritative "Music" category needs one metadata call per video, so
        those run in parallel and only for candidates that already passed.
        """
        candidates = [e for e in entries if self._plausible_track(e)]
        if not candidates:
            return []

        with ThreadPoolExecutor(max_workers=_CLASSIFY_WORKERS) as pool:
            flags = list(pool.map(self._is_music, candidates))

        kept = [e for e, is_music in zip(candidates, flags) if is_music]
        logger.info(
            "[YouTube] %d hits → %d plausible → %d music",
            len(entries), len(candidates), len(kept),
        )
        return [self._to_result(e) for e in kept[:limit]]

    @staticmethod
    def _plausible_track(entry: dict) -> bool:
        """Cheap pre-filter: a single track, not a livestream or an hour-long mix."""
        if entry.get("live_status") in ("is_live", "is_upcoming"):
            return False
        duration = entry.get("duration")
        if not duration:
            return False
        return _MIN_MUSIC_SECONDS <= int(duration) <= _MAX_MUSIC_SECONDS

    def _is_music(self, entry: dict) -> bool:
        """Strict check: a video whose lookup fails is dropped, not kept."""
        verdict = self._music_verdict(
            str(entry.get("id") or ""), entry.get("uploader") or entry.get("channel")
        )
        return verdict is MusicVerdict.MUSIC

    def _music_verdict(self, video_id: str, uploader: str | None) -> MusicVerdict:
        """Ask YouTube which category the video is filed under.

        Auto-generated "- Topic" channels are licensed music by definition and
        skip the lookup. A failed lookup is UNKNOWN so each caller decides
        whether to hide or keep the video.
        """
        if (uploader or "").lower().endswith(_TOPIC_SUFFIX):
            return MusicVerdict.MUSIC
        if not video_id:
            return MusicVerdict.UNKNOWN
        try:
            with YoutubeDL(self._META_OPTS) as ydl:
                info = ydl.extract_info(
                    _WATCH_URL.format(video_id=video_id), download=False
                )
        except Exception as exc:
            logger.debug("[YouTube] Category lookup failed for %s: %s", video_id, exc)
            return MusicVerdict.UNKNOWN

        categories = (info or {}).get("categories") or []
        return MusicVerdict.MUSIC if _MUSIC_CATEGORY in categories else MusicVerdict.NOT_MUSIC

    @staticmethod
    def _to_result(entry: dict) -> YoutubeSearchResult:
        video_id = str(entry.get("id") or "")
        duration = entry.get("duration")
        return YoutubeSearchResult(
            video_id=video_id,
            title=str(entry.get("title") or "Unbekannt"),
            uploader=entry.get("uploader") or entry.get("channel"),
            duration=int(duration) if duration else None,
            thumbnail=YoutubeService._first_thumbnail(entry),
            url=str(entry.get("url") or _WATCH_URL.format(video_id=video_id)),
        )

    @staticmethod
    def _to_playlist_hit(entry: dict) -> YoutubePlaylistHit:
        playlist_id = str(entry["id"])
        return YoutubePlaylistHit(
            playlist_id=playlist_id,
            title=str(entry.get("title") or "Unbekannt"),
            uploader=entry.get("uploader") or entry.get("channel"),
            thumbnail=YoutubeService._first_thumbnail(entry),
            url=str(entry.get("url") or f"https://www.youtube.com/playlist?list={playlist_id}"),
        )

    @staticmethod
    def _first_thumbnail(entry: dict) -> str | None:
        thumbnails = entry.get("thumbnails") or []
        if thumbnails and isinstance(thumbnails, list):
            return thumbnails[0].get("url")
        thumbnail = entry.get("thumbnail")
        return str(thumbnail) if thumbnail else None
