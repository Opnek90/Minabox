"""Background task: log system temperature and trigger overheating alert (MQTT + WebSocket)."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend_service.models.database import TemperatureReading

if TYPE_CHECKING:
    from backend_service.core.db_manager import DatabaseManager
    from backend_service.core.mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)

LOG_INTERVAL_SECONDS = 5 * 60  # 5 minutes
HOST_HELPER_TIMEOUT = 10.0
RETENTION_DAYS = 30

# Der Warnungsspeicher liegt in system_alerts - dort koennen mehrere Meldungen
# nebeneinander stehen, ohne sich zu verdraengen. Hier nur noch re-exportiert,
# damit bestehende Aufrufer unveraendert bleiben.
from backend_service.core.system_alerts import (  # noqa: E402
    clear_alert,
    get_current_alert,
    set_alert,
)

ALERT_TEMPERATURE_HIGH = "temperature_high"


def _read_temperature_warning_celsius() -> float:
    """Read temperature_warning_celsius from general_settings.json (default 80)."""
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    if not gs_path.exists():
        return 80.0
    try:
        data = json.loads(gs_path.read_text(encoding="utf-8"))
        return max(0, min(100, float(data.get("temperature_warning_celsius", 80))))
    except (OSError, ValueError, TypeError):
        return 80.0


def _host_helper_url() -> str:
    return os.environ.get("HOST_HELPER_URL", "http://host-helper:8000").rstrip("/")


def _host_helper_api_key() -> str | None:
    return os.environ.get("HOST_HELPER_API_KEY", "").strip() or None


async def _fetch_host_status() -> dict[str, Any] | None:
    """Fetch host-status from Host-Helper. Returns None on failure."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/host-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("temperature_fetch_host_status_failed", error=str(e))
    return None


def _log_temperature(session: Session, temperature_celsius: float) -> None:
    """Insert one temperature reading and optionally run retention delete."""
    now = datetime.now(UTC)
    session.add(
        TemperatureReading(
            recorded_at=now,
            temperature_celsius=round(temperature_celsius, 1),
        )
    )
    session.commit()

    # Retention: delete older than RETENTION_DAYS
    cutoff = now - timedelta(days=RETENTION_DAYS)
    try:
        session.execute(
            text("DELETE FROM temperature_readings WHERE recorded_at < :cutoff"),
            {"cutoff": cutoff},
        )
        session.commit()
    except Exception as e:
        logger.warning("temperature_retention_delete_failed", error=str(e))
        session.rollback()


async def _publish_overheating_start(
    mqtt_client: MQTTClient | None,
    get_mqtt_topic: Any,
    ws_broadcast: Any,
    temp: float,
    threshold: float,
) -> None:
    """Announce that the box entered the overheating state (MQTT + WebSocket)."""
    if mqtt_client and mqtt_client.is_connected:
        try:
            topic = get_mqtt_topic("system", "service-error")
            await mqtt_client.publish(
                topic,
                {"message": "High system temperature", "code": "temperature_high"},
            )
            logger.warning("temperature_overheating_published", temp=temp, threshold=threshold)
        except Exception as e:
            logger.warning("temperature_mqtt_publish_failed", error=str(e))

    set_alert(ALERT_TEMPERATURE_HIGH, "warning", "alerts.temperature_high")
    if ws_broadcast:
        try:
            await ws_broadcast({
                "type": "system_alert",
                "data": {
                    "level": "warning",
                    "code": "temperature_high",
                    "message": "alerts.temperature_high",
                },
            })
        except Exception as e:
            logger.debug("temperature_ws_broadcast_failed", error=str(e))


async def _publish_overheating_end(
    mqtt_client: MQTTClient | None,
    get_mqtt_topic: Any,
    ws_broadcast: Any,
    temp: float,
) -> None:
    """Announce that the box left the overheating state (MQTT + WebSocket)."""
    if mqtt_client and mqtt_client.is_connected:
        try:
            topic = get_mqtt_topic("system", "service-started")
            await mqtt_client.publish(topic, {"reason": "temperature_normal"})
            logger.info("temperature_normal_published", temp=temp)
        except Exception as e:
            logger.warning("temperature_mqtt_publish_failed", error=str(e))

    clear_alert(ALERT_TEMPERATURE_HIGH)
    if ws_broadcast:
        try:
            await ws_broadcast({
                "type": "system_alert_cleared",
                "data": {"code": "temperature_high"},
            })
        except Exception as e:
            logger.debug("temperature_ws_broadcast_failed", error=str(e))


async def _sample_temperature_once(
    db_manager: DatabaseManager,
    mqtt_client: MQTTClient | None,
    get_mqtt_topic: Any,
    ws_broadcast: Any,
    overheating_active: bool,
) -> bool:
    """Take one temperature sample, persist it and handle alert transitions.

    Returns the new overheating state. Raises nothing that the caller must
    handle beyond CancelledError - the loop treats any other error as a
    skipped sample.
    """
    data = await _fetch_host_status()
    if not data:
        return overheating_active

    temp = data.get("temperature_celsius")
    if temp is None:
        return overheating_active

    session = db_manager.get_session()
    try:
        _log_temperature(session, float(temp))
    finally:
        session.close()

    threshold = _read_temperature_warning_celsius()
    is_overheating = float(temp) >= threshold

    if is_overheating and not overheating_active:
        await _publish_overheating_start(
            mqtt_client, get_mqtt_topic, ws_broadcast, float(temp), threshold
        )
        return True

    if not is_overheating and overheating_active:
        await _publish_overheating_end(mqtt_client, get_mqtt_topic, ws_broadcast, float(temp))
        return False

    return overheating_active


async def run_temperature_log_loop(
    db_manager: DatabaseManager | None,
    mqtt_client: MQTTClient | None,
    device_id: str,
    get_mqtt_topic: Any,
    ws_broadcast: Any,
) -> None:
    """Background task: fetch host-status, log temperature, check overheating, publish MQTT/WS.

    The interval sleep runs after every iteration, including the ones where no
    sample could be taken. A missing Host-Helper (unreachable, no API key, or
    restarting) must never turn this into a busy loop.
    """
    if not db_manager:
        return

    overheating_active = False
    await asyncio.sleep(30)  # initial delay before first sample

    while True:
        try:
            overheating_active = await _sample_temperature_once(
                db_manager, mqtt_client, get_mqtt_topic, ws_broadcast, overheating_active
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            # A single failed sample must not kill the background task.
            logger.warning("temperature_sample_failed", error=str(e))

        try:
            await asyncio.sleep(LOG_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break

    logger.info("temperature_log_loop_stopped")
