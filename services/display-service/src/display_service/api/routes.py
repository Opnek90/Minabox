"""FastAPI routes for the display service."""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from ..config_manager import ConfigManager
from ..config_schema import AppConfig
from ..infrastructure import MQTTClient, is_available
from ..models import HealthResponse

logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    config_manager: ConfigManager,
    mqtt_client: MQTTClient,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Minabox Display Service",
        description="I2C OLED status display service for Minabox",
        version="0.1.0",
    )

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        display_config = config_manager.get_current_config()
        return HealthResponse(
            status="healthy",
            service="display",
            device_id=config.env.minabox_device_id,
            display_enabled=display_config.enabled if display_config else False,
            display_available=is_available(),
            mqtt_connected=mqtt_client.is_connected,
            mqtt_broker=config.env.mqtt_broker,
            mqtt_port=config.env.mqtt_port,
        )

    return app
