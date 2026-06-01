#!/bin/bash
set -e

AUDIO_DIR="/app/test_audio"
EXTENSIONS="wav mp3 flac ogg aiff m4a"

if [ "$ANALYZE" = "1" ]; then
    if [ -d "$AUDIO_DIR" ]; then
        for ext in $EXTENSIONS; do
            for file in "$AUDIO_DIR"/*.$ext "$AUDIO_DIR"/*.${ext^^}; do
                [ -f "$file" ] || continue
                echo "[Entrypoint] Running pipeline on: $file"
                python -m src.analysis.pipeline "$file" --save || echo "[Entrypoint] FAILED: $file"
            done
        done
    else
        echo "[Entrypoint] test_audio/ not found — skipping pipeline run"
    fi
fi

exec uvicorn src.main:app --host 0.0.0.0 --port 8000
