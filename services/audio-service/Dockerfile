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

# libVLC plus the Pulse/PipeWire command line tools.
#
# Deliberately NOT the 'vlc' package: that is the desktop player and drags in
# vlc-plugin-qt, which pulls Qt5 and the full Mesa stack - libLLVM (118 MB),
# libgallium (34 MB), libz3 (26 MB). None of it is reachable from a headless
# audio service, and together they were more than half the image.
#
# libvlc5 is the library python-vlc binds against; vlc-plugin-base carries the
# codecs and the pulse output module, vlc-plugin-access-extra the HTTP/HTTPS
# stream access. No ALSA tooling: /dev/snd is not mapped into the container,
# audio only ever leaves through the host's Pulse socket.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libvlc5 \
    vlc-plugin-base \
    vlc-plugin-access-extra \
    pulseaudio-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# No VLC_PLUGIN_PATH: the plugin directory is architecture-specific
# (/usr/lib/<triplet>/vlc/plugins), so any fixed value is wrong on some
# platform. libVLC finds its own plugins.

# Do not write .pyc files (the source is read-only anyway) and keep stdout
# unbuffered so structlog output reaches the container log immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (paths relative to context ./services)
COPY audio-service/src/ ./src/
COPY audio-service/config/ ./config/
# Test tone for the first-run setup wizard (POST /test-tone)
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

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
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
