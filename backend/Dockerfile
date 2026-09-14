# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "120";\n' > /etc/apt/apt.conf.d/80-retries \
    && printf 'Types: deb\nURIs: http://ftp.de.debian.org/debian\nSuites: bookworm bookworm-updates\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n' > /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libchromaprint-tools \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock is the pinned pip-freeze snapshot; requirements.txt is
# the human-edited manifest (see the lock file header for how to regenerate).
#
# --no-deps is deliberate: the lock is a complete freeze, so every transitive
# dependency is already pinned below. Resolving deps again would drag in the
# GPU builds that inaSpeechSegmenter asks for by name (tensorflow instead of
# tensorflow-cpu, onnxruntime-gpu) plus ~2.9 GB of CUDA libraries that never
# run on this CPU-only image.
#
# The cache mount keeps pip's wheel cache between builds, so a rebuild after a
# dependency change re-downloads only what actually changed.
COPY requirements.lock .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps -r requirements.lock

COPY src/ ./src/
COPY entrypoint.sh ./entrypoint.sh
RUN sed -i 's/\r//' entrypoint.sh && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
