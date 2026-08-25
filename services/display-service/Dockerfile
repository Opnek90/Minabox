# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# No apt layer, and no compiler. Every dependency of this service resolves to a
# prebuilt wheel on aarch64 - Pillow and pydantic-core ship manylinux wheels,
# everything else is pure Python - so gcc, libjpeg-dev, zlib1g-dev and
# libfreetype6-dev were installed on every build and never used.
#
# --only-binary=:all: is what keeps that true. Without it, a future release that
# drops the aarch64 wheel would quietly fall back to building from source and
# fail on the missing toolchain; with it, pip says so instead.

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY display-service/requirements.txt ./requirements.txt
#
# The rm keeps the build tooling out of the runtime image. Nothing installs
# anything at runtime, and no runtime dependency needs pkg_resources.
#
# pip is in the list for a different reason than the rest. The runtime image
# keeps the copy python:3.13-slim ships in its own base layer either way, and
# a whiteout on top of that would save nothing. But without this rm the COPY
# below lays a *second* pip over the first, which measures 12 MB.
RUN pip install --no-cache-dir --only-binary=:all: ./shared-lib && \
    pip install --no-cache-dir --only-binary=:all: -r requirements.txt && \
    rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/site-packages/setuptools \
           /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.13/site-packages/pkg_resources \
           /usr/local/lib/python3.13/site-packages/wheel \
           /usr/local/lib/python3.13/site-packages/wheel-*.dist-info

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# fonts-dejavu-core is the only thing this image needs from apt: it carries
# DejaVu Sans and Sans Mono, which are the `sans` and `mono` font settings, and
# the shipped config uses `sans`.
#
# libjpeg62-turbo, libfreetype6 and zlib1g used to be here and are not needed.
# Pillow's aarch64 wheel bundles its own freetype, libjpeg and libpng under
# PIL/../pillow.libs - verified with ldd, nothing in PIL/*.so resolves to a
# system copy - and libz comes with the base image.
#
# curl stays, deliberately. Replacing it with a Python health check saves
# 14.5 MB but costs 6 % of a CPU core: python:3.13-slim ships no compiled
# bytecode for the standard library, and this container runs unprivileged
# against root-owned directories, so every probe recompiles ssl, email and
# http.client from source - 2.13 s of CPU versus 0.052 s for curl, every 30
# seconds, forever. See docs/services/display/GoLive-Review.md section 5.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies. /usr/local/bin is deliberately not copied: the entrypoint
# is `python -m`, and the console scripts in there belong to packages this
# service never invokes.
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# Copy application code (paths relative to context ./services)
COPY display-service/src/ ./src/
COPY display-service/config/ ./config/

# API_PORT is configurable, so the probe has to follow it. Shell form on
# purpose: the exec form would pass the ${...} through literally.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f "http://localhost:${API_PORT:-8000}/health" || exit 1

RUN useradd -m -u 1000 minabox && chown -R minabox:minabox /app

# Compose overrides this with ${HOST_UID}:${I2C_GID}; the numeric i2c group id
# does not belong in the image, where it would be wrong on any box that numbers
# the group differently.
USER minabox

EXPOSE 8000

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-display" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "display_service.main"]
