FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libchromaprint-tools \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY entrypoint.sh ./entrypoint.sh
RUN sed -i 's/\r//' entrypoint.sh && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
