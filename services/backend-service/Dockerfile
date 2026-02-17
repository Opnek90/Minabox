# Stage 1: Build dependencies
FROM python:3.13-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies to /opt/venv
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini .

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

# Set Python path
ENV PYTHONPATH=/app/src

# Run application
CMD ["python", "-m", "backend_service.main"]
