"""The host-helper HTTP API, assembled from one module per domain.

Splitting it up is the only change; every path, body and response is the same
as when they all lived in one file. The include order below is the order the
routes are registered in.
"""

from fastapi import APIRouter

from host_helper.api.routes import (
    audio,
    backup,
    bluetooth,
    diagnostics,
    health,
    maintenance,
    media,
    network,
    power,
    system,
    update,
    usb,
)
from host_helper.api.routes.deps import get_config, set_config

router = APIRouter()
for _module in (
    health,
    media,
    power,
    network,
    usb,
    backup,
    system,
    maintenance,
    update,
    bluetooth,
    diagnostics,
    audio,
):
    router.include_router(_module.router)

__all__ = ["get_config", "router", "set_config"]
