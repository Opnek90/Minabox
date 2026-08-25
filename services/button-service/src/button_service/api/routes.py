"""FastAPI routes for the button service.

This module provides a minimal REST API with health check endpoint.
"""

from __future__ import annotations

from collections.abc import Callable

import structlog
from fastapi import FastAPI
from shared_lib.version import get_version

from ..config_schema import AppConfig
from ..infrastructure import MQTTClient
from ..models import HealthState

logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    mqtt_client: MQTTClient,
    get_health_state: Callable[[], HealthState],
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration.
        mqtt_client: MQTT client instance.
        get_health_state: Callable returning the current health snapshot.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Minabox Button Service",
        description="GPIO-based button and rotary encoder service for Minabox",
        version=get_version(),
    )

    @app.get("/health")
    async def health_check() -> dict[str, object]:
        """Health check endpoint.

        Reports ``degraded`` when the broker is away, when buttons are
        configured that could not claim their GPIO pins, or when buttons.json
        cannot be loaded. The container health check only asks whether this
        endpoint answers at all -- a restart would fix none of those.
        """
        # is_connected is the live socket state, so an outage shows up here.
        mqtt_connected = mqtt_client.is_connected
        state = get_health_state()

        return {
            "status": (
                "healthy" if mqtt_connected and state.buttons_usable else "degraded"
            ),
            "service": "button",
            "version": get_version(),
            "device_id": config.env.minabox_device_id,
            # Configured is not the same as usable: a pin another service
            # already owns leaves the button dead while the entry still stands
            # in buttons.json.
            "buttons_configured": state.buttons_configured,
            "buttons_available": state.buttons_available,
            "gpio_enabled": state.gpio_enabled,
            "config_error": state.config_error,
            "mqtt_connected": mqtt_connected,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
        }

    return app
