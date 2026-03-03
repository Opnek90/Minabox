from __future__ import annotations

import logging
from typing import Iterable

import structlog


def setup_structlog(log_level: str, *, silence_loggers: Iterable[str] | None = None) -> None:
    """Configure structlog-based logging for a service.

    DEBUG → human-readable console output.
    INFO+ → structured JSON suitable for log aggregation.
    """
    level_name = (log_level or "INFO").upper()
    log_level_int = getattr(logging, level_name, logging.INFO)

    if level_name == "DEBUG":
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
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    if silence_loggers:
        for name in silence_loggers:
            logging.getLogger(name).setLevel(logging.WARNING)

