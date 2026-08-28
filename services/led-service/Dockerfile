# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Toolchain for building lgpio from source:
# - gcc, libc6-dev, make: the compiler and its headers
# - swig: generates the Python C extension wrapper
# - wget: fetches the lg release tarball
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    make \
    swig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# The lg C library is built from source because PyPI publishes lgpio wheels
# only for cp39-cp312 - on 3.13 pip builds the sdist and has to link against
# liblgpio.so and its header.
#
# Pinned to a tag with its checksum: this used to pull the master branch, so no
# two builds were guaranteed to contain the same library, and nothing verified
# what was downloaded into an image that builds as root and later gets GPIO
# access. v0.2.2 is the release the PyPI package lgpio 0.2.2.0 belongs to.
# Bump the version and the checksum together.
ARG LG_VERSION=v0.2.2
ARG LG_SHA256=b08d8569d6dc8fa91a42ba1e37f620fdcb19d6bf2330e4b7d7301431ddbe124c
RUN wget -q "https://github.com/joan2937/lg/archive/refs/tags/${LG_VERSION}.tar.gz" \
        -O /tmp/lg.tar.gz \
    && echo "${LG_SHA256}  /tmp/lg.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/lg.tar.gz -C /tmp \
    && cd /tmp/lg-* \
    # Only the library and its header, not "make install": that also drops the
    # rgpiod and rgs daemons into /usr/local/bin, which this service never runs.
    && make \
    && install -m 0755 liblgpio.so.1 /usr/local/lib/ \
    && ln -sf liblgpio.so.1 /usr/local/lib/liblgpio.so \
    && install -m 0644 lgpio.h /usr/local/include/ \
    && ldconfig \
    && cd / \
    && rm -rf /tmp/lg.tar.gz /tmp/lg-*

# Install shared-lib first, then service requirements (context: ./services)
COPY shared-lib ./shared-lib
COPY led-service/requirements.txt ./requirements.txt
#
# The rm drops the build tooling pip pulled in to compile the lgpio sdist.
# Nothing installs anything at runtime, and no runtime dependency needs
# pkg_resources - gpiozero resolves its pin factories through
# importlib.metadata, and click 8 stopped using it years ago.
#
# pip is in the list for a different reason than the rest. The runtime image
# keeps the copy python:3.13-slim ships in its own base layer either way, and
# a whiteout on top of that would save nothing. But without this rm the COPY
# below lays a *second* pip over the first, which measured 7 MB.
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/site-packages/setuptools \
           /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.13/site-packages/pkg_resources \
           /usr/local/lib/python3.13/site-packages/wheel \
           /usr/local/lib/python3.13/site-packages/wheel-*.dist-info

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# No apt layer at all. curl used to live here purely for the health check;
# Python is already in the image and can make the same request.
# Copy liblgpio.so from builder so the _lgpio.so extension can load at runtime
COPY --from=builder /usr/local/lib/liblgpio.so* /usr/local/lib/
RUN ldconfig

# Python dependencies (including the compiled lgpio extension). /usr/local/bin
# is deliberately not copied: the entrypoint is `python -m`, and the console
# scripts in there belong to packages this service never invokes.
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# python:3.13-slim ships no compiled bytecode for the standard library, and the
# container runs as a non-root user against root-owned directories - so it can
# never write a __pycache__ either. The Python health check therefore
# re-translated ssl, email, http.client and urllib.parse from source on every
# single run: measured 2.05 s of CPU, which at interval=30s is ~6 % of a core,
# permanently, and more than the service itself uses.
#
# Precompiling once at build time brings the same import down to 0.53 s and
# takes the same translation out of the service start as well. The price is
# 27 MB on the image (minabox-button measured 229 MB -> 256 MB).
#
# Has to run as root, before USER: that the service user cannot write there is
# the whole reason the bytecode was missing. compileall writes regardless of
# PYTHONDONTWRITEBYTECODE, so the ENV further down does not interfere.
RUN python -m compileall -q /usr/local/lib/python3.13 > /dev/null

# Copy application code (paths relative to context ./services)
COPY led-service/src/ ./src/
COPY led-service/config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

# /app has to stay writable: lgpio creates a notification file (.lgd-nfy0)
# in the working directory.
RUN useradd -u 1000 -M -d /nonexistent -s /usr/sbin/nologin minabox && chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-led" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "led_service.main"]
