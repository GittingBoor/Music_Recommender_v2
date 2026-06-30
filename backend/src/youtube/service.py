import logging
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
_MP3_QUALITY = "192"


@dataclass(frozen=True)
class YoutubeSearchResult:
    """A single search hit returned to the frontend."""

    video_id: str
    title: str
    uploader: str | None
    duration: int | None  # seconds
    thumbnail: str | None
    url: str


class YoutubeService:
    """Search YouTube and download a video's audio track via yt-dlp.

    No external API key is required: yt-dlp's built-in ``ytsearch`` query
    handles search, and its FFmpeg post-processor extracts the audio as MP3.
    """

    _SEARCH_OPTS: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    def search(self, query: str, limit: int = 10) -> list[YoutubeSearchResult]:
        """Return up to ``limit`` YouTube results for ``query``."""
        if not query.strip():
            raise ValueError("Search query must not be empty")

        search_term = f"ytsearch{limit}:{query.strip()}"
        with YoutubeDL(self._SEARCH_OPTS) as ydl:
            info = ydl.extract_info(search_term, download=False)

        entries = (info or {}).get("entries") or []
        return [self._to_result(entry) for entry in entries if entry]

    def download_audio(self, video_id: str, dest_dir: Path) -> Path:
        """Download the video's audio as MP3 into ``dest_dir``.

        Returns the path of the resulting ``<video_id>.mp3`` file. Requires
        FFmpeg to be available on the system PATH.
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
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": _MP3_QUALITY,
                }
            ],
        }

        with YoutubeDL(opts) as ydl:
            ydl.extract_info(_WATCH_URL.format(video_id=video_id), download=True)

        result_path = dest_dir / f"{video_id}.mp3"
        if not result_path.exists():
            raise RuntimeError(f"Download produced no MP3 for video {video_id}")
        return result_path

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
    def _first_thumbnail(entry: dict) -> str | None:
        thumbnails = entry.get("thumbnails") or []
        if thumbnails and isinstance(thumbnails, list):
            return thumbnails[0].get("url")
        thumbnail = entry.get("thumbnail")
        return str(thumbnail) if thumbnail else None
