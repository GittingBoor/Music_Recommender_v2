# Music Recommender v2 — CLAUDE.md

Musikinformatik-Projekt (Master). Nimmt Audiodateien (MP3, WAV, FLAC, OGG, AIFF, M4A) und extrahiert Audio-Eigenschaften via Essentia (DSP + ML) sowie Metadaten via Mutagen + Last.fm API, um Musik zu analysieren und zu empfehlen.

## Stack

- **Backend**: FastAPI · Python 3.10+ · `src/` layout
- **Frontend**: Vite · React · TypeScript · Tailwind
- **ML**: Essentia-TensorFlow (`.pb` Modelle, lokal gecacht)
- **DB**: PostgreSQL via SQLAlchemy + Alembic
- **Metadaten**: Mutagen (File-Tags) + Last.fm API (track.getInfo, artist.getInfo, track.getSimilar)

## Docker

```powershell
# Nach Code-Änderungen immer neu bauen:
docker-compose down
docker-compose up --build -d

# In den Container einloggen:
docker exec -it music_recommender_v2-backend-1 bash
```

Volumes: `test_audio/`, `test_output/`, `model_cache/` — alle gemountet und gitignored.
DNS im Backend-Container: 8.8.8.8 + 1.1.1.1 (nötig für Last.fm API-Zugriff aus Docker heraus).

## Pipeline-Übersicht

```
audio file → [Mutagen Tags] + [Last.fm API]
           → [DSP 44kHz]
           → [EffNet-Embedding 16kHz] → EffNet-Klassifikatoren
           → [MusiCNN-Embedding 16kHz] → DEAM (Arousal/Valence)
           → JSON: { metadata, dsp, ml }
```

## DSP-Features (`backend/src/analysis/dsp.py`, `essentia.standard`, 44.1 kHz)

| Key | Algorithmus |
|---|---|
| `bpm`, `beat_count`, `beat_confidence` | `es.RhythmExtractor2013()` |
| `danceability` (0–3) | `es.Danceability()` |
| `beat_loudness_mean` | `es.BeatsLoudness()` |
| `onset_rate` | `es.OnsetRate()` |
| `key`, `scale`, `key_strength` | `es.KeyExtractor()` |
| `tuning_frequency_hz`, `tuning_cents_deviation` | `es.TuningFrequency()` via SpectralPeaks per Frame |
| `integrated_lufs`, `loudness_range_lu` | `es.LoudnessEBUR128()` (Stereo-Input nötig) |
| `dynamic_complexity`, `loudness_db` | `es.DynamicComplexity()` |
| `spectral_centroid_mean`, `spectral_rolloff_mean`, `spectral_flux_mean` | `es.SpectralCentroid()` etc. |
| `mfcc_mean` (13 Koeffizienten) | `es.MFCC()` |
| `zero_crossing_rate` | `es.ZeroCrossingRate()` |
| `dissonance` | `es.Dissonance()` |
| `most_common_chord`, `chord_strength_mean`, `chord_change_rate` | `es.ChordsDetection()` |

## ML-Modelle (`backend/src/analysis/`, alle via `model_manager.get_path(key)`)

**Embeddings:**
| Key | Datei | Für |
|---|---|---|
| `effnet_embedding` | `discogs-effnet-bs64-1.pb` | Alle EffNet-Klassifikatoren |
| `musicnn_embedding` | `msd-musicnn-1.pb` | Nur DEAM (Arousal/Valence) |

**Klassifikatoren (alle auf EffNet-Embedding, außer `arousal_valence`):**
| Key | Ausgabe |
|---|---|
| `mood_happy` | P(happy) 0–1 |
| `mood_sad` | P(sad) 0–1 |
| `mood_aggressive` | P(aggressive) 0–1 |
| `mood_party` | P(party) 0–1 |
| `mood_relaxed` | P(relaxed) 0–1 |
| `mood_acoustic` | P(acoustic) 0–1 |
| `mood_electronic` | P(electronic) 0–1 |
| `arousal_valence` | [arousal, valence] je 1–9 · braucht MusiCNN |
| `genre_discogs400` | 400 Klassen, Multi-Label — TF2-Modell (`_LAYER_OVERRIDES`) |
| `approachability` | [niche, mainstream] 0–1 |
| `engagement` | [background, active] 0–1 |
| `instrument` | 40 Klassen (MTG Jamendo), Multi-Label |
| `voice_instrumental` | [instrumental, vocal] 0–1 |
| `gender` | [female, male] 0–1 |

TF1 vs TF2: `genre_discogs400` ist TF2 (`serving_default_model_Placeholder` / `PartitionedCall`), alle anderen TF1 (`model/Placeholder`). Gesteuert via `_LAYER_OVERRIDES` in `classifiers.py`.

## Metadaten (`backend/src/analysis/metadata.py`)

1. Mutagen liest File-Tags (title, artist, album, year, genre_tag, track_number, composer, comment, bitrate, sample_rate, channels, duration)
2. Fallback: Dateiname im Format `Artist - Title.mp3` → artist + title geparst
3. Last.fm: `track.getInfo` + `artist.getInfo` + `track.getSimilar` — befüllt alle null-Tags aus Schritt 1+2
4. Alles landet in `metadata.lastfm` als Sub-Objekt (playcount, listeners, tags, artist_bio, similar_artists, similar_tracks etc.)

## Wichtigste Datei: `backend/src/analysis/model_manager.py`

Lädt alle Essentia-ML-Modelle beim ersten Start von `https://essentia.upf.edu/models/` herunter und cached sie in `model_cache/` (gitignored).

```bash
python -m src.analysis.model_manager
```

16 Modelle (2 Embeddings + 14 Klassifikatoren), ~50–200 MB pro Datei. `get_manager().get_path("mood_happy")` → `Path` zur `.pb`-Datei.

## Ordnerstruktur

```
backend/src/
  main.py                  # FastAPI app (noch leer)
  analysis/
    model_manager.py       # Download + Cache aller .pb Modelle
    embeddings.py          # EffNet- und MusiCNN-Embedding-Extraktion
    classifiers.py         # 14 predict_* Funktionen + Label-Listen
    dsp.py                 # DSP-Feature-Extraktion (44.1 kHz)
    metadata.py            # Mutagen + Last.fm Metadaten
    pipeline.py            # Einstiegspunkt: run_full_pipeline(), CLI
  api/routes/              # HTTP-Routen (noch leer)
  core/config.py           # Settings (model_cache_dir, database_url, lastfm_api_key)
  db/models/               # SQLAlchemy ORM (noch leer)
  recommender/             # Empfehlungslogik (noch leer)
  schemas/                 # Pydantic API-Modelle (noch leer)

model_cache/               # gitignored — .pb Dateien landen hier
backend/test_audio/        # gitignored — Test-Audiodateien
backend/test_output/       # gitignored — JSON-Outputs der Pipeline
frontend/src/              # React + TypeScript
```

## Config (`.env` in `backend/`)

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql://user:password@db:5432/music_recommender` |
| `MODEL_CACHE_DIR` | `model_cache` |
| `DEBUG` | `false` |
| `LASTFM_API_KEY` | `` (leer → Last.fm wird übersprungen) |
