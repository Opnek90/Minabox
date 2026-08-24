"""Liveness probe."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from shared_lib.version import get_version as get_build_version

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Deliberately async: this is what the Docker healthcheck polls, and it
    does no blocking work. Keeping it off the threadpool means it stays
    answerable even while a long update occupies the worker threads."""
    return {"status": "ok", "service": "host-helper", "version": get_build_version()}
