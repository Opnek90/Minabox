"""FastAPI routes for the RFID service.

This module provides a minimal REST API with a health check endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from fastapi import FastAPI
from shared_lib.version import get_version

from ..config_schema import AppConfig
from ..core import RFIDManager
from ..infrastructure import MQTTClient

logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    mqtt_client: MQTTClient,
    manager_provider: Callable[[], RFIDManager | None],
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration.
        mqtt_client: MQTT client instance.
        manager_provider: Returns the RFID manager once it exists. Passed as a
            callable because the API server starts before the manager does.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Minabox RFID Service",
        description="PN532-based RFID tag reader service for Minabox",
        version=get_version(),
    )

    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint.

        Reports the MQTT connection and the state of the reader and scan loop.
        The endpoint always answers with HTTP 200 and expresses trouble in the
        ``status`` field: a container that is merely waiting for the broker or
        for hardware should be visible, not killed by the container health
        check.
        """
        manager = manager_provider()
        reader_state: dict[str, Any] = (
            manager.status_snapshot()
            if manager is not None
            else {
                "reader_id": None,
                "reader_ready": False,
                "scan_loop_alive": False,
                "mode": None,
                "tag_present": False,
                "tag_id": None,
                "last_scan_age_s": None,
                "last_error": None,
            }
        )

        # is_connected is the live socket state, so an outage shows up here.
        healthy = (
            mqtt_client.is_connected
            and reader_state["reader_ready"]
            and reader_state["scan_loop_alive"]
        )

        return {
            "status": "healthy" if healthy else "degraded",
            "service": "rfid",
            "version": get_version(),
            "device_id": config.env.minabox_device_id,
            "mqtt_connected": mqtt_client.is_connected,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
            "reader": reader_state,
        }

    return app
