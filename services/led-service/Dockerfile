# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Nur grundlegende Build-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Nur curl für Health-Check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1

RUN useradd -m -u 1000 minabox
RUN chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "led_service.main"]
