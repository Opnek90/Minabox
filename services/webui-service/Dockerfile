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
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# Copy source and build (build:fast = vite only, no tsc; much faster on Raspberry Pi)
# Locales werden direkt aus public/locales/ kopiert – kein Generierungsschritt mehr.
COPY . .
RUN npm run build:fast

# ---- Stage 2: Serve with Nginx ----
FROM nginx:alpine

# Remove default nginx config
RUN rm -f /etc/nginx/nginx.conf

# Copy Nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy built React app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Health check via nginx health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# -- Version (build args; docs/Versionierung.md) ------------------------------
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
