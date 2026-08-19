"""FastAPI routes for the RFID service.

This module provides a minimal REST API with health check endpoint.
"""

from __future__ import annotations

from typing import Dict

from fastapi import FastAPI
import structlog

from ..config_schema import AppConfig
from ..infrastructure import MQTTClient


logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    mqtt_client: MQTTClient,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration.
        mqtt_client: MQTT client instance.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Minabox RFID Service",
        description="PN532-based RFID tag reader service for Minabox",
        version="0.1.0",
    )

    @app.get("/health")
    async def health_check() -> Dict[str, object]:
        """Health check endpoint.

        Returns service status and basic statistics.
        """
        # is_connected is the live socket state, so an outage shows up here.
        return {
            "status": "healthy" if mqtt_client.is_connected else "degraded",
            "service": "rfid",
            "device_id": config.env.minabox_device_id,
            "mqtt_connected": mqtt_client.is_connected,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
        }

    return app
