"""FastAPI routes for the display service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, HTTPException
from shared_lib.version import get_version

from ..config_manager import ConfigManager
from ..config_schema import AppConfig
from ..infrastructure import MQTTClient, is_available
from ..models import HealthResponse

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..main import DisplayService


def create_app(
    config: AppConfig,
    config_manager: ConfigManager,
    mqtt_client: MQTTClient,
    service: DisplayService | Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Minabox Display Service",
        description="I2C OLED status display service for Minabox",
        version=get_version(),
    )

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        display_config = config_manager.get_current_config()
        display_enabled = display_config.enabled if display_config else False
        display_available = is_available()
        # Configured is not the same as usable. A panel that never answered on
        # the I2C bus reported "healthy" for as long as the broker was up,
        # which is the one thing this endpoint is asked about.
        panel_usable = display_available or not display_enabled
        # is_connected is the live socket state, so an outage shows up here.
        return HealthResponse(
            status=(
                "healthy" if mqtt_client.is_connected and panel_usable else "degraded"
            ),
            service="display",
            version=get_version(),
            device_id=config.env.minabox_device_id,
            display_enabled=display_enabled,
            display_available=display_available,
            mqtt_connected=mqtt_client.is_connected,
            mqtt_broker=config.env.mqtt_broker,
            mqtt_port=config.env.mqtt_port,
        )

    @app.post("/test")
    async def test_display() -> dict[str, object]:
        """Show a brief test pattern so the setup wizard can verify the panel.

        Mirrors the LED service's /test endpoint. Returns 404 when no display
        is attached or the service is disabled, so the wizard can say so
        instead of claiming a successful test.
        """
        if service is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        if not await service.show_test_pattern():
            raise HTTPException(
                status_code=404,
                detail="Display not available or disabled",
            )
        return {"tested": True}

    return app
