# Multi-Stage: Builder (build context: ./services)
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install shared-lib first, then host-helper requirements
COPY shared-lib ./shared-lib
COPY host-helper-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir ./shared-lib && \
    pip install --no-cache-dir -r requirements.txt

# Runtime
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl docker.io docker-compose && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONPATH=/app/src

COPY host-helper-service/src/ ./src/

RUN useradd -m -u 1000 minabox && chown -R minabox:minabox /app

USER minabox

EXPOSE 8000

CMD ["python", "-m", "host_helper.main"]
