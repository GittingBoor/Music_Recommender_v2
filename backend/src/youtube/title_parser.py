"""Guess artist and song title from a YouTube video title.

Used when AcoustID does not know the audio, and to spot songs that are
already in the library before anything is downloaded. Typical inputs:
"Avicii - Hey Brother (Official Video)", "Hey Brother" on "Avicii - Topic",
"Hey Brother" on "AviciiOfficialVEVO".
"""
import re
from dataclasses import dataclass

from src.metadata.cleaning import split_artist_featuring

_TOPIC_SUFFIX = " - topic"
_SEPARATOR_RE = re.compile(r"\s+[-–—|]\s+")
_BRACKETED_RE = re.compile(r"\s*[\(\[【][^\)\]】]*[\)\]】]")
_NOISE_RE = re.compile(
    r"official|video|audio|lyric|visuali[sz]er|\bhd\b|\bhq\b|\b4k\b|\bmv\b|remaster|"
    r"clip|explicit|full song|with lyrics",
    re.IGNORECASE,
)
_UNBRACKETED_NOISE_RE = re.compile(
    r"\s+(?:official\s+)?(?:music\s+)?(?:video|audio|lyrics?)(?:\s+video)?\s*$",
    re.IGNORECASE,
)
_TITLE_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
_CHANNEL_NOISE_RE = re.compile(r"(?:\s*-?\s*official)?\s*(?:vevo|music|tv)?\s*$", re.IGNORECASE)
_QUOTES = "\"'“”‘’«»"


@dataclass(frozen=True)
class ParsedTrack:
    """Artist and title read from a video title."""

    title: str
    artist: str


def _strip_noise_brackets(text: str) -> str:
    """Drop bracketed parts like "(Official Video)" but keep "(Radio Edit)"."""
    return _BRACKETED_RE.sub(lambda m: "" if _NOISE_RE.search(m.group()) else m.group(), text)


def _clean_title(text: str) -> str:
    title = _strip_noise_brackets(text)
    title = _UNBRACKETED_NOISE_RE.sub("", title)
    title = _TITLE_FEAT_RE.sub("", title)
    return title.strip().strip(_QUOTES).strip()


def _clean_artist(text: str) -> str:
    artist, _ = split_artist_featuring(_strip_noise_brackets(text).strip())
    return artist.strip().strip(_QUOTES).strip()


def _artist_from_channel(uploader: str) -> str:
    channel = uploader.strip()
    if channel.lower().endswith(_TOPIC_SUFFIX):
        return channel[: -len(_TOPIC_SUFFIX)].strip()
    return _CHANNEL_NOISE_RE.sub("", channel).strip()


def parse_video_title(video_title: str, uploader: str | None) -> ParsedTrack | None:
    """Return the artist/title a video most likely contains, or None if neither is readable.

    "Artist - Title" wins; without a separator the channel name is the artist
    ("- Topic" and "VEVO" channels are named after the artist).
    """
    parts = _SEPARATOR_RE.split(video_title.strip(), maxsplit=1)
    if len(parts) == 2 and not (uploader or "").lower().endswith(_TOPIC_SUFFIX):
        artist, title = _clean_artist(parts[0]), _clean_title(parts[1])
    else:
        artist, title = _artist_from_channel(uploader or ""), _clean_title(video_title)
    if not artist or not title:
        return None
    return ParsedTrack(title=title, artist=artist)
