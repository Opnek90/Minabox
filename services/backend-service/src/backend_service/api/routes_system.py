"""REST API endpoints for system status and health."""

import time

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import HealthCheckResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

# Service start time
_start_time = time.time()

# MQTT client will be injected at startup
_mqtt_client: MQTTClient | None = None


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for system routes.

    Args:
        mqtt_client: MQTT client instance
    """
    global _mqtt_client
    _mqtt_client = mqtt_client


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse:
    """Health check endpoint.

    Returns:
        Health status
    """
    uptime_seconds = int(time.time() - _start_time)

    # Check database connection
    try:
        db.execute("SELECT 1")
        database_connected = True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        database_connected = False

    # Check MQTT connection
    mqtt_connected = _mqtt_client.is_connected() if _mqtt_client else False

    status = "healthy" if (database_connected and mqtt_connected) else "unhealthy"

    return HealthCheckResponse(
        status=status,
        service="backend",
        version="0.1.0",
        uptime_seconds=uptime_seconds,
        mqtt_connected=mqtt_connected,
        database_connected=database_connected,
    )
