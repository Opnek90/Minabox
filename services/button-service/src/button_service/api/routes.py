"""FastAPI routes for the button service.

This module provides a minimal REST API with health check endpoint.
"""

from __future__ import annotations

from typing import Callable, Dict

from fastapi import FastAPI
import structlog

from ..config_schema import AppConfig
from ..infrastructure import MQTTClient


logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    mqtt_client: MQTTClient,
    get_buttons_count: Callable[[], int],
) -> FastAPI:
    """Create and configure the FastAPI application.
    
    Args:
        config: Application configuration.
        mqtt_client: MQTT client instance.
        get_buttons_count: Callable that returns current number of configured buttons.
        
    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Minabox Button Service",
        description="GPIO-based button and rotary encoder service for Minabox",
        version="0.1.0",
    )
    
    @app.get("/health")
    async def health_check() -> Dict[str, object]:
        """Health check endpoint.
        
        Returns service status and basic statistics.
        """
        return {
            "status": "healthy",
            "service": "button",
            "device_id": config.env.minabox_device_id,
            "buttons_configured": get_buttons_count(),
            "mqtt_connected": mqtt_client.is_connected,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
        }
    
    return app
