# Stage 1: Build dependencies
# Build context must be ./services (parent of backend-service) so shared-lib is available
FROM python:3.13-slim AS builder

WORKDIR /app

# gcc only. g++ used to be here for packages that no longer build from source
# on arm64 - every dependency ships a wheel - and a C++ toolchain costs minutes
# of build time for nothing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install shared-lib first (minabox-shared), then backend requirements
COPY shared-lib ./shared-lib
COPY backend-service/requirements.txt ./requirements.txt
# Drop the builder's own pip/setuptools before the runtime stage copies this
# directory - they would otherwise be carried across for nothing.
#
# It has to happen here, not after the COPY: layers are additive, so deleting
# afterwards adds a whiteout and leaves the bytes in the layer underneath.
#
# Note this does not remove pip from the image. The runtime base ships its own
# copy in the same directory, and the COPY merges rather than replaces. Getting
# rid of that one would mean rebuilding the base image, which is not worth it.
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt && \
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

# curl is here for the health check. A Python one-liner would save the ~14 MB,
# but it would also start a CPython process every 30 seconds, which on a Pi
# costs more than the space is worth.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# PYTHONPATH so `python -m backend_service.main` finds the package.
# PYTHONUNBUFFERED because Python buffers stdout when it is not attached to a
# terminal, and a log line that arrives late is worth nothing while a box is
# hanging.
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Copy application code (paths relative to context ./services)
COPY backend-service/src/ ./src/
COPY backend-service/config/ ./config/
COPY backend-service/alembic/ ./alembic/
COPY backend-service/alembic.ini .

# Create directories for data and audio
RUN mkdir -p /data /mnt/audio/tracks

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Create non-root user
RUN useradd -u 1000 -M -d /nonexistent -s /usr/sbin/nologin minabox && \
    chown -R minabox:minabox /app /data /mnt/audio

USER minabox

# Expose API port
EXPOSE 8080

# Run application
# -- Version (build args) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so a version
# change only invalidates the last few metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-backend" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "backend_service.main"]
