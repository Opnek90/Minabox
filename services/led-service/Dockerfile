# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Build-Dependencies: gcc + swig + liblgpio-dev required for lgpio (PWMLED support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    swig \
    liblgpio-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY led-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# liblgpio needed at runtime for the lgpio C extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    liblgpio-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (paths relative to context ./services)
COPY led-service/src/ ./src/
COPY led-service/config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1

RUN useradd -m -u 1000 minabox
RUN chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "led_service.main"]
