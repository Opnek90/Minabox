# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Dependencies to build lgpio from source:
# - build-essential: gcc, make, libc6-dev
# - swig: generates Python C extension wrapper
# - wget, tar: download lgpio source
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    swig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Build lgpio C library from source (not available as Debian Trixie package).
# This installs liblgpio.so + lgpio.h into /usr/local so pip can link against it.
RUN wget -q https://github.com/joan2937/lg/archive/refs/heads/master.tar.gz -O /tmp/lg.tar.gz \
    && tar -xzf /tmp/lg.tar.gz -C /tmp \
    && cd /tmp/lg-master \
    && make \
    && make install \
    && ldconfig \
    && rm -rf /tmp/lg.tar.gz /tmp/lg-master

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY led-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Runtime: curl for healthcheck + liblgpio.so (copied from builder via site-packages .so)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy liblgpio.so from builder so the _lgpio.so extension can load at runtime
COPY --from=builder /usr/local/lib/liblgpio.so* /usr/local/lib/
RUN ldconfig

# Copy Python dependencies (including compiled lgpio .so)
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
