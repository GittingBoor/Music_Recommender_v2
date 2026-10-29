"""Which library songs are in a user's Spotify playlists (user_playlists / user_playlist_songs).

Songs belong to everyone; a playlist is one user's view on them. A Spotify
track is found in the library in two ways: a playlist import that already
ended in a song (any user's — the song is shared), or the exact song id its
title and one of its artists give.

A sync reads from Spotify only what changed since the last one (see
UserPlaylist.snapshot_id): Spotify's quota for the app is small.
"""
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.db.models import PlaylistImportTrack, Song, UserPlaylist, UserPlaylistSong, generate_song_id
from src.db.models.user_playlist import LIKED, LIKED_ID, PLAYLIST
from src.metadata.cleaning import plain_quotes, strip_version_markers
from src.spotify.client import SpotifyApiError, SpotifyClient
from src.spotify.matching import SpotifyTrack

logger = logging.getLogger(__name__)

LIKED_NAME = "Lieblingssongs"


def candidate_song_ids(title: str, artists: Iterable[str]) -> list[str]:
    """Song ids the track would have in the library, one per artist (title without version markers)."""
    plain = plain_quotes(strip_version_markers(title))
    return [generate_song_id(plain, plain_quotes(a)) for a in artists]


def resolve_song_ids(db: Session, tracks: list[SpotifyTrack]) -> dict[str, str]:
    """``{spotify track id: song id}`` for the tracks that are in the library."""
    if not tracks:
        return {}
    spotify_ids = {t.spotify_id for t in tracks}
    imported = dict(
        db.query(PlaylistImportTrack.spotify_track_id, PlaylistImportTrack.song_id)
        .join(Song, Song.id == PlaylistImportTrack.song_id)
        .filter(PlaylistImportTrack.spotify_track_id.in_(spotify_ids))
        .all()
    )
    candidates = {t.spotify_id: candidate_song_ids(t.plain_title, t.artists) for t in tracks}
    wanted = {sid for ids in candidates.values() for sid in ids}
    existing = {sid for (sid,) in db.query(Song.id).filter(Song.id.in_(wanted)).all()} if wanted else set()
    found: dict[str, str] = {}
    for track in tracks:
        song_id = imported.get(track.spotify_id) or next(
            (sid for sid in candidates[track.spotify_id] if sid in existing), None,
        )
        if song_id:
            found[track.spotify_id] = song_id
    return found


def _playlist(db: Session, user_id: int, spotify_playlist_id: str) -> UserPlaylist | None:
    return (
        db.query(UserPlaylist)
        .filter(UserPlaylist.user_id == user_id, UserPlaylist.spotify_playlist_id == spotify_playlist_id)
        .one_or_none()
    )


def store_playlist(
    db: Session,
    user_id: int,
    spotify_playlist_id: str,
    name: str,
    image: str | None,
    tracks: list[SpotifyTrack],
    kind: str = PLAYLIST,
    snapshot_id: str | None = None,
) -> UserPlaylist:
    """Create or replace the user's copy of the playlist with the tracks Spotify lists now (no commit)."""
    entry = _playlist(db, user_id, spotify_playlist_id)
    if entry is None:
        entry = UserPlaylist(user_id=user_id, spotify_playlist_id=spotify_playlist_id, kind=kind)
        db.add(entry)
    entry.name = name
    entry.image = image
    entry.track_count = len({t.spotify_id for t in tracks})
    entry.synced_at = datetime.now(timezone.utc)
    entry.snapshot_id = snapshot_id
    entry.tracks = [{"id": t.spotify_id, "title": t.title, "artists": list(t.artists)} for t in tracks]
    db.flush()
    db.query(UserPlaylistSong).filter(UserPlaylistSong.playlist_id == entry.id).delete()
    found = resolve_song_ids(db, tracks)
    positions: dict[str, int] = {}
    for position, track in enumerate(tracks):
        song_id = found.get(track.spotify_id)
        if song_id and song_id not in positions:
            positions[song_id] = position
    db.add_all(UserPlaylistSong(playlist_id=entry.id, song_id=s, position=p) for s, p in positions.items())
    return entry


def store_liked(db: Session, user_id: int, tracks: list[SpotifyTrack], version: str | None = None) -> UserPlaylist:
    return store_playlist(db, user_id, LIKED_ID, LIKED_NAME, None, tracks, kind=LIKED, snapshot_id=version)


def _stored_tracks(db: Session, user_id: int, spotify_playlist_id: str, version: str | None) -> list[SpotifyTrack] | None:
    """The track list stored for this version of the playlist; None when it has to be read again."""
    entry = _playlist(db, user_id, spotify_playlist_id)
    if version is None or entry is None or entry.snapshot_id != version or entry.tracks is None:
        return None
    return _as_tracks(entry.tracks)


def _as_tracks(stored: list) -> list[SpotifyTrack]:
    return [
        SpotifyTrack(spotify_id=t["id"], title=t["title"], artists=tuple(t["artists"]), duration_ms=None, isrc=None)
        for t in stored
    ]


@dataclass(frozen=True)
class SyncResult:
    # Playlists (saved tracks included) read from Spotify / unchanged and matched from the stored list.
    read: int
    unchanged: int
    # The connection predates the saved-tracks permission; reconnecting grants it.
    liked_needs_reconnect: bool


def sync(db: Session, user_id: int, client: SpotifyClient) -> SyncResult:
    """Compare the user's playlists and saved tracks with Spotify and match them with the library.

    Commits after each playlist, so what was read survives a rate limit halfway
    and the next sync starts after it. Raises SpotifyApiError (except a 403 on
    the saved tracks, which means the missing scope).
    """
    read = unchanged = 0
    playlists = client.playlists()
    for playlist in playlists:
        tracks = _stored_tracks(db, user_id, playlist.id, playlist.snapshot_id)
        if tracks is None:
            tracks = client.playlist_tracks(playlist.id)
            read += 1
        else:
            unchanged += 1
        store_playlist(db, user_id, playlist.id, playlist.name, playlist.image, tracks, snapshot_id=playlist.snapshot_id)
        db.commit()
    liked_needs_reconnect = False
    try:
        version = client.liked_version()
        liked = _stored_tracks(db, user_id, LIKED_ID, version)
        if liked is None:
            liked = client.liked_tracks()
            read += 1
        else:
            unchanged += 1
        store_liked(db, user_id, liked, version)
    except SpotifyApiError as exc:
        # The playlists just worked, so a 403 here is the missing user-library-read scope.
        if exc.status != 403:
            raise
        logger.info("[Spotify] User %d: saved tracks need a reconnect (scope)", user_id)
        liked_needs_reconnect = True
    remove_missing(db, user_id, {p.id for p in playlists})
    db.commit()
    return SyncResult(read=read, unchanged=unchanged, liked_needs_reconnect=liked_needs_reconnect)


def sync_one(db: Session, entry: UserPlaylist, client: SpotifyClient) -> bool:
    """Compare one playlist (or the saved tracks) with Spotify; True when its tracks were read again.

    Costs one request while unchanged. Commits. Raises SpotifyApiError (404: the
    playlist is gone on Spotify).
    """
    if entry.kind == LIKED:
        version = client.liked_version()
        tracks = _stored_tracks(db, entry.user_id, LIKED_ID, version)
        changed = tracks is None
        store_liked(db, entry.user_id, client.liked_tracks() if changed else tracks, version)
    else:
        playlist = client.playlist(entry.spotify_playlist_id)
        tracks = _stored_tracks(db, entry.user_id, playlist.id, playlist.snapshot_id)
        changed = tracks is None
        if changed:
            tracks = client.playlist_tracks(playlist.id)
        store_playlist(
            db, entry.user_id, playlist.id, playlist.name, playlist.image, tracks, snapshot_id=playlist.snapshot_id,
        )
    db.commit()
    return changed


def link_song(db: Session, user_id: int, spotify_playlist_id: str, song_id: str, position: int) -> None:
    """Add one song an import has just brought into the library to the user's playlist (no commit)."""
    entry = _playlist(db, user_id, spotify_playlist_id)
    if entry is None or db.get(Song, song_id) is None:
        return
    link = db.get(UserPlaylistSong, (entry.id, song_id))
    if link is None:
        db.add(UserPlaylistSong(playlist_id=entry.id, song_id=song_id, position=position))
    elif position < link.position:
        link.position = position


def remove_missing(db: Session, user_id: int, kept_playlist_ids: set[str]) -> int:
    """Drop the user's playlists Spotify no longer lists (saved tracks stay); returns how many."""
    gone = (
        db.query(UserPlaylist)
        .filter(UserPlaylist.user_id == user_id, UserPlaylist.kind == PLAYLIST)
        .all()
    )
    removed = 0
    for entry in gone:
        if entry.spotify_playlist_id not in kept_playlist_ids:
            db.delete(entry)
            removed += 1
    return removed


@dataclass(frozen=True)
class PlaylistTrack:
    position: int
    title: str
    artists: tuple[str, ...]
    # The library song, None when the track is not in the library (yet).
    song_id: str | None


def playlist_tracks(db: Session, entry: UserPlaylist) -> list[PlaylistTrack]:
    """The playlist's tracks as last read from Spotify, matched with the library as it is now.

    Rows from before the track list was stored have only their linked songs.
    """
    if entry.tracks is not None:
        tracks = _as_tracks(entry.tracks)
        found = resolve_song_ids(db, tracks)
        return [
            PlaylistTrack(position=i, title=t.title, artists=t.artists, song_id=found.get(t.spotify_id))
            for i, t in enumerate(tracks)
        ]
    rows = (
        db.query(UserPlaylistSong.position, Song.title, Song.artist, Song.id)
        .join(Song, Song.id == UserPlaylistSong.song_id)
        .filter(UserPlaylistSong.playlist_id == entry.id)
        .order_by(UserPlaylistSong.position)
        .all()
    )
    return [PlaylistTrack(position=p, title=t or "", artists=(a,) if a else (), song_id=sid) for p, t, a, sid in rows]


def user_playlist(db: Session, user_id: int, playlist_id: int) -> UserPlaylist | None:
    entry = db.get(UserPlaylist, playlist_id)
    return entry if entry is not None and entry.user_id == user_id else None


def user_playlists(db: Session, user_id: int) -> list[tuple[UserPlaylist, list[str]]]:
    """The user's playlists (saved tracks first, then by name) with their song ids in playlist order."""
    entries = db.query(UserPlaylist).filter(UserPlaylist.user_id == user_id).all()
    entries.sort(key=lambda e: (e.kind != LIKED, e.name.lower()))
    songs: dict[int, list[str]] = {e.id: [] for e in entries}
    if entries:
        rows = (
            db.query(UserPlaylistSong.playlist_id, UserPlaylistSong.song_id)
            .filter(UserPlaylistSong.playlist_id.in_(songs))
            .order_by(UserPlaylistSong.playlist_id, UserPlaylistSong.position)
            .all()
        )
        for playlist_id, song_id in rows:
            songs[playlist_id].append(song_id)
    return [(e, songs[e.id]) for e in entries]
