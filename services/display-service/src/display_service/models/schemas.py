"""Pydantic schemas for API response models."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    service: str
    version: str | None = None
    device_id: str
    display_enabled: bool
    display_available: bool
    mqtt_connected: bool
    mqtt_broker: str
    mqtt_port: int
