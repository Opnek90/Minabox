# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

# ffmpeg is required by yt-dlp for audio extraction & thumbnail embedding
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY media-downloader-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.13-slim

WORKDIR /app

# ffmpeg needed at runtime for yt-dlp post-processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY media-downloader-service/src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

RUN useradd -m -u 1000 minabox \
    && mkdir -p /mnt/audio/tracks/downloads \
    && chown -R minabox:minabox /app /mnt/audio

USER minabox

CMD ["python", "-m", "uvicorn", "media_downloader_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
