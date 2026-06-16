from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from src.db.models import Song
from src.db.session import get_session

router = APIRouter()

TIMESERIES_FEATURES: dict[str, tuple[str, str]] = {
    "loudness":            ("dsp_features",  "loudness_short_term_timeseries"),
    "spectral_centroid":   ("dsp_features",  "spectral_centroid_timeseries"),
    "spectral_rolloff":    ("dsp_features",  "spectral_rolloff_timeseries"),
    "spectral_flux":       ("dsp_features",  "spectral_flux_timeseries"),
    "zero_crossing_rate":  ("dsp_features",  "zero_crossing_rate_timeseries"),
    "dissonance":          ("dsp_features",  "dissonance_timeseries"),
    "arousal":             ("ml_profile",    "arousal_timeseries"),
    "valence":             ("ml_profile",    "valence_timeseries"),
    "approachability":     ("ml_profile",    "approachability_timeseries"),
    "engagement":          ("ml_profile",    "engagement_timeseries"),
    "voice":               ("ml_profile",    "voice_timeseries"),
    "gender":              ("ml_profile",    "gender_timeseries"),
    "happy":               ("ml_moods",      "happy_timeseries"),
    "sad":                 ("ml_moods",      "sad_timeseries"),
    "aggressive":          ("ml_moods",      "aggressive_timeseries"),
    "party":               ("ml_moods",      "party_timeseries"),
    "relaxed":             ("ml_moods",      "relaxed_timeseries"),
    "acoustic":            ("ml_moods",      "acoustic_timeseries"),
    "electronic":          ("ml_moods",      "electronic_timeseries"),
}

MOOD_FIELDS = ["happy", "sad", "aggressive", "party", "relaxed", "acoustic", "electronic"]


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _normalize_array(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=float)
    mn, mx = float(arr.min()), float(arr.max())
    if mx == mn:
        return [0.5] * len(values)
    return ((arr - mn) / (mx - mn)).tolist()


@router.get("/analysis/correlations")
def get_correlations(db: Session = Depends(get_db)) -> dict[str, Any]:
    songs = (
        db.query(Song)
        .options(
            selectinload(Song.dsp_features),
            selectinload(Song.ml_profile),
            selectinload(Song.ml_moods),
            selectinload(Song.track_metadata),
        )
        .all()
    )

    rows: list[dict[str, float | None]] = []
    for s in songs:
        row: dict[str, float | None] = {}
        if s.dsp_features:
            d = s.dsp_features
            row.update({
                "bpm":                d.bpm,
                "beat_confidence":    d.beat_confidence,
                "danceability":       d.danceability,
                "onset_rate":         d.onset_rate,
                "key_strength":       d.key_strength,
                "chord_strength":     d.chord_strength_mean,
                "chord_change_rate":  d.chord_change_rate,
                "lufs":               d.integrated_lufs,
                "loudness_range":     d.loudness_range_lu,
                "dynamic_complexity": d.dynamic_complexity,
                "loudness_db":        d.loudness_db,
                "spectral_centroid":  d.spectral_centroid_mean,
                "spectral_rolloff":   d.spectral_rolloff_mean,
                "spectral_flux":      d.spectral_flux_mean,
                "zero_crossing_rate": d.zero_crossing_rate,
                "dissonance":         d.dissonance,
            })
        if s.ml_profile:
            p = s.ml_profile
            row.update({
                "niche_score":    p.niche_score,
                "mainstream":     p.mainstream_score,
                "background":     p.background_score,
                "active":         p.active_score,
                "instrumental":   p.instrumental_score,
                "vocal":          p.vocal_score,
                "female":         p.female_score,
                "male":           p.male_score,
                "arousal":        p.arousal,
                "valence":        p.valence,
            })
        if s.ml_moods:
            m = s.ml_moods
            row.update({
                "happy":          m.happy,
                "sad":            m.sad,
                "aggressive":     m.aggressive,
                "party":          m.party,
                "relaxed":        m.relaxed,
                "acoustic":       m.acoustic,
                "electronic":     m.electronic,
            })
        if s.track_metadata:
            t = s.track_metadata
            row["playcount"] = float(t.playcount) if t.playcount else None
            row["listeners"] = float(t.listeners) if t.listeners else None
        rows.append(row)

    if not rows:
        return {"features": [], "matrix": []}

    df = pd.DataFrame(rows)
    min_valid = max(2, len(df) // 3)
    df = df.dropna(axis=1, thresh=min_valid)
    corr = df.corr(method="pearson")
    features = list(corr.columns)
    matrix = [
        [None if pd.isna(v) else round(float(v), 3) for v in row]
        for row in corr.values
    ]
    return {"features": features, "matrix": matrix}


@router.get("/analysis/timeseries")
def get_timeseries(
    feature: str = Query(default="loudness"),
    mood: str | None = Query(default=None),
    threshold: float = Query(default=0.7, ge=0.0, le=1.0),
    song_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if feature not in TIMESERIES_FEATURES:
        return {"feature": feature, "song_count": 0, "selected_song": None, "avg_timeseries": []}

    if mood and mood not in MOOD_FIELDS:
        return {"feature": feature, "song_count": 0, "selected_song": None, "avg_timeseries": []}

    songs = (
        db.query(Song)
        .options(
            selectinload(Song.dsp_features),
            selectinload(Song.ml_profile),
            selectinload(Song.ml_moods),
        )
        .all()
    )

    table_attr, col = TIMESERIES_FEATURES[feature]

    def get_ts(song: Song) -> list[float] | None:
        obj = getattr(song, table_attr, None)
        return None if obj is None else getattr(obj, col, None)

    def get_mood_val(song: Song, mood_name: str) -> float | None:
        return None if song.ml_moods is None else getattr(song.ml_moods, mood_name, None)

    selected_song_data: dict[str, Any] | None = None
    filtered: list[list[float]] = []

    for s in songs:
        ts = get_ts(s)
        if not ts:
            continue

        # Always capture selected song regardless of mood filter
        if s.id == song_id and selected_song_data is None:
            selected_song_data = {
                "song_id": s.id,
                "title":   s.title,
                "artist":  s.artist,
                "values":  _normalize_array(ts),
            }

        if mood:
            score = get_mood_val(s, mood)
            if score is None or score < threshold:
                continue

        filtered.append(ts)

    if not filtered:
        avg: list[float] = []
        counts_at_time: list[int] = []
    else:
        max_len = max(len(t) for t in filtered)
        counts_at_time = [
            sum(1 for t in filtered if sec < len(t))
            for sec in range(max_len)
        ]
        padded = np.array(
            [t + [t[-1]] * (max_len - len(t)) for t in filtered],
            dtype=float,
        )
        mean_ts = padded.mean(axis=0)
        avg = _normalize_array(mean_ts.tolist())

    return {
        "feature":        feature,
        "song_count":     len(filtered),
        "selected_song":  selected_song_data,
        "avg_timeseries": avg,
        "counts_at_time": counts_at_time,
    }


@router.get("/analysis/song/{song_id}")
def get_song_detail(song_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    song = (
        db.query(Song)
        .options(
            selectinload(Song.file_metadata),
            selectinload(Song.track_metadata),
            selectinload(Song.parent_genres),
            selectinload(Song.detailed_genres),
            selectinload(Song.instruments),
            selectinload(Song.ml_profile),
            selectinload(Song.ml_moods),
            selectinload(Song.dsp_features),
        )
        .filter(Song.id == song_id)
        .first()
    )

    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")

    ts: dict[str, list[float] | None] = {}
    if song.dsp_features:
        d = song.dsp_features
        ts["loudness"]           = d.loudness_short_term_timeseries
        ts["spectral_centroid"]  = d.spectral_centroid_timeseries
        ts["spectral_rolloff"]   = d.spectral_rolloff_timeseries
        ts["spectral_flux"]      = d.spectral_flux_timeseries
        ts["zero_crossing_rate"] = d.zero_crossing_rate_timeseries
        ts["dissonance"]         = d.dissonance_timeseries
    if song.ml_profile:
        p = song.ml_profile
        ts["arousal"]        = p.arousal_timeseries
        ts["valence"]        = p.valence_timeseries
        ts["approachability"] = p.approachability_timeseries
        ts["engagement"]     = p.engagement_timeseries
        ts["voice"]          = p.voice_timeseries
        ts["gender"]         = p.gender_timeseries
    if song.ml_moods:
        m = song.ml_moods
        ts["happy"]      = m.happy_timeseries
        ts["sad"]        = m.sad_timeseries
        ts["aggressive"] = m.aggressive_timeseries
        ts["party"]      = m.party_timeseries
        ts["relaxed"]    = m.relaxed_timeseries
        ts["acoustic"]   = m.acoustic_timeseries
        ts["electronic"] = m.electronic_timeseries

    result: dict[str, Any] = {
        "id":         song.id,
        "title":      song.title,
        "artist":     song.artist,
        "timeseries": ts,
    }

    if song.dsp_features:
        d = song.dsp_features
        result["dsp"] = {
            "bpm":                   d.bpm,
            "beat_count":            d.beat_count,
            "beat_confidence":       d.beat_confidence,
            "danceability":          d.danceability,
            "key":                   d.key,
            "scale":                 d.scale,
            "key_strength":          d.key_strength,
            "integrated_lufs":       d.integrated_lufs,
            "loudness_range_lu":     d.loudness_range_lu,
            "dynamic_complexity":    d.dynamic_complexity,
            "loudness_db":           d.loudness_db,
            "spectral_centroid_mean": d.spectral_centroid_mean,
            "spectral_flux_mean":    d.spectral_flux_mean,
            "dissonance":            d.dissonance,
            "chord_change_rate":     d.chord_change_rate,
            "most_common_chord":     d.most_common_chord,
            "tuning_frequency_hz":   d.tuning_frequency_hz,
        }

    if song.ml_profile:
        p = song.ml_profile
        result["ml_profile"] = {
            "niche_score":      p.niche_score,
            "mainstream_score": p.mainstream_score,
            "background_score": p.background_score,
            "active_score":     p.active_score,
            "instrumental_score": p.instrumental_score,
            "vocal_score":      p.vocal_score,
            "female_score":     p.female_score,
            "male_score":       p.male_score,
            "arousal":          p.arousal,
            "valence":          p.valence,
        }

    if song.ml_moods:
        m = song.ml_moods
        result["ml_moods"] = {
            "happy":      m.happy,
            "sad":        m.sad,
            "aggressive": m.aggressive,
            "party":      m.party,
            "relaxed":    m.relaxed,
            "acoustic":   m.acoustic,
            "electronic": m.electronic,
        }

    if song.file_metadata:
        fm = song.file_metadata
        result["file_metadata"] = {
            "duration_seconds": fm.duration_seconds,
            "file_format":      fm.file_format,
            "bitrate_kbps":     fm.bitrate_kbps,
            "sample_rate_hz":   fm.sample_rate_hz,
        }

    if song.track_metadata:
        tm = song.track_metadata
        result["track_metadata"] = {
            "release_date": tm.release_date,
            "playcount":    tm.playcount,
            "listeners":    tm.listeners,
        }

    result["parent_genres"]   = [{"genre": g.genre, "percentage": g.percentage} for g in song.parent_genres]
    result["detailed_genres"] = [{"genre": g.genre, "probability": g.probability} for g in song.detailed_genres]
    result["instruments"]     = [{"instrument": i.instrument, "probability": i.probability} for i in song.instruments]

    return result
