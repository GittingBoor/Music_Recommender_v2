"""Read technical metadata and embedded tags from local audio files (mutagen)."""
import logging
from pathlib import Path

from mutagen import File as MutagenFile

from src.metadata.cleaning import (
    dedup_featured_artists,
    normalize_date,
    parse_featured_artists,
    split_artist_featuring,
)

logger = logging.getLogger(__name__)


def _tag_str(tags: object, key: str) -> str | None:
    value = tags.get(key) if tags else None
    if value is None:
        return None
    return str(value[0]) if isinstance(value, list) else str(value)


def extract_file_metadata(audio_path: Path) -> dict[str, object]:
    logger.info("[Metadata] Reading file tags: %s", audio_path.name)
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        logger.warning("[Metadata] No tags readable from %s", audio_path.name)
        return {"filename": audio_path.name, "file_format": audio_path.suffix.lstrip(".").upper()}

    tags = audio.tags or {}
    genre_raw = _tag_str(tags, "genre")
    title = _tag_str(tags, "title")

    # Always clean feat./ft. from the artist tag so the main artist is stored cleanly
    raw_artist = _tag_str(tags, "artist")
    clean_artist, feat_from_artist = split_artist_featuring(raw_artist or "") if raw_artist else (raw_artist, [])

    feat_from_title = parse_featured_artists(title) if title else []
    all_featured: list[str] = list(feat_from_artist)
    for fa in feat_from_title:
        if fa not in all_featured:
            all_featured.append(fa)
    all_featured = dedup_featured_artists(all_featured)

    result: dict[str, object] = {
        "filename": audio_path.name,
        "title": title,
        "artist": clean_artist,
        "featured_artists": all_featured,
        "album": _tag_str(tags, "album"),
        "release_date": normalize_date(_tag_str(tags, "date")),
        "genres": [genre_raw] if genre_raw else [],
        "file_format": audio_path.suffix.lstrip(".").upper(),
    }
    info = audio.info
    result["duration_seconds"] = round(float(info.length), 2)
    result["sample_rate_hz"] = getattr(info, "sample_rate", None)
    result["channels"] = getattr(info, "channels", None)
    bitrate = getattr(info, "bitrate", None)
    result["bitrate_kbps"] = round(bitrate / 1000) if bitrate else None
    return result
