# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

COPY media-downloader-service/requirements.txt .
# Every dependency ships a prebuilt py3-none-any or manylinux/cp313 aarch64
# wheel (verified against the built image) - nothing here compiles, so this
# stage needs no compiler.
RUN pip install --no-cache-dir --prefix=/app/deps -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 minabox \
    && mkdir -p /mnt/audio/tracks/downloads \
    && chown minabox:minabox /mnt/audio/tracks/downloads

# --chown here, not a separate `chown -R` after the copy: a metadata-only
# change on overlayfs forces a full copy-up of every file into a new layer,
# which nearly doubled the cost of these two COPY layers.
COPY --from=builder --chown=minabox:minabox /app/deps /app/deps
ENV PATH=/app/deps/bin:$PATH
ENV PYTHONPATH=/app/src:/app/deps/lib/python3.13/site-packages

COPY --chown=minabox:minabox media-downloader-service/src/ ./src/

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8007/health || exit 1

USER minabox

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-media-downloader" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "media_downloader_service.main"]
