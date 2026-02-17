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

# Install packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Runtime Image
FROM python:3.13-slim

WORKDIR /app

# Runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        i2c-tools && \
    rm -rf /var/lib/apt/lists/*

# **KOPIERE Python packages aus Builder**
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# **PYTHONPATH setzen**
ENV PYTHONPATH=/app/src

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Non-root user
RUN useradd -m -u 1000 minabox && \
    chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "rfid_service.main"]
