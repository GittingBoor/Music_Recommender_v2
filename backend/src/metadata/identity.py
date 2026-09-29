"""Where a song's title and artist come from when AcoustID does not know the audio."""
from dataclasses import dataclass
from enum import Enum

from src.metadata.cleaning import strip_version_markers


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
class AcoustidMatch:
    """What the AcoustID fingerprint lookup found; all None when it found nothing usable."""

    recording_id: str | None
    title: str | None
    artist: str | None
    featured_artists: tuple[str, ...] = ()


@dataclass(frozen=True)
class SongOrigin:
    """Where a song's audio came from, kept so it can be traced and fetched again."""

    original_name: str
    youtube_video_id: str | None = None


@dataclass(frozen=True)
class SongIdentity:
    """The title/artist a song is stored under, plus its AcoustID recording if known."""

    title: str
    raw_artist: str
    source: MetadataSource
    acoustid_id: str | None
    featured_artists: tuple[str, ...] = ()


def resolve_identity(
    acoustid: AcoustidMatch,
    hint: IdentityHint | None,
    tag_title: str,
    tag_artist: str,
) -> SongIdentity | None:
    """Pick the most trustworthy title/artist: AcoustID, then the hint, then the file tags.

    Edit/remaster/live markers are dropped from the title, so every cut of a
    song is stored under one name. Returns None when no source names both
    title and artist.
    """
    if acoustid.title and acoustid.artist:
        return SongIdentity(
            strip_version_markers(acoustid.title), acoustid.artist, MetadataSource.ACOUSTID,
            acoustid.recording_id, acoustid.featured_artists,
        )
    if hint and hint.title.strip() and hint.artist.strip():
        return SongIdentity(strip_version_markers(hint.title.strip()), hint.artist.strip(), hint.source, None)
    if tag_title.strip() and tag_artist.strip():
        return SongIdentity(
            strip_version_markers(tag_title.strip()), tag_artist.strip(), MetadataSource.FILE_TAGS, None
        )
    return None


def _same_name(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def needs_composer_check(identity: SongIdentity, hint: IdentityHint | None) -> bool:
    """True when AcoustID named the song but credits someone other than the artist the video/user named.

    Typical for classical music: MusicBrainz credits the recording to the
    performer, while the video names the composer.
    """
    if identity.source is not MetadataSource.ACOUSTID or hint is None or not hint.artist.strip():
        return False
    credited = (identity.raw_artist, *identity.featured_artists)
    return not any(_same_name(hint.artist, name) for name in credited)


def credit_composer(identity: SongIdentity, expected_artist: str, composers: list[str]) -> SongIdentity:
    """Make the composer the artist when the video/user named them; the performer becomes featured.

    Returns ``identity`` unchanged when ``expected_artist`` is none of ``composers``.
    """
    composer = next((c for c in composers if _same_name(c, expected_artist)), None)
    if composer is None:
        return identity
    featured = (identity.raw_artist, *[f for f in identity.featured_artists if not _same_name(f, composer)])
    return SongIdentity(identity.title, composer, identity.source, identity.acoustid_id, featured)
