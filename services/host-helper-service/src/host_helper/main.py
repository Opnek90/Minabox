"""Host-Helper service entry point."""

from __future__ import annotations

import logging
import sys

import structlog
import uvicorn
from fastapi import FastAPI

from host_helper.api.routes import router, set_config
from shared_lib.exceptions import ConfigError

from host_helper.config import load_config

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


def create_app(config: dict) -> FastAPI:
    app = FastAPI(title="Minabox Host-Helper", version="0.1.0")
    app.include_router(router)
    return app


def run() -> None:
    try:
        config = load_config()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config["log_level"])
    set_config(config)

    logger.info("host_helper_starting", port=config["port"])
    app = create_app(config)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config["port"],
        log_config=None,
    )


if __name__ == "__main__":
    run()
