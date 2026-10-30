"""Turn a Spotify playlist into bulk-queue jobs and keep track of what became of each track.

Every track gets a row in ``playlist_import_tracks``: songs already in the
library are marked duplicate right away, the rest are queued and updated by
the bulk worker when it is done with them. Rows still queued when the backend
stops are queued again by ``resume`` on the next start.

The import also keeps the user's playlist view (src.spotify.library) current:
known songs are linked at the start, each further song as soon as it is in.
"""
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.db.models import PlaylistImport, PlaylistImportTrack, Song
from src.ingest.bulk import BulkItem
from src.ingest.failures import reason_category
from src.spotify import library
from src.spotify.client import PlaylistSummary
from src.spotify.matching import SpotifyTrack
from src.youtube.library_match import LibraryMatcher

logger = logging.getLogger(__name__)

_MAX_REASON_LENGTH = 64

QUEUED = "queued"
SAVED = "saved"
DUPLICATE = "duplicate"
FAILED = "failed"


def library_matcher(db: Session) -> LibraryMatcher:
    return LibraryMatcher([(title, artist) for title, artist in db.query(Song.title, Song.artist).all()])


def _library_song_id(track: SpotifyTrack, matcher: LibraryMatcher) -> str | None:
    # Exact song ids only: a fuzzy title match would take "Over My Dead Body" for "Over".
    return next((sid for sid in library.candidate_song_ids(track.plain_title, track.artists)
                 if matcher.has_song_id(sid)), None)


def _known_song_id(db: Session, row: PlaylistImportTrack) -> str | None:
    """The library song an import track names exactly, for duplicates found without a song id."""
    track = _track_of(row)
    for song_id in library.candidate_song_ids(track.plain_title, track.artists):
        if db.get(Song, song_id) is not None:
            return song_id
    return None


def artists_of(row: PlaylistImportTrack) -> list[str]:
    return list(json.loads(row.artists))


def _track_of(row: PlaylistImportTrack) -> SpotifyTrack:
    return SpotifyTrack(
        spotify_id=row.spotify_track_id, title=row.title, artists=tuple(artists_of(row)),
        duration_ms=row.duration_ms, isrc=row.isrc,
    )


class PlaylistImporter:
    """Starts playlist imports and records the bulk worker's verdict per track."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        enqueue: Callable[[list[BulkItem]], int],
        library: Callable[[Session], LibraryMatcher] = library_matcher,
    ) -> None:
        self._session_factory = session_factory
        self._enqueue = enqueue
        self._library = library

    def start(self, user_id: int, playlist: PlaylistSummary, tracks: list[SpotifyTrack]) -> int:
        """Store the import, mark known songs as duplicate, queue the rest; returns the import id."""
        db = self._session_factory()
        try:
            matcher = self._library(db)
            entry = PlaylistImport(user_id=user_id, spotify_playlist_id=playlist.id, name=playlist.name)
            db.add(entry)
            db.flush()
            seen: dict[str, str | None] = {}
            queued: list[tuple[PlaylistImportTrack, SpotifyTrack]] = []
            for position, track in enumerate(tracks):
                repeated = track.spotify_id in seen
                song_id = seen[track.spotify_id] if repeated else _library_song_id(track, matcher)
                known = repeated or song_id is not None
                seen[track.spotify_id] = song_id
                row = PlaylistImportTrack(
                    import_id=entry.id, position=position, spotify_track_id=track.spotify_id,
                    title=track.title, artists=json.dumps(list(track.artists), ensure_ascii=False),
                    duration_ms=track.duration_ms, isrc=track.isrc, status=DUPLICATE if known else QUEUED,
                    song_id=song_id, finished_at=datetime.now(timezone.utc) if known else None,
                )
                db.add(row)
                if not known:
                    queued.append((row, track))
            db.flush()
            library.store_playlist(
                db, user_id, playlist.id, playlist.name, playlist.image, tracks,
                snapshot_id=playlist.snapshot_id, collaborative=playlist.collaborative,
            )
            db.commit()
            import_id = entry.id
            items = [self._item(row.id, track) for row, track in queued]
        finally:
            db.close()
        self._enqueue(items)
        logger.info("[Spotify] Import %d of %r: %d tracks, %d queued", import_id, playlist.name, len(tracks), len(items))
        return import_id

    def record(self, track_row_id: int, result: dict, video_id: str | None) -> None:
        """Store what the bulk worker made of one track."""
        reason: str | None = None
        if result.get("status") == SAVED:
            status = SAVED
        elif result.get("reason") == DUPLICATE:
            status = DUPLICATE
        else:
            # A category, never a raw exception text: the UI shows it to the user.
            status, reason = FAILED, reason_category(result)
        db = self._session_factory()
        try:
            row = db.get(PlaylistImportTrack, track_row_id)
            if row is None:
                logger.warning("[Spotify] Import track %d vanished before its result arrived", track_row_id)
                return
            row.status = status
            row.reason = reason[:_MAX_REASON_LENGTH] if reason else None
            row.song_id = result.get("song_id")
            if status == DUPLICATE and not row.song_id:
                # A duplicate found by video title carries no song id.
                row.song_id = _known_song_id(db, row)
            row.video_id = video_id
            row.finished_at = datetime.now(timezone.utc)
            if row.song_id and status in (SAVED, DUPLICATE):
                entry = db.get(PlaylistImport, row.import_id)
                if entry is not None:
                    library.link_song(db, entry.user_id, entry.spotify_playlist_id, row.song_id, row.position)
            db.commit()
        finally:
            db.close()

    def retry_failed(self, import_id: int) -> int:
        """Queue the import's failed tracks once more; returns how many."""
        db = self._session_factory()
        try:
            rows = (
                db.query(PlaylistImportTrack)
                .filter(PlaylistImportTrack.import_id == import_id, PlaylistImportTrack.status == FAILED)
                .order_by(PlaylistImportTrack.position)
                .all()
            )
            for row in rows:
                row.status, row.reason, row.song_id, row.video_id, row.finished_at = QUEUED, None, None, None, None
            db.commit()
            items = [self._item(row.id, _track_of(row)) for row in rows]
        finally:
            db.close()
        if items:
            self._enqueue(items)
            logger.info("[Spotify] Import %d: %d failed tracks queued again", import_id, len(items))
        return len(items)

    def resume(self) -> int:
        """Queue every track still marked queued (the in-memory queue died with the last process)."""
        db = self._session_factory()
        try:
            rows = (
                db.query(PlaylistImportTrack)
                .filter(PlaylistImportTrack.status == QUEUED)
                .order_by(PlaylistImportTrack.import_id, PlaylistImportTrack.position)
                .all()
            )
            items = [self._item(row.id, _track_of(row)) for row in rows]
        finally:
            db.close()
        if items:
            self._enqueue(items)
            logger.info("[Spotify] Resumed %d queued playlist tracks", len(items))
        return len(items)

    def _item(self, track_row_id: int, track: SpotifyTrack) -> BulkItem:
        label = f"{', '.join(track.artists)} – {track.title}"
        return BulkItem(
            query=track.query, label=label, expected=track,
            on_done=lambda result, video_id: self.record(track_row_id, result, video_id),
        )
