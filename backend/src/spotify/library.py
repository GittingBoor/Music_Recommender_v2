"""Which library songs are in a user's Spotify playlists (user_playlists / user_playlist_songs).

Songs belong to everyone; a playlist is one user's view on them. A Spotify
track is found in the library in two ways: a playlist import that already
ended in a song (any user's — the song is shared), or the exact song id its
title and one of its artists give.
"""
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.db.models import PlaylistImportTrack, Song, UserPlaylist, UserPlaylistSong, generate_song_id
from src.db.models.user_playlist import LIKED, LIKED_ID, PLAYLIST
from src.metadata.cleaning import plain_quotes, strip_version_markers
from src.spotify.matching import SpotifyTrack

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


def store_liked(db: Session, user_id: int, tracks: list[SpotifyTrack]) -> UserPlaylist:
    return store_playlist(db, user_id, LIKED_ID, LIKED_NAME, None, tracks, kind=LIKED)


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
