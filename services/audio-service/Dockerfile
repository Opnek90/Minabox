# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY audio-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Install VLC, ALSA and Pulse/PipeWire CLI for sink discovery
# Note: Debian Trixie only has 'vlc' (not vlc-nox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    vlc \
    libvlc-dev \
    vlc-plugin-base \
    vlc-plugin-access-extra \
    libasound2 \
    alsa-utils \
    pulseaudio-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Disable VLC GUI components (we run headless)
ENV VLC_PLUGIN_PATH=/usr/lib/vlc/plugins

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (paths relative to context ./services)
COPY audio-service/src/ ./src/
COPY audio-service/config/ ./config/
# Testton fuer den Ersteinrichtungs-Assistenten (POST /test-tone)
COPY audio-service/assets/ ./assets/

# Create state directory
RUN mkdir -p ./state

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Create non-root user for security
RUN useradd -m -u 1000 minabox && \
    chown -R minabox:minabox /app

# Switch to non-root user
USER minabox

# Expose FastAPI port
EXPOSE 8003

# Python module path: src/ contains the audio_service package
ENV PYTHONPATH=/app/src

# -- Version (Build-Args; docs/Versionierung.md) ------------------------------
# Die Defaults sind absichtlich "dev": ein lokal gebautes Image soll sich nicht
# als Release ausgeben. Der Block steht am Ende der Datei, damit ein
# Versionswechsel nur die letzten Metadaten-Layer ungueltig macht.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-audio" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "audio_service.main"]
