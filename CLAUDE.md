# Music Recommender v2 — CLAUDE.md

Musikinformatik-Projekt (Master). Nimmt `.wav`-Dateien und extrahiert Audio-Eigenschaften via Essentia (DSP + ML), um Musik zu analysieren und zu empfehlen.

## Stack

- **Backend**: FastAPI · Python 3.10+ · `src/` layout
- **Frontend**: Vite · React · TypeScript · Tailwind
- **ML**: Essentia-TensorFlow (`.pb` Modelle, lokal gecacht)
- **DB**: PostgreSQL via SQLAlchemy + Alembic

## Wichtigste Datei: `backend/src/analysis/model_manager.py`

Lädt alle Essentia-ML-Modelle beim ersten Start von `https://essentia.upf.edu/models/` herunter und cached sie in `model_cache/` (gitignored). Standalone ausführen:

```bash
# aus backend/
python -m src.analysis.model_manager
```

16 Modelle, ~50–200 MB pro Datei. `get_manager().get_path("mood_happy")` → `Path` zur `.pb`-Datei.

## Pipeline-Übersicht

```
track.wav → [DSP 44kHz] + [EffNet-Embedding 16kHz] + [MusiCNN-Embedding 16kHz]
                                    ↓                           ↓
                          EffNet-Klassifikatoren          DEAM (Arousal/Valence)
                                    ↓
                          JSON mit allen Features
```

## DSP-Features (kein Modell, `essentia.standard`)

| Key | Algorithmus |
|---|---|
| Danceability (0–3) | `es.Danceability()` |
| BPM + Beat Positions | `es.RhythmExtractor2013()` |
| Beat Loudness | `es.BeatsLoudness()` |
| Onset Rate | `es.OnsetRate()` |
| Key + Major/Minor | `es.KeyExtractor()` |
| Tuning (Cent-Abweichung) | `es.TuningFrequency()` |
| Loudness (LUFS) | `es.LoudnessEBUR128()` |
| Dynamic Complexity | `es.DynamicComplexity()` |
| Spectral Centroid/Rolloff/Flux | `es.SpectralCentroid()` etc. |
| MFCC (13 Koeffizienten) | `es.MFCC()` |
| Zero Crossing Rate | `es.ZeroCrossingRate()` |
| Dissonance | `es.Dissonance()` |
| Chords + Tonal Complexity | `es.ChordsDetection()` |

## ML-Modelle (alle via `model_manager.get_path(key)`)

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
| `genre_discogs400` | 400 Klassen, Multi-Label |
| `approachability` | [niche, mainstream] 0–1 |
| `engagement` | [background, active] 0–1 |
| `instrument` | 40 Klassen, Multi-Label |
| `voice_instrumental` | [instrumental, vocal] 0–1 |
| `gender` | [female, male] 0–1 |

## Ordnerstruktur

```
backend/src/
  main.py               # FastAPI app
  analysis/
    model_manager.py    # Download + Cache aller .pb Modelle
  api/routes/           # HTTP-Routen
  core/config.py        # Settings (model_cache_dir, database_url)
  db/models/            # SQLAlchemy ORM
  recommender/          # Empfehlungslogik
  schemas/              # Pydantic API-Modelle

model_cache/            # gitignored — .pb Dateien landen hier
frontend/src/           # React + TypeScript
```

## Config (`.env` oder Env-Variablen)

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql://user:password@localhost:5432/music_recommender` |
| `MODEL_CACHE_DIR` | `model_cache` |
| `DEBUG` | `false` |
