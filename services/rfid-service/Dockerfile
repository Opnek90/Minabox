# Multi-Stage: Builder
FROM python:3.13-slim AS builder

WORKDIR /app

# Build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libi2c-dev \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY rfid-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt


# Runtime Image
FROM python:3.13-slim

WORKDIR /app

# Runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        i2c-tools && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONPATH=/app/src

# API port: single source for EXPOSE, the health check and the service itself,
# so the three cannot drift apart (see config.py, DEFAULT_API_PORT).
ARG API_PORT=8000
ENV API_PORT=${API_PORT}

# Copy application code (paths relative to context ./services)
COPY rfid-service/src/ ./src/
COPY rfid-service/config/ ./config/

# Non-root user
RUN useradd -m -u 1000 minabox && \
    chown -R minabox:minabox /app

USER minabox

EXPOSE ${API_PORT}

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:${API_PORT}/health || exit 1

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. This block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-rfid" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "rfid_service.main"]
