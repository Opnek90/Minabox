# ============================================================
# Stage 1: Python dependencies
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

COPY tts-service/requirements.txt .
# Every dependency ships a prebuilt py3-none-any or manylinux/cp313 aarch64
# wheel - nothing here compiles, so this stage needs no compiler. The heavy
# part of this service is not a wheel at all: Piper arrives as a binary below.
RUN pip install --no-cache-dir --prefix=/app/deps -r requirements.txt

# ============================================================
# Stage 2: Piper and its voices
# ============================================================
# Fetched in a stage of its own so a changed voice list does not invalidate the
# Python layer, and so nothing that only exists to unpack a tarball - curl, the
# tarball itself - ends up in the runtime image.
FROM debian:bookworm-slim AS piper

ARG TARGETARCH
# The published Linux build is self-contained: the executable, its ONNX
# runtime and the espeak phoneme data in one tarball. That is deliberately not
# the pip package - `piper-tts` drags in onnxruntime and piper-phonemize, whose
# wheels have to exist for exactly this Python version on arm64, and a box that
# cannot be built is worse than one that speaks a little later.
ARG PIPER_VERSION=2023.11.14-2
# Piper's "low" tier - about 60 MB per language. Measured on a Raspberry Pi 4 it
# needs roughly 1.5 s of inference for a four-word phrase; the higher tiers are
# slower again for a difference nobody notices in an announcement this short,
# and the box pays that price on every card it has not said before.
ARG VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main
ARG VOICE_DE=de/de_DE/thorsten/low/de_DE-thorsten-low
ARG VOICE_EN=en/en_US/lessac/low/en_US-lessac-low

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH:-arm64}" in \
      arm64) arch=aarch64 ;; \
      amd64) arch=x86_64 ;; \
      arm)   arch=armv7l ;; \
      *) echo "No Piper build for ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/piper.tar.gz \
      "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${arch}.tar.gz"; \
    mkdir -p /opt; \
    tar -xzf /tmp/piper.tar.gz -C /opt; \
    rm /tmp/piper.tar.gz; \
    test -x /opt/piper/piper

RUN set -eu; \
    mkdir -p /opt/piper/voices; \
    for voice in "${VOICE_DE}" "${VOICE_EN}"; do \
      name="$(basename "${voice}")"; \
      curl -fsSL -o "/opt/piper/voices/${name}.onnx"      "${VOICE_BASE}/${voice}.onnx"; \
      curl -fsSL -o "/opt/piper/voices/${name}.onnx.json" "${VOICE_BASE}/${voice}.onnx.json"; \
      test -s "/opt/piper/voices/${name}.onnx"; \
    done

# ============================================================
# Stage 3: Runtime
# ============================================================
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -M -d /nonexistent -s /usr/sbin/nologin minabox \
    && mkdir -p /announcements \
    && chown minabox:minabox /announcements

# --chown here, not a separate `chown -R` after the copy: a metadata-only
# change on overlayfs forces a full copy-up of every file into a new layer.
COPY --from=piper --chown=minabox:minabox /opt/piper /opt/piper
# The tarball's own libraries sit next to the executable. Its RPATH normally
# finds them; naming the directory as well costs nothing and turns a linker
# error at the first announcement into one that never happens.
ENV LD_LIBRARY_PATH=/opt/piper

COPY --from=builder --chown=minabox:minabox /app/deps /app/deps
ENV PATH=/app/deps/bin:$PATH
ENV PYTHONPATH=/app/src:/app/deps/lib/python3.13/site-packages

COPY --chown=minabox:minabox tts-service/src/ ./src/

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8008/health || exit 1

USER minabox

# -- Version (build args) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-tts" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "tts_service.main"]
