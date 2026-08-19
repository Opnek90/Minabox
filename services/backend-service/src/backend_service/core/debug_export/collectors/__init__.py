"""Importing this package registers every collector in the allowlist."""

from backend_service.core.debug_export.collectors import (  # noqa: F401
    data,
    services,
    system,
)

__all__ = ["data", "services", "system"]
