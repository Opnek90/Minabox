# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Build liblgpio C library from source (lg repo); then pip install lgpio links against it
# swig required for building the lgpio Python package from PyPI
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    git \
    make \
    swig \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone lg, build C library only, install to /usr/local so pip install lgpio can find it
RUN git clone --depth 1 https://github.com/joan2937/lg /tmp/lg \
    && cd /tmp/lg \
    && make \
    && install -m 0755 liblgpio.so.1 /usr/local/lib/ \
    && ln -sf liblgpio.so.1 /usr/local/lib/liblgpio.so \
    && install -m 0644 lgpio.h /usr/local/include/ \
    && ldconfig \
    && cd / \
    && rm -rf /tmp/lg

# App dependencies (pip install lgpio compiles against /usr/local liblgpio)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# liblgpio required at runtime by the lgpio Python module (gpiozero pin factory)
COPY --from=builder /usr/local/lib/liblgpio.so* /usr/local/lib/
RUN ldconfig

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1

RUN useradd -m -u 1000 minabox

# lgpio may create pipes/lock files; provide a writable directory
RUN mkdir -p /tmp/lgpio && chown minabox:minabox /tmp/lgpio && chmod 755 /tmp/lgpio

RUN chown -R minabox:minabox /app

USER minabox
WORKDIR /app/src

ENV GPIOZERO_PIN_FACTORY=lgpio

CMD ["python", "-m", "button_service.main"]
