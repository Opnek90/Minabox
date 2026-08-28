# Stage 1: Build
FROM python:3.13-slim AS builder

WORKDIR /app

# Toolchain for building lgpio from source:
# - gcc, libc6-dev, make: the compiler and its headers
# - swig: generates the Python C extension wrapper
# - wget: fetches the lg release tarball
#
# No python3-dev: python:3.13-slim already ships the headers under
# /usr/local/include/python3.13, which is what the lgpio sdist links against.
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
# Pinned to a tag with its checksum: this used to `git clone` the master
# branch, so no two builds were guaranteed to contain the same library, and
# nothing verified what was downloaded into an image that builds as root and
# later gets GPIO access. v0.2.2 is the release the PyPI package lgpio 0.2.2.0
# belongs to. Bump the version and the checksum together.
ARG LG_VERSION=v0.2.2
ARG LG_SHA256=b08d8569d6dc8fa91a42ba1e37f620fdcb19d6bf2330e4b7d7301431ddbe124c

# How long lg's alert thread waits in ppoll() before looking again, in
# nanoseconds. Upstream ships 5e5 (0.5 ms), which means 2000 wakeups a second
# whether or not a pin moved - measured at ~6 % of a core on a Pi 4, and by far
# the biggest single consumer on the box. 2 ms costs ~2.3 % instead.
#
# This does not delay event *detection*: a real edge makes ppoll return at
# once, and the timestamps come from the kernel either way. It delays only how
# soon a batch is handed on, by at most this interval on top of the 0.5 ms lg
# already waits to sort events into time order. Imperceptible for a press;
# a very fast encoder turn arrives in slightly larger batches.
#
# Raise it to trade more latency for less CPU, or set it back to 500000 for
# upstream behaviour. The grep afterwards is deliberate: if a future lg release
# rewrites that line, the build must fail loudly instead of silently shipping
# an unpatched library.
ARG LG_ALERT_POLL_NS=2000000

RUN wget -q "https://github.com/joan2937/lg/archive/refs/tags/${LG_VERSION}.tar.gz" \
        -O /tmp/lg.tar.gz \
    && echo "${LG_SHA256}  /tmp/lg.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/lg.tar.gz -C /tmp \
    && cd /tmp/lg-* \
    && sed -i "s/struct timespec tspec = {0, 5e5};/struct timespec tspec = {0, ${LG_ALERT_POLL_NS}};/" lgPthAlerts.c \
    && grep -q "struct timespec tspec = {0, ${LG_ALERT_POLL_NS}};" lgPthAlerts.c \
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
COPY button-service/requirements.txt ./requirements.txt
#
# The rm drops the build tooling pip pulled in to compile the lgpio sdist.
# Nothing installs anything at runtime, and no runtime dependency needs
# pkg_resources - gpiozero resolves its pin factories through
# importlib.metadata.
#
# pip is in the list for a different reason than the rest. The runtime image
# keeps the copy python:3.13-slim ships in its own base layer either way, and
# a whiteout on top of that would save nothing. But without this rm the COPY
# below lays a *second* pip over the first, which measures 12 MB.
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

# curl is the container health check (see HEALTHCHECK below). The Python
# one-liner that briefly replaced it re-translated ssl, email and http.client
# from source on every run - python:3.13-slim ships no stdlib bytecode and the
# non-root container cannot write __pycache__ - which cost ~6 % of a core.
# curl is one apt package, and the whole project standardises on it:
# docs/Entwicklungs-Workflow.md, "Container-Healthcheck".
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# liblgpio is required at runtime by the lgpio Python module (gpiozero pin factory).
COPY --from=builder /usr/local/lib/liblgpio.so* /usr/local/lib/
RUN ldconfig

# Python dependencies (including the compiled lgpio extension). /usr/local/bin
# is deliberately not copied: the entrypoint is `python -m`, and the console
# scripts in there belong to packages this service never invokes.
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# Copy application code (paths relative to context ./services)
COPY button-service/src/ ./src/
COPY button-service/config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# /app has to stay writable: lgpio creates a notification file (.lgd-nfy0)
# in the working directory.
RUN useradd -u 1000 -M -d /nonexistent -s /usr/sbin/nologin minabox && chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GPIOZERO_PIN_FACTORY=lgpio

# -- Version (build args; docs/Versionierung.md) ------------------------------
# The defaults are deliberately "dev": a locally built image must not pass
# itself off as a release. The block sits at the end of the file so that a
# version change only invalidates the last metadata layers.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-button" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}

CMD ["python", "-m", "button_service.main"]
