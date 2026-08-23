"""REST API endpoints for stream folders."""

from __future__ import annotations

from backend_service.api.folder_routes import create_folder_router
from backend_service.models.database import Stream, StreamFolder

router = create_folder_router(
    folder_model=StreamFolder,
    item_model=Stream,
    log_name="stream",
)
