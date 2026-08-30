# Multi-Stage: Builder (build context: ./services)
FROM python:3.13-slim AS builder

WORKDIR /app

# No toolchain here on purpose: every dependency of this service ships a
# manylinux wheel for aarch64 and amd64, so nothing is compiled. Adding gcc
# "just in case" would only slow the build and grow the cache.

# Install shared-lib first, then host-helper requirements
COPY shared-lib ./shared-lib
COPY host-helper-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt

# Runtime
FROM python:3.13-slim

WORKDIR /app

# curl is for the compose healthcheck and is the only thing this image needs
# from apt. Everything the service runs against the host - nsenter, chroot -
# is already in the base image, and the host tools themselves (docker, nmcli,
# systemctl, bluetoothctl) are reached through the host's own namespaces, not
# installed here. An earlier version pulled in docker.io, which on Debian is
# the *daemon* and not the CLI: 253 MB that were never executed.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY host-helper-service/src/ ./src/

# No USER directive: the service exists to chroot and nsenter into the host and
# to write /etc/shadow, all of which need uid 0. docker-compose.yml pins
# "user: 0:0" accordingly. A non-root user here would only be decoration.

EXPOSE 8000

# -- Version (build args) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-host-helper" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "host_helper.main"]
