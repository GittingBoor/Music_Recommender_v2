"""Song search on YouTube Music: the official releases (Topic uploads) of a track.

The plain YouTube search ranks lyric videos and fan uploads high; these carry
other cuts AcoustID often does not know. YouTube Music's "songs" filter only
returns the released audio, credited to the artist's Topic channel.
"""
import logging
from typing import Protocol

from src.youtube.service import _WATCH_URL, YoutubeSearchResult

logger = logging.getLogger(__name__)

_SONGS_FILTER = "songs"
_TOPIC_SUFFIX = " - Topic"


class SongSearchApi(Protocol):
    def search(self, query: str, filter: str, limit: int) -> list[dict]: ...


def _default_api() -> SongSearchApi:
    # Imported lazily: the client fetches YouTube Music's config on construction.
    from ytmusicapi import YTMusic
    return YTMusic()


class YoutubeMusicSearch:
    """Finds released songs; the hit's uploader is the main artist's Topic channel."""

    def __init__(self, api: SongSearchApi | None = None) -> None:
        self._api = api

    def songs(self, query: str, limit: int) -> list[YoutubeSearchResult]:
        """Up to ``limit`` songs for ``query``, YouTube Music's order.

        Raises:
            ValueError: If the query is empty.
            Exception: Whatever ytmusicapi raises when YouTube Music cannot be queried.
        """
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if self._api is None:
            self._api = _default_api()
        entries = self._api.search(query.strip(), filter=_SONGS_FILTER, limit=limit)
        hits = [hit for hit in (self._to_result(e) for e in entries) if hit is not None]
        logger.info("[YouTube Music] %r: %d songs", query, len(hits))
        return hits[:limit]

    @staticmethod
    def _to_result(entry: dict) -> YoutubeSearchResult | None:
        video_id = entry.get("videoId")
        artists = [a.get("name") for a in entry.get("artists") or [] if a.get("name")]
        if not video_id or not entry.get("title") or not artists:
            return None
        thumbnails = entry.get("thumbnails") or []
        duration = entry.get("duration_seconds")
        return YoutubeSearchResult(
            video_id=str(video_id),
            title=str(entry["title"]),
            uploader=f"{artists[0]}{_TOPIC_SUFFIX}",
            duration=int(duration) if duration else None,
            thumbnail=thumbnails[-1].get("url") if thumbnails else None,
            url=_WATCH_URL.format(video_id=video_id),
        )
