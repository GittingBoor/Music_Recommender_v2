from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a"}
_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"

_NOISE_RE = re.compile(
    r'\s*[\(\[]\s*(?:'
    r'official\s*(?:video|audio|lyrics?|music\s*video)|'
    r'lyrics?|hd|hq|4k|'
    r'remaster(?:ed)?|live|acoustic|'
    r'radio\s*edit|extended|remix|'
    r'explicit|clean|visualizer'
    r')[^\)\]]*[\)\]]',
    re.IGNORECASE,
)

_FEATURED_RE = re.compile(
    r'\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+([^\)\]]+?)\s*[\)\]]',
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r'[\(\[]((?:19|20)\d{2})[\)\]]')
_TRACK_PREFIX_RE = re.compile(r'^(\d{1,3})\s*[.\-]\s*')


@dataclass
class _ParseResult:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_number: str | None = None
    featured_artist: str | None = None
    year: str | None = None


def _clean_stem(stem: str) -> tuple[str, str | None, str | None]:
    """Strip noise, extract featured artist and year. Returns (cleaned, featured, year)."""
    featured: str | None = None
    year: str | None = None

    m = _FEATURED_RE.search(stem)
    if m:
        featured = m.group(1).strip()
        stem = stem[:m.start()] + stem[m.end():]

    m = _YEAR_RE.search(stem)
    if m:
        year = m.group(1)
        stem = stem[:m.start()] + stem[m.end():]

    stem = _NOISE_RE.sub("", stem).strip(" -_.[]() ")
    return stem, featured, year


def _try_parse_filename(stem: str) -> _ParseResult | None:
    stem, featured, year = _clean_stem(stem)
    if not stem:
        return None

    track_num: str | None = None
    m = _TRACK_PREFIX_RE.match(stem)
    if m:
        track_num = m.group(1)
        stem = stem[m.end():].strip()

    result = _ParseResult(track_number=track_num, featured_artist=featured, year=year)

    if " - " in stem:
        parts = [p.strip() for p in stem.split(" - ")]

        if len(parts) == 2:
            # Default: "Artist - Title". Validation step will catch if it's actually swapped.
            result.artist, result.title = parts[0], parts[1]
            return result

        if len(parts) == 3:
            result.artist, result.album, result.title = parts[0], parts[1], parts[2]
            return result

        if len(parts) > 3:
            result.artist, result.title = parts[0], parts[-1]
            return result

    # "Artist_Title" — underscore-only, no spaces
    if "_" in stem and " " not in stem:
        parts = stem.split("_", 1)
        if parts[0] and parts[1]:
            result.artist = parts[0].replace("_", " ")
            result.title = parts[1].replace("_", " ")
            return result

    # Single token — treat as title only
    if stem:
        result.title = stem
        return result

    return None


def _lastfm_track_exists(artist: str, title: str, api_key: str) -> bool:
    """Return True if Last.fm knows this artist+title combination."""
    params = urllib.parse.urlencode({
        "method": "track.getInfo",
        "api_key": api_key,
        "artist": artist,
        "track": title,
        "format": "json",
        "autocorrect": 1,
    })
    try:
        with urllib.request.urlopen(f"{_LASTFM_BASE}?{params}", timeout=5) as resp:
            data = json.loads(resp.read().decode())
        # error 6 = Track not found, error 7 = Invalid resource
        return "error" not in data and "track" in data
    except Exception:
        return False


def _musicbrainz_track_exists(artist: str, title: str) -> bool:
    """Return True if MusicBrainz search returns a high-confidence match."""
    try:
        import musicbrainzngs
        results = musicbrainzngs.search_recordings(
            recording=title, artistname=artist, limit=1
        )
        recordings = results.get("recording-list", [])
        if recordings and int(recordings[0].get("ext:score", 0)) >= 80:
            return True
    except Exception:
        pass
    return False


def _extract_isrc_raw(audio_raw: Any) -> str | None:
    tags = audio_raw.tags
    if tags is None:
        return None
    # ID3 (MP3)
    if hasattr(tags, "getall"):
        tsrc = tags.getall("TSRC")
        if tsrc:
            return str(tsrc[0])
    # FLAC / Vorbis
    if hasattr(tags, "get"):
        for key in ("ISRC", "isrc"):
            val = tags.get(key)
            if val:
                return str(val[0]) if isinstance(val, list) else str(val)
    # MP4 freeform atoms
    if hasattr(tags, "keys"):
        for key in tags.keys():
            if "isrc" in str(key).lower():
                val = tags[key]
                if val:
                    return str(val[0]) if isinstance(val, (list, tuple)) else str(val)
    return None


class SongMetadataExtractor:
    """
    Extract song metadata from an audio file using a 3-step chain:
    1. Embedded tags (mutagen)
    2. Filename pattern parsing — validated via Last.fm or MusicBrainz to catch
       swapped "Title - Artist" filenames
    3. Audio fingerprinting via AcoustID + MusicBrainz
    """

    def __init__(
        self,
        acoustid_api_key: str = "",
        lastfm_api_key: str = "",
        mb_useragent: tuple[str, str, str] = ("MusicRecommender", "0.1", "user@example.com"),
    ) -> None:
        self._acoustid_key = acoustid_api_key
        self._lastfm_key = lastfm_api_key
        self._mb_useragent = mb_useragent

    def extract(self, audio_path: str | Path) -> dict[str, Any]:
        path = Path(audio_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format '{path.suffix}'. Supported: {sorted(_SUPPORTED_EXTENSIONS)}"
            )

        result: dict[str, Any] = {
            "title": None,
            "artist": None,
            "album": None,
            "year": None,
            "genre": None,
            "track_number": None,
            "duration_seconds": None,
            "isrc": None,
            "label": None,
            "source": [],
        }

        self._apply_embedded_tags(path, result)

        if result["title"] is None or result["artist"] is None:
            self._apply_filename_parse(path, result)

        if result["title"] is None or result["artist"] is None:
            self._apply_acoustid(path, result)

        missing = [k for k, v in result.items() if v is None and k != "source"]
        if missing:
            logger.warning(
                "Incomplete metadata for %s. Missing fields: %s", path.name, missing
            )

        return result

    # ------------------------------------------------------------------
    # Step 1 — Embedded tags
    # ------------------------------------------------------------------

    def _apply_embedded_tags(self, path: Path, result: dict[str, Any]) -> None:
        try:
            from mutagen import File as MutagenFile
        except ImportError:
            logger.warning("mutagen not installed — skipping embedded tags")
            return

        audio = MutagenFile(path, easy=True)
        if audio is None:
            return

        tags = audio.tags or {}

        def tag(key: str) -> str | None:
            val = tags.get(key)
            if not val:
                return None
            return str(val[0]) if isinstance(val, list) else str(val)

        if audio.info:
            result["duration_seconds"] = round(float(audio.info.length), 2)

        changed = False
        for field_name, tag_key in [
            ("title", "title"),
            ("artist", "artist"),
            ("album", "album"),
            ("genre", "genre"),
        ]:
            if result[field_name] is None:
                val = tag(tag_key)
                if val:
                    result[field_name] = val
                    changed = True

        if result["year"] is None:
            raw_date = tag("date")
            if raw_date:
                m = re.search(r"(19|20)\d{2}", raw_date)
                if m:
                    result["year"] = m.group(0)
                    changed = True

        if result["track_number"] is None:
            tn = tag("tracknumber")
            if tn:
                result["track_number"] = tn.split("/")[0].strip()
                changed = True

        # ISRC is not exposed in easy tags — re-open raw
        if result["isrc"] is None:
            audio_raw = MutagenFile(path, easy=False)
            if audio_raw:
                isrc = _extract_isrc_raw(audio_raw)
                if isrc:
                    result["isrc"] = isrc
                    changed = True

        if changed or result["duration_seconds"] is not None:
            result["source"].append("embedded_tags")

    # ------------------------------------------------------------------
    # Step 2 — Filename parsing + swap validation
    # ------------------------------------------------------------------

    def _apply_filename_parse(self, path: Path, result: dict[str, Any]) -> None:
        parsed = _try_parse_filename(path.stem)
        if parsed is None:
            return

        # Only validate when we got both artist and title from parsing —
        # that's the only case where a swap could produce plausible-looking results.
        if parsed.artist and parsed.title:
            corrected = self._validate_artist_title(parsed.artist, parsed.title)
            if corrected:
                parsed.artist, parsed.title = corrected

        changed = False
        if result["title"] is None and parsed.title:
            result["title"] = parsed.title
            changed = True
        if result["artist"] is None and parsed.artist:
            artist = parsed.artist
            if parsed.featured_artist:
                artist = f"{artist} feat. {parsed.featured_artist}"
            result["artist"] = artist
            changed = True
        if result["album"] is None and parsed.album:
            result["album"] = parsed.album
            changed = True
        if result["track_number"] is None and parsed.track_number:
            result["track_number"] = parsed.track_number
            changed = True
        if result["year"] is None and parsed.year:
            result["year"] = parsed.year
            changed = True

        if changed:
            result["source"].append("filename_parse")

    def _validate_artist_title(self, artist: str, title: str) -> tuple[str, str] | None:
        """
        Check whether artist+title exists. If not, try the swapped order.
        Returns the correct (artist, title) tuple, or None if unverifiable.
        Uses Last.fm if a key is set, otherwise falls back to MusicBrainz.
        """
        if self._lastfm_key:
            return self._validate_via_lastfm(artist, title)
        return self._validate_via_musicbrainz(artist, title)

    def _validate_via_lastfm(self, artist: str, title: str) -> tuple[str, str] | None:
        if _lastfm_track_exists(artist, title, self._lastfm_key):
            logger.debug("[Validate] Last.fm confirmed: %s — %s", artist, title)
            return artist, title

        if _lastfm_track_exists(title, artist, self._lastfm_key):
            logger.info(
                "[Validate] Last.fm: artist/title were swapped — correcting to: %s — %s",
                title, artist,
            )
            return title, artist

        logger.debug("[Validate] Last.fm: neither order found for '%s' / '%s'", artist, title)
        return None

    def _validate_via_musicbrainz(self, artist: str, title: str) -> tuple[str, str] | None:
        try:
            import musicbrainzngs
        except ImportError:
            return None

        app, version, contact = self._mb_useragent
        musicbrainzngs.set_useragent(app, version, contact)

        if _musicbrainz_track_exists(artist, title):
            logger.debug("[Validate] MusicBrainz confirmed: %s — %s", artist, title)
            return artist, title

        if _musicbrainz_track_exists(title, artist):
            logger.info(
                "[Validate] MusicBrainz: artist/title were swapped — correcting to: %s — %s",
                title, artist,
            )
            return title, artist

        logger.debug("[Validate] MusicBrainz: neither order found for '%s' / '%s'", artist, title)
        return None

    # ------------------------------------------------------------------
    # Step 3 — AcoustID fingerprinting + MusicBrainz
    # ------------------------------------------------------------------

    def _apply_acoustid(self, path: Path, result: dict[str, Any]) -> None:
        if not self._acoustid_key:
            logger.info("[AcoustID] Skipped — no API key configured")
            return

        try:
            import acoustid
        except ImportError:
            logger.warning("pyacoustid not installed — skipping fingerprinting")
            return

        try:
            matches = list(acoustid.match(self._acoustid_key, str(path)))
        except Exception as exc:
            logger.warning("[AcoustID] Fingerprinting failed: %s", exc)
            return

        if not matches:
            logger.info("[AcoustID] No match found for %s", path.name)
            return

        score, recording_id, lfm_title, lfm_artist = max(matches, key=lambda x: x[0])
        if score < 0.5:
            logger.info("[AcoustID] Best match score %.2f below threshold — skipping", score)
            return

        logger.info("[AcoustID] Match: score=%.2f, recording=%s", score, recording_id)
        result["source"].append("acoustid")

        if result["title"] is None and lfm_title:
            result["title"] = lfm_title
        if result["artist"] is None and lfm_artist:
            result["artist"] = lfm_artist

        if recording_id:
            self._apply_musicbrainz(recording_id, result)

    def _apply_musicbrainz(self, recording_id: str, result: dict[str, Any]) -> None:
        try:
            import musicbrainzngs
        except ImportError:
            logger.warning("musicbrainzngs not installed — skipping MusicBrainz lookup")
            return

        app, version, contact = self._mb_useragent
        musicbrainzngs.set_useragent(app, version, contact)

        try:
            mb_result = musicbrainzngs.get_recording_by_id(
                recording_id,
                includes=["artists", "releases", "isrcs"],
            )
        except Exception as exc:
            logger.warning("[MusicBrainz] Recording lookup failed for %s: %s", recording_id, exc)
            return

        recording = mb_result.get("recording", {})
        result["source"].append("musicbrainz")
        logger.info("[MusicBrainz] Found: %s", recording.get("title"))

        if result["title"] is None:
            result["title"] = recording.get("title")

        if result["artist"] is None:
            credits = recording.get("artist-credit", [])
            names = [
                c["artist"]["name"]
                for c in credits
                if isinstance(c, dict) and "artist" in c
            ]
            if names:
                result["artist"] = " & ".join(names)

        if result["isrc"] is None:
            isrc_list = recording.get("isrc-list", [])
            if isrc_list:
                result["isrc"] = isrc_list[0]

        releases = recording.get("release-list", [])
        if not releases:
            return

        release = releases[0]
        if result["album"] is None:
            result["album"] = release.get("title")
        if result["year"] is None:
            m = re.search(r"(19|20)\d{2}", release.get("date", ""))
            if m:
                result["year"] = m.group(0)
        if result["label"] is None and release.get("id"):
            self._fetch_release_label(release["id"], result)

    def _fetch_release_label(self, release_id: str, result: dict[str, Any]) -> None:
        try:
            import musicbrainzngs
            mb_result = musicbrainzngs.get_release_by_id(release_id, includes=["labels"])
            label_info = mb_result.get("release", {}).get("label-info-list", [])
            if label_info:
                entry = label_info[0]
                if isinstance(entry, dict) and "label" in entry:
                    result["label"] = entry["label"].get("name")
        except Exception as exc:
            logger.warning("[MusicBrainz] Label lookup failed for release %s: %s", release_id, exc)


def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python song_metadata_extractor.py <audio_file> [acoustid_api_key]")
        sys.exit(1)

    audio_path = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else ""

    extractor = SongMetadataExtractor(
        acoustid_api_key=api_key,
        mb_useragent=("MusicRecommender", "0.1", "example@email.com"),
    )
    metadata = extractor.extract(audio_path)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


# SETUP REQUIRED:
# - AcoustID API Key: https://acoustid.org/login (kostenlos, registrieren)
# - fpcalc binary: https://acoustid.org/chromaprint (herunterladen, in PATH)
# - pip install mutagen pyacoustid musicbrainzngs
# MusicBrainz braucht KEINEN API Key, aber setze einen User-Agent:
# musicbrainzngs.set_useragent("AppName", "0.1", "deine@email.com")
