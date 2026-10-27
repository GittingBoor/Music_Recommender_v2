"""add user_playlists and user_playlist_songs

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-27

Backfilled from the playlist imports so far: the latest import of each
(user, playlist) becomes a user playlist, its tracks are linked to the songs
they ended in. Duplicates were stored without a song id until now; they get
the song their title and artists name exactly (written to the import track as
well). Library songs that never went through an import are linked by the
first sync (POST /api/spotify/library/sync), which needs the Spotify API.
"""
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _candidates(title: str, artists_json: str) -> list[str]:
    # The importer's own matching, so backfilled links agree with new ones.
    from src.spotify.library import candidate_song_ids
    from src.spotify.matching import SpotifyTrack

    artists = tuple(json.loads(artists_json))
    track = SpotifyTrack(spotify_id="", title=title, artists=artists, duration_ms=None, isrc=None)
    return candidate_song_ids(track.plain_title, artists)


def _backfill() -> None:
    conn = op.get_bind()
    song_ids = {sid for (sid,) in conn.execute(sa.text("SELECT id FROM songs"))}

    # Duplicates without a song id: the song their title and artists name.
    for row_id, title, artists in conn.execute(sa.text(
        "SELECT id, title, artists FROM playlist_import_tracks WHERE status = 'duplicate' AND song_id IS NULL"
    )).all():
        song_id = next((sid for sid in _candidates(title, artists) if sid in song_ids), None)
        if song_id:
            conn.execute(sa.text("UPDATE playlist_import_tracks SET song_id = :s WHERE id = :i"),
                         {"s": song_id, "i": row_id})

    # A Spotify track that ended in a song in any import is that song everywhere.
    by_track = {
        track: sid for track, sid in conn.execute(sa.text(
            "SELECT spotify_track_id, song_id FROM playlist_import_tracks WHERE song_id IS NOT NULL ORDER BY id"
        )).all()
        if sid in song_ids
    }

    latest = conn.execute(sa.text("""
        SELECT DISTINCT ON (user_id, spotify_playlist_id) id, user_id, spotify_playlist_id, name, created_at
        FROM playlist_imports ORDER BY user_id, spotify_playlist_id, id DESC
    """)).all()
    for import_id, user_id, playlist_id, name, created_at in latest:
        tracks = conn.execute(sa.text(
            "SELECT position, spotify_track_id FROM playlist_import_tracks WHERE import_id = :i ORDER BY position"
        ), {"i": import_id}).all()
        new_id = conn.execute(sa.text("""
            INSERT INTO user_playlists (user_id, spotify_playlist_id, kind, name, image, track_count, synced_at)
            VALUES (:u, :p, 'playlist', :n, NULL, :c, :t) RETURNING id
        """), {
            "u": user_id, "p": playlist_id, "n": name, "c": len({t for _, t in tracks}),
            "t": created_at or datetime.now(timezone.utc),
        }).scalar_one()
        positions: dict[str, int] = {}
        for position, track in tracks:
            sid = by_track.get(track)
            if sid and sid not in positions:
                positions[sid] = position
        if positions:
            conn.execute(
                sa.text("INSERT INTO user_playlist_songs (playlist_id, song_id, position) VALUES (:p, :s, :n)"),
                [{"p": new_id, "s": s, "n": n} for s, n in positions.items()],
            )


def upgrade() -> None:
    op.create_table(
        "user_playlists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spotify_playlist_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("image", sa.String(1024), nullable=True),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "spotify_playlist_id", name="uq_user_playlists_user_playlist"),
    )
    op.create_index("ix_user_playlists_user_id", "user_playlists", ["user_id"])
    op.create_table(
        "user_playlist_songs",
        sa.Column("playlist_id", sa.Integer(), sa.ForeignKey("user_playlists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("song_id", sa.String(22), sa.ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_user_playlist_songs_song_id", "user_playlist_songs", ["song_id"])
    _backfill()


def downgrade() -> None:
    op.drop_index("ix_user_playlist_songs_song_id", table_name="user_playlist_songs")
    op.drop_table("user_playlist_songs")
    op.drop_index("ix_user_playlists_user_id", table_name="user_playlists")
    op.drop_table("user_playlists")
