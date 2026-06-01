"""initial schema

Revision ID: 54e51b95250d
Revises:
Create Date: 2026-06-01 14:10:32.138122

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '54e51b95250d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'songs',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('artist', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'artists',
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('artist_playcount', sa.Integer(), nullable=True),
        sa.Column('artist_listeners', sa.Integer(), nullable=True),
        sa.Column('artist_bio', sa.Text(), nullable=True),
        sa.Column('similar_artists', postgresql.ARRAY(sa.String()), nullable=True),
        sa.PrimaryKeyConstraint('name'),
    )
    op.create_table(
        'file_metadata',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('file_format', sa.String(20), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('sample_rate_hz', sa.Integer(), nullable=True),
        sa.Column('bitrate_kbps', sa.Integer(), nullable=True),
        sa.Column('channels', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'track_metadata',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('release_date', sa.String(20), nullable=True),
        sa.Column('playcount', sa.Integer(), nullable=True),
        sa.Column('listeners', sa.Integer(), nullable=True),
        sa.Column('mbid', sa.String(100), nullable=True),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('album_mbid', sa.String(100), nullable=True),
        sa.Column('mb_genres', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('featured_artists', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('similar_tracks', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'dsp_features',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('beat_count', sa.Integer(), nullable=True),
        sa.Column('beat_confidence', sa.Float(), nullable=True),
        sa.Column('danceability', sa.Float(), nullable=True),
        sa.Column('beat_loudness_mean', sa.Float(), nullable=True),
        sa.Column('onset_rate', sa.Float(), nullable=True),
        sa.Column('key', sa.String(10), nullable=True),
        sa.Column('scale', sa.String(10), nullable=True),
        sa.Column('key_strength', sa.Float(), nullable=True),
        sa.Column('tuning_frequency_hz', sa.Float(), nullable=True),
        sa.Column('tuning_cents_deviation', sa.Float(), nullable=True),
        sa.Column('most_common_chord', sa.String(20), nullable=True),
        sa.Column('chord_strength_mean', sa.Float(), nullable=True),
        sa.Column('chord_change_rate', sa.Float(), nullable=True),
        sa.Column('integrated_lufs', sa.Float(), nullable=True),
        sa.Column('loudness_range_lu', sa.Float(), nullable=True),
        sa.Column('dynamic_complexity', sa.Float(), nullable=True),
        sa.Column('loudness_db', sa.Float(), nullable=True),
        sa.Column('spectral_centroid_mean', sa.Float(), nullable=True),
        sa.Column('spectral_rolloff_mean', sa.Float(), nullable=True),
        sa.Column('spectral_flux_mean', sa.Float(), nullable=True),
        sa.Column('mfcc_mean', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('zero_crossing_rate', sa.Float(), nullable=True),
        sa.Column('dissonance', sa.Float(), nullable=True),
        sa.Column('loudness_short_term_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('spectral_centroid_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('spectral_rolloff_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('spectral_flux_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('zero_crossing_rate_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('dissonance_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'ml_profile_features',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('approachability_label', sa.String(20), nullable=True),
        sa.Column('approachability_score', sa.Float(), nullable=True),
        sa.Column('approachability_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('engagement_label', sa.String(20), nullable=True),
        sa.Column('engagement_score', sa.Float(), nullable=True),
        sa.Column('engagement_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('voice_label', sa.String(20), nullable=True),
        sa.Column('voice_score', sa.Float(), nullable=True),
        sa.Column('voice_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('gender_label', sa.String(10), nullable=True),
        sa.Column('gender_score', sa.Float(), nullable=True),
        sa.Column('gender_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('arousal', sa.Float(), nullable=True),
        sa.Column('arousal_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('valence', sa.Float(), nullable=True),
        sa.Column('valence_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'ml_mood_features',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('happy', sa.Float(), nullable=True),
        sa.Column('happy_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('sad', sa.Float(), nullable=True),
        sa.Column('sad_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('aggressive', sa.Float(), nullable=True),
        sa.Column('aggressive_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('party', sa.Float(), nullable=True),
        sa.Column('party_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('relaxed', sa.Float(), nullable=True),
        sa.Column('relaxed_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('acoustic', sa.Float(), nullable=True),
        sa.Column('acoustic_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('electronic', sa.Float(), nullable=True),
        sa.Column('electronic_timeseries', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'ml_gmbi_features',
        sa.Column('id', sa.String(22), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'parent_genres',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('genre', sa.String(200), nullable=False),
        sa.Column('percentage', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id', 'genre'),
    )
    op.create_table(
        'detailed_genres',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('genre', sa.String(200), nullable=False),
        sa.Column('probability', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id', 'genre'),
    )
    op.create_table(
        'instruments',
        sa.Column('id', sa.String(22), nullable=False),
        sa.Column('instrument', sa.String(100), nullable=False),
        sa.Column('probability', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['songs.id']),
        sa.PrimaryKeyConstraint('id', 'instrument'),
    )


def downgrade() -> None:
    op.drop_table('instruments')
    op.drop_table('detailed_genres')
    op.drop_table('parent_genres')
    op.drop_table('ml_gmbi_features')
    op.drop_table('ml_mood_features')
    op.drop_table('ml_profile_features')
    op.drop_table('dsp_features')
    op.drop_table('track_metadata')
    op.drop_table('file_metadata')
    op.drop_table('songs')
    op.drop_table('artists')
