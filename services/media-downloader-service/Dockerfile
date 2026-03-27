# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY media-downloader-service/requirements.txt .
RUN pip install --no-cache-dir --prefix=/app/deps -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/deps /app/deps
ENV PATH=/app/deps/bin:$PATH
ENV PYTHONPATH=/app/src:/app/deps/lib/python3.13/site-packages

COPY media-downloader-service/src/ ./src/

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8007/health || exit 1

RUN useradd -m -u 1000 minabox \
    && mkdir -p /mnt/audio/tracks/downloads \
    && chown -R minabox:minabox /app /mnt/audio

USER minabox

CMD ["python", "-m", "uvicorn", "media_downloader_service.main:app", "--host", "0.0.0.0", "--port", "8007"]
