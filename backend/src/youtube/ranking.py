"""Order YouTube search hits so the artist's own studio recording comes first.

Works on the raw entries of a flat search (no extra YouTube call per video):
who uploaded it, whether YouTube verified that channel (artists and labels),
whether the title announces a different version, and how often it was viewed.
"""
import math
import re

_TOPIC_SUFFIX = " - topic"
_CHANNEL_NOISE_RE = re.compile(r"\s*-\s*topic$|vevo$|\s+official$|\s+music$|\s+tv$", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\w\s]")

# A different version of the song than the one people search for.
_VERSION_WORDS = (
    "live", "cover", "karaoke", "remix", "reaction", "lesson", "tutorial", "transcription",
    "instrumental", "slowed", "sped up", "nightcore", "8d", "loop", "hour", "acoustic",
)

_TOPIC_BONUS = 3.0
_ARTIST_CHANNEL_BONUS = 3.0
_VERIFIED_BONUS = 2.0
_VERSION_PENALTY = 4.0
# log10(views): 1k → 0.9, 1M → 1.8, 1B → 2.7 — a tiebreaker, not a trump card.
_VIEWS_WEIGHT = 0.3


def _normalise(text: str) -> str:
    return " ".join(_WORD_RE.sub(" ", text.lower()).split())


def _channel_artist(channel: str) -> str:
    return _normalise(_CHANNEL_NOISE_RE.sub("", channel.strip()))


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _score(query: str, entry: dict) -> float:
    title = _normalise(str(entry.get("title") or ""))
    channel = str(entry.get("channel") or entry.get("uploader") or "")
    score = 0.0

    if channel.lower().endswith(_TOPIC_SUFFIX):
        score += _TOPIC_BONUS
    artist = _channel_artist(channel)
    if len(artist) >= 2 and _has_word(query, artist):
        score += _ARTIST_CHANNEL_BONUS
    if entry.get("channel_is_verified"):
        score += _VERIFIED_BONUS

    if any(_has_word(title, w) and not _has_word(query, w) for w in _VERSION_WORDS):
        score -= _VERSION_PENALTY

    views = int(entry.get("view_count") or 0)
    score += _VIEWS_WEIGHT * math.log10(views + 1)
    return score


def rank_entries(query: str, entries: list[dict]) -> list[dict]:
    """Return ``entries`` best match first; equal scores keep YouTube's order."""
    normalised_query = _normalise(query)
    return sorted(entries, key=lambda e: _score(normalised_query, e), reverse=True)
