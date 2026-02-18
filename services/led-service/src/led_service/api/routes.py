"""FastAPI routes for the LED service.

This module provides a minimal REST API with health check endpoint.
"""

from __future__ import annotations

from typing import Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog


class TestLEDRequest(BaseModel):
    led_id: str

from ..config_schema import AppConfig
from ..led_controller import LEDManager
from ..mqtt_client import MQTTClient


logger = structlog.get_logger(__name__)


def create_app(
    config: AppConfig,
    led_manager: LEDManager,
    mqtt_client: MQTTClient,
) -> FastAPI:
    """Create and configure the FastAPI application.
    
    Args:
        config: Application configuration.
        led_manager: LED manager instance.
        mqtt_client: MQTT client instance.
        
    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Minabox LED Service",
        description="GPIO-based LED control service for Minabox",
        version="0.1.0",
    )
    
    @app.post("/test")
    async def test_led(body: TestLEDRequest) -> Dict[str, object]:
        """Trigger an LED's first binding pattern for testing.

        Returns 404 if the LED is not found or has no bindings.
        """
        success = await led_manager.test_led(body.led_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"LED '{body.led_id}' not found or has no bindings",
            )
        return {"led_id": body.led_id, "tested": True}

    @app.get("/health")
    async def health_check() -> Dict[str, object]:
        """Health check endpoint.
        
        Returns service status and basic statistics.
        """
        # Count configured LEDs
        current_config = led_manager._controllers
        leds_count = len(current_config)
        
        # Check MQTT connection status
        mqtt_connected = mqtt_client._client is not None and mqtt_client._running
        
        return {
            "status": "healthy",
            "service": "led",
            "device_id": config.env.minabox_device_id,
            "leds_configured": leds_count,
            "mqtt_connected": mqtt_connected,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
        }
    
    return app
