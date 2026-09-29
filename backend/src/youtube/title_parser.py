"""Guess artist and song title from a YouTube video title.

Used when AcoustID does not know the audio, and to spot songs that are
already in the library before anything is downloaded. Typical inputs:
"Avicii - Hey Brother (Official Video)", "Hey Brother" on "Avicii - Topic",
"Hey Brother" on "AviciiOfficialVEVO".
"""
import re
import unicodedata
from dataclasses import dataclass

from src.metadata.cleaning import split_artist_featuring

_TOPIC_SUFFIX = " - topic"
_SEPARATOR_RE = re.compile(r"\s+[-–—|]\s+")
# "Artist: Title" — only used when the title has no dash separator.
_COLON_SEPARATOR_RE = re.compile(r":\s+")
_BRACKETED_RE = re.compile(r"\s*[\(\[【][^\)\]】]*[\)\]】]")
_NOISE_RE = re.compile(
    r"official|video|audio|lyric|visuali[sz]er|\bhd\b|\bhq\b|\b4k\b|\bmv\b|remaster|"
    r"clip|explicit|full song|with lyrics|\blive\b|[\(\[【]\s*from\s|#",
    re.IGNORECASE,
)
# "⚪ 432 Hz", emoji and other pictographs decorating the title.
_FREQUENCY_RE = re.compile(r"\s+\d+\s*hz\b", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"\s+#\w+")
_UNBRACKETED_NOISE_RE = re.compile(
    r"\s+(?:official\s+)?(?:music\s+)?(?:video|audio|lyrics?)(?:\s+video)?\s*$",
    re.IGNORECASE,
)
_QUALITY_TAGS_RE = re.compile(r"(?:\s+(?:hd|hq|4k|1080p|720p))+\s*$", re.IGNORECASE)
# "Enter Sandman Live Moscow 1991" or "Wake Me Up - Live"; a leading "Live"
# ("Live Forever") or a closing one ("Long Live") belongs to the song.
_LIVE_SUFFIX_RE = re.compile(r"(?:\s+[-–—]\s+live\b.*|(?<=\S)\s+live\s+\S.*)$", re.IGNORECASE)
_TITLE_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
_CHANNEL_NOISE_RE = re.compile(r"(?:\s*-?\s*official)?\s*(?:vevo|music|tv)?\s*$", re.IGNORECASE)
_QUOTES = "\"'“”‘’«»"


@dataclass(frozen=True)
class ParsedTrack:
    """Artist and title read from a video title."""

    title: str
    artist: str
    # Another artist the title names, e.g. the composer in "Tchaikovsky: Swan Lake" on a Topic channel.
    mentioned_artist: str | None = None


def _strip_noise_brackets(text: str) -> str:
    """Drop bracketed parts like "(Official Video)" but keep "(Radio Edit)"."""
    return _BRACKETED_RE.sub(lambda m: "" if _NOISE_RE.search(m.group()) else m.group(), text)


def _strip_symbols(text: str) -> str:
    """Remove pictographs such as ⚪ or emoji; letters, digits and punctuation like & or $ stay."""
    return "".join(c for c in text if unicodedata.category(c) != "So")


def _clean_title(text: str) -> str:
    title = _strip_noise_brackets(text)
    title = _strip_symbols(title)
    title = _HASHTAG_RE.sub("", title)
    title = _FREQUENCY_RE.sub("", title)
    title = _QUALITY_TAGS_RE.sub("", title)
    title = _UNBRACKETED_NOISE_RE.sub("", title)
    title = _LIVE_SUFFIX_RE.sub("", title)
    title = _TITLE_FEAT_RE.sub("", title)
    return title.strip().strip(_QUOTES).strip()


def _clean_artist(text: str) -> str:
    # "Rammstein: Paris" names the concert film, not the artist.
    text = _COLON_SEPARATOR_RE.split(text, maxsplit=1)[0]
    artist, _ = split_artist_featuring(_strip_noise_brackets(text).strip())
    return artist.strip().strip(_QUOTES).strip()


def _split_artist_title(video_title: str) -> list[str]:
    parts = _SEPARATOR_RE.split(video_title.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts
    return _COLON_SEPARATOR_RE.split(video_title.strip(), maxsplit=1)


def _artist_from_channel(uploader: str) -> str:
    channel = uploader.strip()
    if channel.lower().endswith(_TOPIC_SUFFIX):
        return channel[: -len(_TOPIC_SUFFIX)].strip()
    return _CHANNEL_NOISE_RE.sub("", channel).strip()


_ARTIST_LIST_RE = re.compile(r"\s*(?:,|&|\bx\b|\band\b)\s*", re.IGNORECASE)


def _drop_artist_prefix(title: str, artist: str) -> str:
    """ "Erik Satie: Gymnopédie No.1" under "Khatia Buniatishvili, Erik Satie" → "Gymnopédie No.1"."""
    prefix, colon, rest = title.partition(": ")
    named = {a.casefold() for a in _ARTIST_LIST_RE.split(artist) if a} | {artist.casefold()}
    if colon and rest.strip() and prefix.strip().casefold() in named:
        return rest.strip()
    return title


def _is_title_first(parts: list[str], uploader: str | None) -> bool:
    """ "In The End - Linkin Park" on the Linkin Park channel: the channel names the right side."""
    channel = _artist_from_channel(uploader or "").casefold()
    return bool(channel) and (
        _clean_artist(parts[1]).casefold() == channel and _clean_artist(parts[0]).casefold() != channel
    )


def video_names_artist(video_title: str, uploader: str | None) -> bool:
    """True when the video itself tells who the artist is.

    That is an "Artist - Title" (or "Artist: Title") title, or a "- Topic" or
    VEVO channel, which YouTube names after the artist. Any other channel
    name (a label, a fan, "… Official channel") is a guess.
    """
    channel = (uploader or "").lower()
    return len(_split_artist_title(video_title)) == 2 or channel.endswith(_TOPIC_SUFFIX) or "vevo" in channel


def parse_search_query(query: str) -> ParsedTrack | None:
    """Read an "Artist - Title" search query (as typed or bulk-imported); None without a dash separator."""
    parts = _SEPARATOR_RE.split(query.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    artist, title = _clean_artist(parts[0]), _clean_title(parts[1])
    if not artist or not title:
        return None
    return ParsedTrack(title=title, artist=artist)


def parse_video_title(video_title: str, uploader: str | None) -> ParsedTrack | None:
    """Return the artist/title a video most likely contains, or None if neither is readable.

    "Artist - Title" (or "Artist: Title") wins; without a separator the channel
    name is the artist ("- Topic" and "VEVO" channels are named after the artist).
    """
    parts = _split_artist_title(video_title)
    if len(parts) == 2 and not (uploader or "").lower().endswith(_TOPIC_SUFFIX):
        artist, title = _clean_artist(parts[0]), _clean_title(parts[1])
        if _is_title_first(parts, uploader):
            artist, title = _clean_artist(parts[1]), _clean_title(parts[0])
        title = _drop_artist_prefix(title, artist)
    else:
        artist, title = _artist_from_channel(uploader or ""), _clean_title(video_title)
        if len(parts) == 2 and artist and _clean_artist(parts[0]).casefold() == artist.casefold():
            title = _clean_title(parts[1])  # "Adele - Hello" on "Adele - Topic"
    if not artist or not title:
        return None
    return ParsedTrack(title=title, artist=artist, mentioned_artist=_mentioned_artist(video_title, uploader, artist))


def _mentioned_artist(video_title: str, uploader: str | None, artist: str) -> str | None:
    """ "Tchaikovsky: Swan Lake" on an orchestra's Topic channel names the composer before the colon."""
    if not (uploader or "").lower().endswith(_TOPIC_SUFFIX):
        return None
    parts = _COLON_SEPARATOR_RE.split(video_title.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    mentioned = _clean_artist(parts[0])
    return mentioned if mentioned and mentioned.casefold() != artist.casefold() else None


def guess_track(video_title: str, uploader: str | None, query: str | None) -> ParsedTrack | None:
    """Artist/title for a video AcoustID may not know.

    The video's own "Artist - Title" or artist channel wins; otherwise an
    "Artist - Title" search query that led to the video is the better guess
    than an arbitrary uploader name.
    """
    if not video_names_artist(video_title, uploader) and query:
        from_query = parse_search_query(query)
        if from_query is not None:
            return from_query
    return parse_video_title(video_title, uploader)
