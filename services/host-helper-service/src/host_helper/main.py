"""Host-Helper service entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI
from shared_lib.exceptions import ConfigError
from shared_lib.version import get_version as get_build_version

from host_helper.api.routes import router, set_config
from host_helper.config import Config, load_config
from host_helper.netwatch import NetworkMonitor, set_monitor

logger = structlog.get_logger(__name__)


def setup_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    if log_level.upper() == "DEBUG":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def create_app(config: Config) -> FastAPI:
    """Build the app.

    The interactive docs are off unless LOG_LEVEL is DEBUG. /docs and
    /openapi.json are the two routes that never asked for the API key, and on
    a service that runs as root with the host mounted they published the whole
    attack surface - every path, every parameter - to anything that reaches
    the compose network. Someone debugging the service can still turn them on
    the same way they turn on the readable log format.
    """
    debug = config.log_level == "DEBUG"

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # The connectivity watchdog: it brings up the setup hotspot when the
        # box loses its configured Wi-Fi, so a stranded user can still reach
        # the WebUI. Runs here rather than as a host service because the nmcli
        # plumbing it needs already lives in this container.
        monitor = NetworkMonitor()
        set_monitor(monitor)
        task = asyncio.create_task(monitor.run_forever(), name="netwatch")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            set_monitor(None)

    app = FastAPI(
        title="Minabox Host-Helper",
        version=get_build_version(),
        docs_url="/docs" if debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if debug else None,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def run() -> None:
    try:
        config = load_config()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.log_level)
    set_config(config)

    logger.info("host_helper_starting", port=config.port)
    app = create_app(config)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.port,
        log_config=None,
    )


if __name__ == "__main__":
    run()
