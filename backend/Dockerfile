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
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY src/ ./src/
COPY entrypoint.sh ./entrypoint.sh
RUN sed -i 's/\r//' entrypoint.sh && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
