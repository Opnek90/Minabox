"""Shared Pydantic schemas for Minabox services (e.g. health responses)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BaseHealthResponse(BaseModel):
    """Base health check response schema for all services.

    Status semantics: healthy | degraded | unhealthy.
    Services may extend this model or add extra fields when building the response.
    """

    status: str = Field(..., description="healthy | degraded | unhealthy")
    service: str = Field(..., description="Service name, e.g. audio, backend, button")
    device_id: str = Field(..., description="Minabox device id")
    mqtt_connected: bool = Field(..., description="Whether MQTT broker is connected")
    mqtt_broker: str | None = Field(default=None, description="MQTT broker host")
    mqtt_port: int | None = Field(default=None, description="MQTT broker port")

    model_config = {"extra": "allow"}  # Allow service-specific fields (uptime_seconds, etc.)


def build_health_body(
    *,
    status: str,
    service: str,
    device_id: str,
    mqtt_connected: bool,
    mqtt_broker: str | None = None,
    mqtt_port: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a health response dict with common fields and optional extras."""
    body: dict[str, Any] = {
        "status": status,
        "service": service,
        "device_id": device_id,
        "mqtt_connected": mqtt_connected,
        "mqtt_broker": mqtt_broker,
        "mqtt_port": mqtt_port,
    }
    body.update({k: v for k, v in extra.items() if v is not None})
    return body
