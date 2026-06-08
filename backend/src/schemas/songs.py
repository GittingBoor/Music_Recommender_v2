from __future__ import annotations
from pydantic import BaseModel


class FileMetadataSchema(BaseModel):
    filename: str | None = None
    file_format: str | None = None
    duration_seconds: float | None = None
    sample_rate_hz: int | None = None
    bitrate_kbps: int | None = None
    channels: int | None = None

    model_config = {"from_attributes": True}


class TrackMetadataSchema(BaseModel):
    release_date: str | None = None
    playcount: int | None = None
    listeners: int | None = None
    mbid: str | None = None
    url: str | None = None
    album_mbid: str | None = None
    mb_genres: list[str] | None = None
    featured_artists: list[str] | None = None
    similar_tracks: list | None = None

    model_config = {"from_attributes": True}


class DSPFeaturesSchema(BaseModel):
    bpm: float | None = None
    beat_count: int | None = None
    beat_confidence: float | None = None
    danceability: float | None = None
    beat_loudness_mean: float | None = None
    onset_rate: float | None = None
    key: str | None = None
    scale: str | None = None
    key_strength: float | None = None
    tuning_frequency_hz: float | None = None
    tuning_cents_deviation: float | None = None
    most_common_chord: str | None = None
    chord_strength_mean: float | None = None
    chord_change_rate: float | None = None
    integrated_lufs: float | None = None
    loudness_range_lu: float | None = None
    dynamic_complexity: float | None = None
    loudness_db: float | None = None
    spectral_centroid_mean: float | None = None
    spectral_rolloff_mean: float | None = None
    spectral_flux_mean: float | None = None
    mfcc_mean: list[float] | None = None
    zero_crossing_rate: float | None = None
    dissonance: float | None = None

    model_config = {"from_attributes": True}


class MLProfileSchema(BaseModel):
    niche_score: float | None = None
    mainstream_score: float | None = None
    background_score: float | None = None
    active_score: float | None = None
    instrumental_score: float | None = None
    vocal_score: float | None = None
    female_score: float | None = None
    male_score: float | None = None
    arousal: float | None = None
    valence: float | None = None

    model_config = {"from_attributes": True}


class MLMoodsSchema(BaseModel):
    happy: float | None = None
    sad: float | None = None
    aggressive: float | None = None
    party: float | None = None
    relaxed: float | None = None
    acoustic: float | None = None
    electronic: float | None = None

    model_config = {"from_attributes": True}


class ParentGenreSchema(BaseModel):
    genre: str
    percentage: float

    model_config = {"from_attributes": True}


class DetailedGenreSchema(BaseModel):
    genre: str
    probability: float

    model_config = {"from_attributes": True}


class InstrumentSchema(BaseModel):
    instrument: str
    probability: float

    model_config = {"from_attributes": True}


class SongResponse(BaseModel):
    id: str
    title: str | None = None
    artist: str | None = None
    file_metadata: FileMetadataSchema | None = None
    track_metadata: TrackMetadataSchema | None = None
    dsp_features: DSPFeaturesSchema | None = None
    ml_profile: MLProfileSchema | None = None
    ml_moods: MLMoodsSchema | None = None
    parent_genres: list[ParentGenreSchema] = []
    detailed_genres: list[DetailedGenreSchema] = []
    instruments: list[InstrumentSchema] = []
    has_preview: bool = False

    model_config = {"from_attributes": True}
