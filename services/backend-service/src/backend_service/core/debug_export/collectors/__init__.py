"""Importing this package registers every collector in the allowlist."""

from backend_service.core.debug_export.collectors import (  # noqa: F401
    audio,
    data,
    services,
    system,
)

__all__ = ["audio", "data", "services", "system"]
