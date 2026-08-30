# =============================================================================
# Minabox WebUI Service
# Multi-stage build: Node.js (build) → Nginx (serve)
# =============================================================================
# syntax=docker/dockerfile:1 (enables BuildKit cache mounts)
# Build: docker build ... or DOCKER_BUILDKIT=1 docker compose build webui
# =============================================================================

# ---- Stage 1: Build React app ----
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (separate layer for caching; npm cache speeds up rebuilds)
#
# npm ci, not npm install: ci installs exactly what package-lock.json pins and
# fails if the two have drifted apart, while install is free to pick up newer
# patch versions. An image whose version number promises immutability must not
# depend on the day it was built. No --omit=dev - Vite and TypeScript live in
# devDependencies and are what does the building.
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

# Copy source and build (build:fast = vite only, no tsc; much faster on Raspberry Pi)
# Locales werden direkt aus public/locales/ kopiert – kein Generierungsschritt mehr.
COPY . .
RUN npm run build:fast

# ---- Stage 2: Serve with Nginx ----
# alpine-slim, not alpine: the full image carries njs, XSLT, GeoIP and the
# image filter (92.8 MB vs 21.8 MB), none of which is used here. Verified
# before the switch: alpine-slim is still built --with-http_gzip_static_module,
# so the pre-compressed .gz files keep being served, and --with-http_v2_module.
# It has no curl, only BusyBox wget - see the health check below.
FROM nginx:alpine-slim

# Remove default nginx config
RUN rm -f /etc/nginx/nginx.conf

# Copy Nginx configuration (nginx.conf includes security-headers.conf)
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/security-headers.conf /etc/nginx/security-headers.conf

# Copy built React app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Health check via nginx health endpoint.
#
# wget, not curl: alpine-slim ships BusyBox wget and no curl at all.
# 127.0.0.1, not localhost: BusyBox wget resolves localhost to ::1 first and
# gives up when that is refused, while nginx above listens on IPv4 only
# (listen 80). curl used to paper over this by falling back to IPv4.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:80/health || exit 1

# -- Version (build args) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-webui" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"

CMD ["nginx", "-g", "daemon off;"]
