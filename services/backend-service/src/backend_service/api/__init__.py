"""REST API for Backend Service."""

from fastapi import APIRouter

from backend_service.api import (
    routes_audio,
    routes_config,
    routes_host,
    routes_playlists,
    routes_rfid,
    routes_system,
    routes_tags,
    routes_tracks,
)

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(routes_tags.router, prefix="/tags", tags=["Tags"])
api_router.include_router(
    routes_playlists.router, prefix="/playlists", tags=["Playlists"]
)
api_router.include_router(routes_tracks.router, prefix="/tracks", tags=["Tracks"])
api_router.include_router(routes_audio.router, prefix="/audio", tags=["Audio"])
api_router.include_router(routes_rfid.router, prefix="/rfid", tags=["RFID"])
api_router.include_router(routes_config.router, prefix="/config", tags=["Config"])
api_router.include_router(routes_system.router, prefix="/system", tags=["System"])
api_router.include_router(routes_host.router, prefix="/system", tags=["System"])

__all__ = ["api_router"]
