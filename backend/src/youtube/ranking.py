"""Order YouTube search hits so the artist's own studio recording comes first.

Works on the raw entries of a flat search (no extra YouTube call per video):
whether the title names the searched song, who uploaded it, whether YouTube
verified that channel (artists and labels), whether the title announces a
different version, and how often it was viewed.
"""
import math
import re
import unicodedata

_TOPIC_SUFFIX = " - topic"
_CHANNEL_NOISE_RE = re.compile(r"\s*-\s*topic$|vevo$|\s+official$|\s+music$|\s+tv$", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\w\s]")
# "Artist - Song" queries; the left side names the artist, the right side the song.
_QUERY_SEPARATOR_RE = re.compile(r"\s+[-–—]\s+")

# A different version of the song than the one people search for.
_VERSION_WORDS = (
    "live", "cover", "karaoke", "remix", "reaction", "lesson", "tutorial", "transcription",
    "instrumental", "slowed", "sped up", "nightcore", "8d", "loop", "hour", "acoustic",
    "concert", "unplugged", "session", "sessions", "version", "hz",
)

# Query words that say nothing about which song is meant.
_FILLER_WORDS = frozenset({"official", "audio", "video", "music", "lyrics", "lyric", "hd", "hq", "feat", "ft"})

# Share of the searched words found in the title; outweighs every channel bonus,
# so another song on the artist's own channel never beats the searched one.
_TITLE_MATCH_WEIGHT = 8.0
_TOPIC_BONUS = 3.0
_ARTIST_NAMED_BONUS = 3.0
_VERIFIED_BONUS = 2.0
_VERSION_PENALTY = 4.0
# log10(views): 1k → 0.9, 1M → 1.8, 1B → 2.7 — a tiebreaker, not a trump card.
_VIEWS_WEIGHT = 0.3


def _normalise(text: str) -> str:
    """Lower-case words without punctuation or accents ("Gymnopédie" → "gymnopedie")."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_WORD_RE.sub(" ", plain).split())


def _channel_artist(channel: str) -> str:
    return _normalise(_CHANNEL_NOISE_RE.sub("", channel.strip()))


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _title_match(song_words: list[str], title: str) -> float:
    """Share of the searched song's words that appear in the title."""
    if not song_words:
        return 1.0
    title_words = set(title.split())
    return sum(w in title_words for w in song_words) / len(song_words)


def _is_concert_film(raw_title: str) -> bool:
    """ "Rammstein: Paris - Du Hast": a subtitle on the artist side names a concert film or tour."""
    parts = _QUERY_SEPARATOR_RE.split(raw_title.strip(), maxsplit=1)
    return len(parts) == 2 and ":" in parts[0]


def _score(artist_part: str, song_words: list[str], entry: dict) -> float:
    raw_title = str(entry.get("title") or "")
    title = _normalise(raw_title)
    channel = str(entry.get("channel") or entry.get("uploader") or "")
    artist = _channel_artist(channel)
    score = _TITLE_MATCH_WEIGHT * _title_match(song_words, title)

    if channel.lower().endswith(_TOPIC_SUFFIX):
        score += _TOPIC_BONUS
    # The searched artist uploaded it, or the title names them ("Vivaldi - Spring" on a
    # pianist's channel) — not just any song of the same name.
    artist_words = [w for w in artist_part.split() if w not in song_words]
    channel_is_artist = len(artist) >= 2 and _has_word(artist_part, artist)
    title_names_artist = bool(artist_words) and all(_has_word(title, w) for w in artist_words)
    if channel_is_artist or title_names_artist:
        score += _ARTIST_NAMED_BONUS
    if entry.get("channel_is_verified"):
        score += _VERIFIED_BONUS

    wanted = " ".join(song_words)
    if _is_concert_film(raw_title) or any(_has_word(title, w) and not _has_word(wanted, w) for w in _VERSION_WORDS):
        score -= _VERSION_PENALTY

    views = int(entry.get("view_count") or 0)
    score += _VIEWS_WEIGHT * math.log10(views + 1)
    return score


def _split_query(query: str) -> tuple[str, list[str]]:
    """``(artist_part, song_words)``; without an "Artist - Song" separator the whole query is both."""
    parts = _QUERY_SEPARATOR_RE.split(query.strip(), maxsplit=1)
    artist_part, song_part = (parts[0], parts[1]) if len(parts) == 2 else (query, query)
    song_words = [w for w in _normalise(song_part).split() if w not in _FILLER_WORDS]
    return _normalise(artist_part), song_words


def rank_entries(query: str, entries: list[dict]) -> list[dict]:
    """Return ``entries`` best match first; equal scores keep YouTube's order."""
    artist_part, song_words = _split_query(query)
    return sorted(entries, key=lambda e: _score(artist_part, song_words, e), reverse=True)
