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

CMD ["nginx", "-g", "daemon off;"]
