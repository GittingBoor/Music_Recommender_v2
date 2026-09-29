"""Where a song's title and artist come from when AcoustID does not know the audio."""
from dataclasses import dataclass
from enum import Enum

from src.metadata.cleaning import plain_quotes, strip_version_markers


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
    # Another artist the video title names, e.g. the composer in "Tchaikovsky: Swan Lake"
    # on an orchestra's Topic channel.
    mentioned_artist: str | None = None
    # The text the hint was read from (full video title); guests it names are expected.
    source_text: str | None = None


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
    song is stored under one name, and typographic quotes become plain ones
    ("Hips Don’t Lie" → "Hips Don't Lie"). Returns None when no source names
    both title and artist.
    """
    if acoustid.title and acoustid.artist:
        artist = plain_quotes(acoustid.artist)
        featured = tuple(
            plain_quotes(f) for f in acoustid.featured_artists if f.casefold() != artist.casefold()
        )
        return SongIdentity(_clean(acoustid.title), artist, MetadataSource.ACOUSTID, acoustid.recording_id, featured)
    if hint and hint.title.strip() and hint.artist.strip():
        return SongIdentity(_clean(hint.title), plain_quotes(hint.artist.strip()), hint.source, None)
    if tag_title.strip() and tag_artist.strip():
        return SongIdentity(_clean(tag_title), plain_quotes(tag_artist.strip()), MetadataSource.FILE_TAGS, None)
    return None


def _clean(title: str) -> str:
    return plain_quotes(strip_version_markers(title.strip()))


def _same_name(named: str, full: str) -> bool:
    """True when ``named`` is ``full`` or its surname ("Mozart" for "Wolfgang Amadeus Mozart")."""
    a, b = named.strip().casefold(), full.strip().casefold()
    return bool(a) and (a == b or b.endswith(" " + a))


def expected_artists(hint: IdentityHint | None) -> list[str]:
    """Every artist the video or uploader named: the artist, then one mentioned in the title."""
    if hint is None:
        return []
    return [name.strip() for name in (hint.artist, hint.mentioned_artist) if name and name.strip()]


def needs_composer_check(identity: SongIdentity, hint: IdentityHint | None) -> bool:
    """True when AcoustID named the song but credits someone other than an artist the video/user named.

    Typical for classical music: MusicBrainz credits the recording to the
    performer, while the video names the composer.
    """
    if identity.source is not MetadataSource.ACOUSTID:
        return False
    credited = (identity.raw_artist, *identity.featured_artists)
    return any(
        not any(_same_name(named, name) for name in credited) for named in expected_artists(hint)
    )


def credit_composer(identity: SongIdentity, expected_artist: str, composers: list[str]) -> SongIdentity:
    """Make the composer the artist when the video/user named them; the performer becomes featured.

    Returns ``identity`` unchanged when ``expected_artist`` is none of ``composers``.
    """
    composer = next((c for c in composers if _same_name(expected_artist, c)), None)
    if composer is None:
        return identity
    featured = (identity.raw_artist, *[f for f in identity.featured_artists if not _same_name(f, composer)])
    return SongIdentity(identity.title, composer, identity.source, identity.acoustid_id, featured)


_PREFIX_SEPARATORS = (" - ", " – ", ": ")


def split_composer_prefix(identity: SongIdentity, named_artists: list[str]) -> SongIdentity:
    """Turn "Beethoven - Moonlight Sonata" by a performer into Beethoven's piece featuring the performer.

    Performers on YouTube often put the composer into their recording's title,
    and MusicBrainz copies it. Only a prefix the video/uploader named as the
    artist counts; any other title stays as it is.
    """
    for separator in _PREFIX_SEPARATORS:
        prefix, found, rest = identity.title.partition(separator)
        if not found or not rest.strip():
            continue
        named = next((n for n in named_artists if _same_name(prefix, n) or _same_name(n, prefix)), None)
        if named is not None and not _same_name(prefix, identity.raw_artist):
            featured = (identity.raw_artist, *identity.featured_artists)
            return SongIdentity(rest.strip(), prefix.strip(), identity.source, identity.acoustid_id, featured)
    return identity
