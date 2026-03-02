from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .schemas_enums import ServiceState


class HealthCheckResponse(BaseModel):
    """Schema for health check response."""

    status: str = Field(..., description="Health status (healthy/unhealthy)")
    service: str = "backend"
    version: str = "0.1.0"
    uptime_seconds: int = Field(..., ge=0)
    mqtt_connected: bool
    database_connected: bool


class ServiceStatus(BaseModel):
    """Schema for individual service status."""

    service: str
    state: ServiceState
    last_seen: datetime | None = None


class SystemStatusResponse(BaseModel):
    """Schema for system status response."""

    backend: ServiceStatus
    audio: ServiceStatus
    rfid: ServiceStatus
    button: ServiceStatus
    led: ServiceStatus
    mqtt_broker: ServiceStatus


__all__ = [
    "HealthCheckResponse",
    "ServiceStatus",
    "SystemStatusResponse",
]

