"""Decide whether a YouTube video is a song that is already in the library.

Library titles and artists come from AcoustID/MusicBrainz, YouTube titles are
free text ("Avicii - Hey Brother (Official Video)"). A video counts as known
when the song title AND at least one of its artists appear as whole words in
the video title or channel name. Title-only matching would flag every video
containing a common word like "Burn" or "Wild".
"""

import re
from dataclasses import dataclass

_NON_WORD_RE = re.compile(r"[\W_]+")
_BRACKETED_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_ARTIST_SEPARATOR_RE = re.compile(r"\s*(?:,|&|\bfeat\.?|\bft\.?|\bvs\.?|\bx\b)\s*", re.IGNORECASE)


def _word_key(text: str) -> str:
    """Lowercase, punctuation collapsed to single spaces, padded for whole-word lookup."""
    words = _NON_WORD_RE.sub(" ", text.lower()).strip()
    return f" {words} " if words else ""


@dataclass(frozen=True)
class LibraryEntry:
    """Normalised lookup keys for one library song."""

    title_key: str
    artist_keys: tuple[str, ...]

    @classmethod
    def from_song(cls, title: str | None, artist: str | None) -> "LibraryEntry | None":
        """Build keys from a stored song; returns None when title or artist is missing."""
        title_key = _word_key(_BRACKETED_RE.sub(" ", title or ""))
        artist_keys = tuple(
            key for key in (_word_key(part) for part in _ARTIST_SEPARATOR_RE.split(artist or "")) if key
        )
        if not title_key or not artist_keys:
            return None
        return cls(title_key=title_key, artist_keys=artist_keys)

    def matches(self, haystack: str) -> bool:
        return self.title_key in haystack and any(key in haystack for key in self.artist_keys)


class LibraryMatcher:
    """Answer "is this video already in the library?" for many videos at once."""

    def __init__(self, songs: list[tuple[str | None, str | None]]) -> None:
        entries = (LibraryEntry.from_song(title, artist) for title, artist in songs)
        self._entries: list[LibraryEntry] = [entry for entry in entries if entry is not None]

    def contains(self, video_title: str, uploader: str | None) -> bool:
        """True when a library song's title and one of its artists occur in the video's title or channel."""
        haystack = _word_key(f"{video_title} {uploader or ''}")
        return any(entry.matches(haystack) for entry in self._entries)
