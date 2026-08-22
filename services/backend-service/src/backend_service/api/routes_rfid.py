"""REST API endpoints for RFID control."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from backend_service.core.api_errors import ApiError
from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import RFIDLearningModeCommand

logger = structlog.get_logger(__name__)
router = APIRouter()

# MQTT client will be injected at startup
_mqtt_client: MQTTClient | None = None


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for RFID routes.

    Args:
        mqtt_client: MQTT client instance
    """
    global _mqtt_client
    _mqtt_client = mqtt_client


@router.post("/learning-mode")
async def set_learning_mode(command: RFIDLearningModeCommand) -> dict:
    """Enable or disable RFID learning mode.

    Publishes to minabox/<device-id>/rfid/cmd/set-mode via MQTT.

    Args:
        command: Learning mode command with enabled flag

    Returns:
        Success response with active state
    """
    mode = "learning" if command.enabled else "normal"
    logger.info("api_rfid_set_learning_mode", enabled=command.enabled, mode=mode)

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    await _mqtt_client.publish_rfid_command("cmd/set-mode", {"mode": mode})

    return {"status": "ok", "active": command.enabled, "mode": mode}
