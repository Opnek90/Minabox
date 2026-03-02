# Stage 1: Build dependencies
# Build context must be ./services (parent of backend-service) so shared-lib is available
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install shared-lib first (minabox-shared), then backend requirements
COPY shared-lib ./shared-lib
COPY backend-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set Python path
ENV PYTHONPATH=/app/src

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
RUN useradd -m -u 1000 minabox && \
    chown -R minabox:minabox /app /data /mnt/audio

USER minabox

# Expose API port
EXPOSE 8080

# Run application
CMD ["python", "-m", "backend_service.main"]
