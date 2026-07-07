"""Pure text/date helpers shared by all metadata providers. No network access."""
import difflib
import re

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Patterns inside () or [] that are video/platform noise and not part of the real title.
# Covers YouTube upload conventions, quality labels, release variants, and platform markers.
_NOISE_BRACKET_RE = re.compile(
    r'\s*[\(\[]\s*(?:'
    # Official variants
    r'official\s*(?:music\s+)?(?:video|audio|lyric(?:s)?\s*video?|lyrics?|visuali[sz]er|clip|'
    r'performance(?:\s+video)?|live(?:\s+video)?|mv)?\b|'
    r'official\s*artist\s*channel|'
    # Video type
    r'music\s*video|video\s*clip|lyric(?:s)?\s*video|lyrics?|audio|visuali[sz]er|'
    # Quality / resolution
    r'full\s*hd|hd|hq|4k|2160p|1440p|1080p|720p|480p|360p|'
    # Remaster variants (with optional year)
    r'(?:(?:19|20)\d{2}\s*)?remaster(?:ed)?(?:\s+(?:19|20)\d{2})?|'
    # Platform / distribution markers
    r'auto[\s\-]?generated|ncs\s*(?:release)?|vevo|'
    # Standalone year
    r'(?:19|20)\d{2}'
    r')[^\)\]]*[\)\]]',
    re.IGNORECASE,
)

# "Artist - Song - Official Video"  →  strip " - Official Video" suffix
_TRAILING_DASH_NOISE_RE = re.compile(
    r'\s+-\s+(?:official\s*(?:music\s+)?(?:video|audio|lyrics?|clip|mv)?|'
    r'music\s*video|lyrics?|audio|visuali[sz]er|hd|hq|4k)\s*$',
    re.IGNORECASE,
)

# YouTube auto-generated: "Song | Artist - Topic"  or  "Song | Official Video"
_PIPE_NOISE_RE = re.compile(
    r'\s*\|\s*(?:official\s*(?:music\s+)?(?:video|audio|mv)?|'
    r'music\s*video|lyrics?|audio|visuali[sz]er|'
    r'.+?\s*-\s*topic)\s*$',
    re.IGNORECASE,
)

_FEAT_IN_ARTIST_RE = re.compile(
    r'\s*(?:feat\.?|ft\.?|featuring)\s+.+$',
    re.IGNORECASE,
)


def clean_title(text: str) -> str:
    """Remove common YouTube/video-upload noise from a song title or artist string."""
    text = _NOISE_BRACKET_RE.sub("", text)
    text = _TRAILING_DASH_NOISE_RE.sub("", text)
    text = _PIPE_NOISE_RE.sub("", text)
    return text.strip(" -_.")


def strip_html(text: str) -> str:
    text = re.sub(r'<a[^>]*>.*?</a>', '', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def normalize_date(raw: str | None) -> str | None:
    """Normalize various date formats to YYYY-MM-DD or YYYY."""
    if not raw:
        return None
    raw = raw.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        return raw
    if re.match(r'^\d{8}$', raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if re.match(r'^\d{4}$', raw):
        return raw
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', raw)
    if m:
        day = m.group(1).zfill(2)
        mon = _MONTH_MAP.get(m.group(2).lower())
        year = m.group(3)
        return f"{year}-{mon}-{day}" if mon else year
    m = re.match(r'^(\d{4})[/.](\d{2})[/.](\d{2})$', raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'\b(19|20)\d{2}\b', raw)
    return m.group(0) if m else None


def parse_featured_artists(title: str) -> list[str]:
    patterns = [
        r'\(feat\.?\s+([^)]+)\)',
        r'\(ft\.?\s+([^)]+)\)',
        r'\(featuring\s+([^)]+)\)',
        r'\[feat\.?\s+([^\]]+)\]',
        r'\[ft\.?\s+([^\]]+)\]',
        r'\[featuring\s+([^\]]+)\]',
        r'\bfeat\.?\s+([^(\[,\]]+)',
        r'\bft\.?\s+([^(\[,\]]+)',
        r'\bfeaturing\s+([^(\[,\]]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            artists_str = match.group(1).strip().rstrip(')]')
            artists = re.split(r'\s*[&,]\s*|\s+x\s+|\s+and\s+', artists_str, flags=re.IGNORECASE)
            return [a.strip().rstrip('])') for a in artists if a.strip()]
    return []


def dedup_featured_artists(artists: list[str]) -> list[str]:
    """Deduplicate featured artists, keeping the longer/more complete name when one is a substring of another."""
    if not artists:
        return artists
    normalized = [a.lower().strip() for a in artists]
    kept: list[str] = []
    for i, (n, original) in enumerate(zip(normalized, artists)):
        # Skip if a longer version already exists (e.g. "Pharrell" when "Pharrell Williams" is present)
        dominated = any(
            j != i and n in normalized[j] and len(normalized[j]) > len(n)
            for j in range(len(normalized))
        )
        if not dominated and original not in kept:
            kept.append(original)
    return kept


def split_artist_featuring(artist_str: str) -> tuple[str, list[str]]:
    """Split 'David Guetta Feat. Kid Cudi' → ('David Guetta', ['Kid Cudi'])."""
    featured = parse_featured_artists(artist_str)
    if not featured:
        return artist_str, []
    clean = _FEAT_IN_ARTIST_RE.sub("", artist_str).strip()
    return clean, featured


def title_similar(queried: str, returned: str, threshold: float = 0.6) -> bool:
    """Return True if a provider-returned title is close enough to what we searched for.

    Normalise both strings (lowercase, strip punctuation) then accept if:
    - one is a substring of the other, OR
    - SequenceMatcher ratio >= threshold
    """
    def normalise(s: str) -> str:
        return re.sub(r"[^\w\s]", "", s.lower()).strip()

    q = normalise(queried)
    r = normalise(returned)
    if not q or not r:
        return False
    if q in r or r in q:
        return True
    return difflib.SequenceMatcher(None, q, r).ratio() >= threshold


def date_precision(d: str) -> int:
    """Return a precision score: 3=YYYY-MM-DD, 2=YYYY-MM, 1=YYYY, 0=empty."""
    if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
        return 3
    if re.match(r'^\d{4}-\d{2}$', d):
        return 2
    if re.match(r'^\d{4}$', d):
        return 1
    return 0


def better_date(current: str, candidate: str) -> str:
    """Return the preferred date: more precise wins; equal precision → earlier wins."""
    if not current:
        return candidate
    if not candidate:
        return current
    cp = date_precision(current)
    kp = date_precision(candidate)
    if kp > cp:
        return candidate
    if kp < cp:
        return current
    return candidate if candidate < current else current
