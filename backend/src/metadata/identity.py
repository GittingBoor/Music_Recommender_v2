"""Where a song's title and artist come from when AcoustID does not know the audio."""
from dataclasses import dataclass
from enum import Enum


class MetadataSource(str, Enum):
    """Origin of a stored song's title/artist. Anything but ACOUSTID awaits an admin check."""

    ACOUSTID = "acoustid"
    YOUTUBE_TITLE = "youtube_title"
    USER_INPUT = "user_input"
    FILE_TAGS = "file_tags"


@dataclass(frozen=True)
class IdentityHint:
    """Title/artist supplied by the caller (parsed video title or typed in by the uploader)."""

    title: str
    artist: str
    source: MetadataSource


@dataclass(frozen=True)
class SongIdentity:
    """The title/artist a song is stored under, plus its AcoustID recording if known."""

    title: str
    raw_artist: str
    source: MetadataSource
    acoustid_id: str | None


def resolve_identity(
    acoustid: tuple[str | None, str | None, str | None],
    hint: IdentityHint | None,
    tag_title: str,
    tag_artist: str,
) -> SongIdentity | None:
    """Pick the most trustworthy title/artist: AcoustID, then the hint, then the file tags.

    ``acoustid`` is ``(recording_id, title, artist)`` as returned by the lookup.
    Returns None when no source names both title and artist.
    """
    recording_id, aid_title, aid_artist = acoustid
    if aid_title and aid_artist:
        return SongIdentity(aid_title, aid_artist, MetadataSource.ACOUSTID, recording_id)
    if hint and hint.title.strip() and hint.artist.strip():
        return SongIdentity(hint.title.strip(), hint.artist.strip(), hint.source, None)
    if tag_title.strip() and tag_artist.strip():
        return SongIdentity(tag_title.strip(), tag_artist.strip(), MetadataSource.FILE_TAGS, None)
    return None
