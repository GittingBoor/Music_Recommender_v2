"""Decide whether a YouTube video, and later the recognised audio, is the Spotify track asked for.

Two gates keep wrong songs out of the library:

* ``candidate_fits`` before the download: the video title names the song,
  one of its artists appears in the title or channel, the length fits and the
  video is no live/cover/remix version the Spotify track is not.
* ``identity_matches`` after AcoustID: the fingerprinted title and artist
  must be the Spotify track's, otherwise the download is thrown away.
"""
import difflib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from src.metadata.cleaning import parse_featured_artists, plain_quotes, split_artist_featuring, strip_version_markers
from src.youtube.ranking import _VERSION_WORDS

# Same length ±15 s, or longer by up to a quarter (music videos with intro/outro).
_LENGTH_TOLERANCE_SECONDS = 15
_MAX_LENGTH_FACTOR = 1.25
# Titles this similar count as one song ("Dont Stop Me Now" / "Don't Stop Me Now").
_TITLE_SIMILARITY = 0.85

_FEAT_BRACKET_RE = re.compile(r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s[^\)\]]*[\)\]]", re.IGNORECASE)
_FEAT_TAIL_RE = re.compile(r"\s+(?:-\s+)?(?:feat\.?|ft\.?|featuring)\s.+$", re.IGNORECASE)
_FROM_TAIL_RE = re.compile(r"\s+-\s+from\s.+$", re.IGNORECASE)
_CHANNEL_NOISE_RE = re.compile(r"\s*-\s*topic$|vevo$|\s+official$", re.IGNORECASE)
# "Helene Fischer (Official)" once normalised: trailing marker words of a channel name.
_CHANNEL_TAIL_RE = re.compile(r"(?:\s+(?:official|vevo|topic))+$")
# A remaster of the same recording, not another version ("(Remastered Version)").
_REMASTER_RE = re.compile(r"(?:(?:19|20)\d{2}\s*)?remaster(?:ed)?(?:\s+(?:19|20)\d{2})?(?:\s+version)?", re.IGNORECASE)
_ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|&|\bx\b|\band\b|\bund\b)\s*", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\w]+")
# Other recordings of the same song that the ranking's version words miss.
_EXTRA_VERSION_WORDS = ("take", "demo")
_TOPIC_SUFFIX = " - topic"
# Different titles only count as one song when they are this long and name the same numbers.
_MIN_FUZZY_TITLE_LENGTH = 6
_NUMERAL_RE = re.compile(r"^(?:\d+|i|ii|iii|iv|v|vi|vii|viii|ix|x)$")
# Words an official upload adds around "Artist - Title" ("(Official 4K Music Video)").
_UPLOAD_FILLER_WORDS = frozenset({
    "official", "music", "video", "audio", "lyrics", "lyric", "visualizer", "visualiser", "hd", "hq", "4k",
    "mv", "clip", "feat", "ft", "featuring", "with", "remastered", "remaster", "and", "x", "animated",
})
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")

T = TypeVar("T")


@dataclass(frozen=True)
class SpotifyTrack:
    """A playlist track as Spotify names it; artists[0] is the main artist."""

    spotify_id: str
    title: str
    artists: tuple[str, ...]
    duration_ms: int | None
    isrc: str | None

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else ""

    @property
    def plain_title(self) -> str:
        """Title without remaster/edit markers and guest credits ("Stay (feat. X)" → "Stay")."""
        return _plain_title(self.title)

    @property
    def query(self) -> str:
        """YouTube search text in the "Artist - Title" form the ranking expects."""
        return f"{self.primary_artist} - {self.plain_title}"


def _plain_title(title: str) -> str:
    title = _FEAT_BRACKET_RE.sub("", plain_quotes(title))
    title = _FEAT_TAIL_RE.sub("", title)
    title = _FROM_TAIL_RE.sub("", title)
    return strip_version_markers(title).strip()


def _normalise(text: str) -> str:
    """Lower-case words without accents or punctuation; apostrophes vanish ("Don’t" → "dont")."""
    decomposed = unicodedata.normalize("NFKD", plain_quotes(text).lower().replace("'", ""))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_NON_WORD_RE.sub(" ", plain).replace("_", " ").split())


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {haystack} "


def _length_fits(track_ms: int | None, video_s: int | None) -> bool:
    if track_ms is None:
        return True
    if video_s is None:
        return False
    track_s = track_ms / 1000
    return abs(video_s - track_s) <= _LENGTH_TOLERANCE_SECONDS or track_s <= video_s <= track_s * _MAX_LENGTH_FACTOR


def _unwanted_version(track_title: str, video_title: str) -> bool:
    """The video announces a version (live, cover, remix, …) the Spotify title does not."""
    wanted = _normalise(track_title)
    video_title = _normalise(_REMASTER_RE.sub(" ", video_title))
    return any(
        _contains_phrase(video_title, word) and not _contains_phrase(wanted, word)
        for word in (_normalise(w) for w in (*_VERSION_WORDS, *_EXTRA_VERSION_WORDS))
    )


def _foreign_guest(artists: list[str], video_title: str) -> bool:
    """The video credits a guest ("ft. Che'Nelle") the Spotify track does not have."""
    guests = [_normalise(g) for g in parse_featured_artists(video_title)]
    return any(
        guest and not any(_contains_phrase(guest, a) or _contains_phrase(a, guest) for a in artists)
        for guest in guests
    )


def candidate_fits(track: SpotifyTrack, video_title: str, uploader: str | None, duration_s: int | None) -> bool:
    """True when the video is plausibly exactly this track (checked before downloading)."""
    title_words = _normalise(track.plain_title).split()
    if not title_words:
        return False
    video = _normalise(video_title)
    video_words = set(video.split())
    if not all(word in video_words for word in title_words):
        return False
    channel = _normalise(_CHANNEL_NOISE_RE.sub("", (uploader or "").strip()))
    artists = [_normalise(a) for a in track.artists]
    if not any(_contains_phrase(video, a) or _contains_phrase(channel, a) for a in artists):
        return False
    if _unwanted_version(track.title, video_title) or _foreign_guest(artists, video_title):
        return False
    return _length_fits(track.duration_ms, duration_s)


def order_candidates(
    track: SpotifyTrack, hits: list[T], key: Callable[[T], tuple[str, str | None, int | None]],
) -> list[T]:
    """Topic-channel uploads (the release itself) first, then the closest length.

    ``key`` gives a hit's (title, uploader, duration in seconds). A length that
    matches to the second is the studio recording far more often than a
    longer live cut whose title hides that it is live.
    """
    track_s = (track.duration_ms or 0) / 1000

    def rank(hit: T) -> tuple[int, float]:
        _, uploader, duration = key(hit)
        topic = (uploader or "").lower().endswith(_TOPIC_SUFFIX)
        distance = abs(duration - track_s) if duration is not None and track.duration_ms else 0.0
        return (0 if topic else 1, distance)

    return sorted(hits, key=rank)


def _credited_artists(artist: str) -> set[str]:
    """Every name in a credit: "A feat. B & C" → {"a feat b c", "a", "b", "c"}."""
    main, featured = split_artist_featuring(artist)
    names = {artist, main, *featured, *_ARTIST_SPLIT_RE.split(main)}
    return {_normalise(n) for n in names if n.strip()}


def _numerals(text: str) -> list[str]:
    return [w for w in text.split() if _NUMERAL_RE.match(w)]


def _same_title(wanted: str, found: str) -> bool:
    """Equal, or a near spelling of a long title that names the same numbers ("Part I" ≠ "Part II")."""
    if wanted == found:
        return True
    return (
        min(len(wanted), len(found)) >= _MIN_FUZZY_TITLE_LENGTH
        and _numerals(wanted) == _numerals(found)
        and difflib.SequenceMatcher(None, wanted, found).ratio() >= _TITLE_SIMILARITY
    )


def identity_matches(track: SpotifyTrack, title: str, artist: str) -> bool:
    """True when a recognised title/artist (AcoustID) names this Spotify track."""
    wanted, found = _normalise(track.plain_title), _normalise(_plain_title(title))
    if not wanted or not found or not _same_title(wanted, found):
        return False
    credited = _credited_artists(artist)
    return any(name in credited for a in track.artists for name in _credited_artists(a))


def trusted_upload(track: SpotifyTrack, video_title: str, uploader: str | None) -> bool:
    """True for the artist's own (or Topic) upload titled only "Artist - Title" plus official noise.

    Audio AcoustID does not know is only stored under the Spotify name when
    this holds; a fan upload, mashup, drum cam or festival recording does not.
    """
    artist_names = {name for a in track.artists for name in _credited_artists(a)}
    channel = _CHANNEL_TAIL_RE.sub("", _normalise(_CHANNEL_NOISE_RE.sub("", (uploader or "").strip())))
    if channel not in artist_names:
        return False
    allowed = set(_normalise(track.title).split()) | _UPLOAD_FILLER_WORDS
    allowed |= {word for name in artist_names for word in name.split()}
    leftover = [w for w in _normalise(video_title).split() if w not in allowed and not _YEAR_RE.match(w)]
    return not leftover
