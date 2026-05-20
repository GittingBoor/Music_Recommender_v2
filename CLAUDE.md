# Music Recommender v2 — CLAUDE.md

Master's project (Musikinformatik). Takes audio files (MP3, WAV, FLAC, OGG, AIFF, M4A), extracts audio features via Essentia (DSP + ML) and metadata via Mutagen + Last.fm API, to analyze music and power a recommendation engine.

## Stack

- **Backend**: FastAPI · Python 3.10+ · `src/` layout
- **Frontend**: Vite · React · TypeScript · Tailwind
- **ML**: Essentia-TensorFlow (`.pb` models, cached locally)
- **DB**: PostgreSQL via SQLAlchemy + Alembic
- **Metadata**: Mutagen (file tags) + Last.fm API (track.getInfo, artist.getInfo, track.getSimilar)

## Docker

```powershell
# After any code change, always rebuild:
docker-compose down
docker-compose up --build -d

# Enter the container:
docker exec -it music_recommender_v2-backend-1 bash
```

Volumes: `test_audio/`, `test_output/`, `model_cache/` — all mounted and gitignored.
DNS in backend container: 8.8.8.8 + 1.1.1.1 (required for Last.fm API access from inside Docker).

## Pipeline Overview

```
audio file → [Mutagen tags] + [Last.fm API]
           → [DSP 44kHz]
           → [EffNet embedding 16kHz] → EffNet classifiers
           → [MusiCNN embedding 16kHz] → DEAM (Arousal/Valence)
           → JSON: { metadata, dsp, ml }
```

## DSP Features (`backend/src/analysis/dsp.py`, `essentia.standard`, 44.1 kHz)

| Key | Algorithm |
|---|---|
| `bpm`, `beat_count`, `beat_confidence` | `es.RhythmExtractor2013()` |
| `danceability` (0–3) | `es.Danceability()` |
| `beat_loudness_mean` | `es.BeatsLoudness()` |
| `onset_rate` | `es.OnsetRate()` |
| `key`, `scale`, `key_strength` | `es.KeyExtractor()` |
| `tuning_frequency_hz`, `tuning_cents_deviation` | `es.TuningFrequency()` via SpectralPeaks per frame |
| `integrated_lufs`, `loudness_range_lu` | `es.LoudnessEBUR128()` (stereo input required) |
| `dynamic_complexity`, `loudness_db` | `es.DynamicComplexity()` |
| `spectral_centroid_mean`, `spectral_rolloff_mean`, `spectral_flux_mean` | `es.SpectralCentroid()` etc. |
| `mfcc_mean` (13 coefficients) | `es.MFCC()` |
| `zero_crossing_rate` | `es.ZeroCrossingRate()` |
| `dissonance` | `es.Dissonance()` |
| `most_common_chord`, `chord_strength_mean`, `chord_change_rate` | `es.ChordsDetection()` |

## ML Models (`backend/src/analysis/`, all via `model_manager.get_path(key)`)

**Embeddings:**
| Key | File | Used for |
|---|---|---|
| `effnet_embedding` | `discogs-effnet-bs64-1.pb` | All EffNet classifiers |
| `musicnn_embedding` | `msd-musicnn-1.pb` | DEAM (Arousal/Valence) only |

**Classifiers (all on EffNet embedding, except `arousal_valence`):**
| Key | Output |
|---|---|
| `mood_happy` | P(happy) 0–1 |
| `mood_sad` | P(sad) 0–1 |
| `mood_aggressive` | P(aggressive) 0–1 |
| `mood_party` | P(party) 0–1 |
| `mood_relaxed` | P(relaxed) 0–1 |
| `mood_acoustic` | P(acoustic) 0–1 |
| `mood_electronic` | P(electronic) 0–1 |
| `arousal_valence` | [arousal, valence] each 1–9 · requires MusiCNN |
| `genre_discogs400` | 400 classes, multi-label — TF2 model (`_LAYER_OVERRIDES`) |
| `approachability` | [niche, mainstream] 0–1 |
| `engagement` | [background, active] 0–1 |
| `instrument` | 40 classes (MTG Jamendo), multi-label |
| `voice_instrumental` | [instrumental, vocal] 0–1 |
| `gender` | [female, male] 0–1 |

TF1 vs TF2: `genre_discogs400` is TF2 (`serving_default_model_Placeholder` / `PartitionedCall`), all others are TF1 (`model/Placeholder`). Controlled via `_LAYER_OVERRIDES` in `classifiers.py`.

## Metadata (`backend/src/analysis/metadata.py`)

1. Mutagen reads file tags (title, artist, album, year, genre_tag, track_number, composer, comment, bitrate, sample_rate, channels, duration)
2. Fallback: filename in `Artist - Title.mp3` format → artist + title parsed automatically
3. Last.fm: `track.getInfo` + `artist.getInfo` + `track.getSimilar` — fills any null tags from steps 1+2
4. Everything stored under `metadata.lastfm` sub-object (playcount, listeners, tags, artist_bio, similar_artists, similar_tracks, etc.)

## Key File: `backend/src/analysis/model_manager.py`

Downloads all Essentia ML models from `https://essentia.upf.edu/models/` on first run and caches them in `model_cache/` (gitignored).

```bash
python -m src.analysis.model_manager
```

16 models (2 embeddings + 14 classifiers), ~50–200 MB each. `get_manager().get_path("mood_happy")` → `Path` to the `.pb` file.

## Directory Structure

```
backend/src/
  main.py                  # FastAPI app (mostly empty)
  analysis/
    model_manager.py       # Download + cache all .pb models
    embeddings.py          # EffNet and MusiCNN embedding extraction
    classifiers.py         # 14 predict_* functions + label lists
    dsp.py                 # DSP feature extraction (44.1 kHz)
    metadata.py            # Mutagen + Last.fm metadata
    pipeline.py            # Entry point: run_full_pipeline(), CLI
  api/routes/              # HTTP routes (empty)
  core/config.py           # Settings (model_cache_dir, database_url, lastfm_api_key)
  db/models/               # SQLAlchemy ORM (empty)
  recommender/             # Recommendation logic (empty)
  schemas/                 # Pydantic API models (empty)

model_cache/               # gitignored — .pb files go here
backend/test_audio/        # gitignored — test audio files
backend/test_output/       # gitignored — JSON pipeline outputs
frontend/src/              # React + TypeScript
```

## Config (`.env` in `backend/`)

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql://user:password@db:5432/music_recommender` |
| `MODEL_CACHE_DIR` | `model_cache` |
| `DEBUG` | `false` |
| `LASTFM_API_KEY` | `` (empty → Last.fm is skipped entirely) |
