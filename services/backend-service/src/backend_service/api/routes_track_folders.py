"""REST API endpoints for track folders."""

from __future__ import annotations

from backend_service.api.folder_routes import create_folder_router
from backend_service.models.database import Track, TrackFolder

router = create_folder_router(
    folder_model=TrackFolder,
    item_model=Track,
    log_name="track",
)
