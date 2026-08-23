"""REST API endpoints for podcast folders."""

from __future__ import annotations

from backend_service.api.folder_routes import create_folder_router
from backend_service.models.database import Podcast, PodcastFolder

router = create_folder_router(
    folder_model=PodcastFolder,
    item_model=Podcast,
    log_name="podcast",
)
