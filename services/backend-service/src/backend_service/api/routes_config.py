"""REST API endpoints for reading/writing other services' config (Admin UI)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, HTTPException

from backend_service.config import get_config

logger = structlog.get_logger(__name__)
router = APIRouter()

_mqtt_client = None


def set_mqtt_client(client) -> None:  # noqa: ANN001
    """Inject MQTT client (called from main.py at startup)."""
    global _mqtt_client
    _mqtt_client = client

# ---------------------------------------------------------------------------
# Enumeration endpoints – static lists kept in sync with service implementations
# ---------------------------------------------------------------------------

# All logical states the LED service can derive from MQTT events.
# Source of truth: led_service/state_manager.py _build_derivation_rules()
_LED_BINDING_STATES: list[str] = [
    "system_online",
    "system_error",
    "system_booting",
    "audio_playing",
    "audio_paused",
    "audio_stopped",
    "rfid_scanned",
    "rfid_removed",
    "rfid_unknown_tag",
    "button_pressed",
    "backend_unreachable",
]

# All LED pattern types.
# Source of truth: led_service/config_schema.py PatternType
_LED_PATTERN_TYPES: list[str] = ["solid", "blink", "pulse", "off"]

# All actions the button service can trigger.
# Source of truth: button_service/event_processor.py
_BUTTON_ACTIONS: list[str] = [
    "play_pause",
    "volume_up",
    "volume_down",
    "mute_toggle",
    "next",
    "prev",
    "stop",
]


@router.get("/leds/states")
async def get_led_states() -> list[str]:
    """Return all known LED binding state identifiers."""
    return _LED_BINDING_STATES


@router.get("/leds/patterns")
async def get_led_patterns() -> list[str]:
    """Return all supported LED pattern types."""
    return _LED_PATTERN_TYPES


@router.get("/buttons/actions")
async def get_button_actions() -> list[str]:
    """Return all supported button action identifiers."""
    return _BUTTON_ACTIONS


# Base path for service configs (mount points in Docker, e.g. /app/config_services)
CONFIG_SERVICES_BASE = Path(
    os.environ.get("CONFIG_SERVICES_PATH", "/app/config_services")
)

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
GENERAL_SETTINGS_PATH = DATA_PATH / "general_settings.json"


def _general_settings_read() -> dict:
    """Return current general settings (runtime config + env)."""
    config = get_config()
    return {
        "minabox_device_id": config.device_id,
        "log_level": config.env.log_level,
        "mqtt_broker": config.env.mqtt_broker,
        "mqtt_port": config.env.mqtt_port,
        "disable_gpio": os.environ.get("DISABLE_GPIO", "false").lower() in ("true", "1"),
    }


@router.get("/general")
async def get_general_config() -> dict:
    """Return general/minabox settings (device_id, log_level, MQTT, etc.) for Admin UI."""
    return _general_settings_read()


@router.put("/general")
async def update_general_config(body: dict) -> dict:
    """Update general settings. Persisted to /data/general_settings.json; takes effect after restart."""
    allowed = {"minabox_device_id", "log_level", "mqtt_broker", "mqtt_port", "disable_gpio"}
    data = {k: v for k, v in body.items() if k in allowed}
    if "log_level" in data:
        data["log_level"] = str(data["log_level"]).upper()
    if "disable_gpio" in data:
        data["disable_gpio"] = bool(data["disable_gpio"])
    try:
        GENERAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Persist for next startup (and for GET to reflect after restart)
        to_write = {k: data[k] for k in data}
        GENERAL_SETTINGS_PATH.write_text(
            json.dumps(to_write, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        logger.error("general_config_write_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write general settings") from e
    # Return current display values (saved values overlay)
    out = _general_settings_read()
    out.update(data)
    return out

# Mapping: API segment -> (subdir, filename)
CONFIG_FILES = {
    "audio": ("audio", "audio.json"),
    "leds": ("led", "leds.json"),
    "buttons": ("button", "buttons.json"),
    "rfid": ("rfid", "rfid.json"),
}


def _config_path(service: str) -> Path | None:
    if service not in CONFIG_FILES:
        return None
    subdir, filename = CONFIG_FILES[service]
    return CONFIG_SERVICES_BASE / subdir / filename


@router.get("/audio")
async def get_audio_config() -> dict:
    """Return audio service config (for Admin UI)."""
    path = _config_path("audio")
    if not path or not path.exists():
        logger.warning("config_not_available", service="audio", path=str(path) if path else "none")
        raise HTTPException(
            status_code=503,
            detail="Audio config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="audio", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read audio config") from e


@router.put("/audio")
async def update_audio_config(body: dict) -> dict:
    """Update audio service config."""
    path = _config_path("audio")
    if not path or not path.exists():
        raise HTTPException(status_code=503, detail="Audio config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        return body
    except OSError as e:
        logger.error("config_write_failed", service="audio", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write audio config") from e


@router.get("/leds")
async def get_leds_config() -> dict:
    """Return LED service config (for Admin UI)."""
    path = _config_path("leds")
    if not path or not path.exists():
        logger.warning("config_not_available", service="leds", path=str(path) if path else "none")
        raise HTTPException(
            status_code=503,
            detail="LED config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="leds", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read LED config") from e


@router.put("/leds")
async def update_leds_config(body: dict) -> dict:
    """Update LED service config."""
    path = _config_path("leds")
    if not path or not path.exists():
        raise HTTPException(status_code=503, detail="LED config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("led", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("led_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="leds", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write LED config") from e


@router.post("/leds/test")
async def test_led(body: dict) -> dict:
    """Trigger a brief LED flash for testing via the LED service REST API."""
    led_id = body.get("led_id")
    if not led_id:
        raise HTTPException(status_code=422, detail="led_id is required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post("http://led:8000/test", json={"led_id": led_id})
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=response.json().get("detail", "LED not found"))
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        logger.warning("led_service_unreachable", led_id=led_id)
        raise HTTPException(status_code=503, detail="LED service not reachable") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("led_test_failed", led_id=led_id, error=str(e))
        raise HTTPException(status_code=500, detail="LED test failed") from e


@router.get("/buttons")
async def get_buttons_config() -> dict:
    """Return button service config (for Admin UI)."""
    path = _config_path("buttons")
    if not path or not path.exists():
        logger.warning("config_not_available", service="buttons", path=str(path) if path else "none")
        raise HTTPException(
            status_code=503,
            detail="Button config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="buttons", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read button config") from e


@router.put("/buttons")
async def update_buttons_config(body: dict) -> dict:
    """Update button service config."""
    path = _config_path("buttons")
    if not path or not path.exists():
        raise HTTPException(status_code=503, detail="Button config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        return body
    except OSError as e:
        logger.error("config_write_failed", service="buttons", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write button config") from e


def _rfid_flatten(data: dict) -> dict:
    """Convert nested rfid.json { reader: { ... } } to flat API shape for Admin UI."""
    reader = data.get("reader") or {}
    rt = (reader.get("reader_type") or "pn532").lower()
    if rt == "pn532":
        reader_type = "PN532"
    elif rt == "mock":
        reader_type = "Mock"
    else:
        reader_type = rt
    iface = (reader.get("interface") or "i2c").lower()
    interface = iface.upper() if len(iface) <= 4 else iface  # i2c -> I2C, spi -> SPI, uart -> UART
    return {
        "reader_type": reader_type,
        "interface": interface,
        "scan_interval_ms": int(reader.get("scan_interval_ms", 200)),
        "duplicate_suppression_ms": int(reader.get("duplicate_suppression_ms", 2000)),
    }


def _rfid_nest(flat: dict) -> dict:
    """Convert flat API shape to nested rfid.json format (lowercase for service)."""
    rt = (flat.get("reader_type") or "PN532").lower()
    iface = (flat.get("interface") or "I2C").lower()
    return {
        "reader": {
            "reader_type": rt,
            "interface": iface,
            "scan_interval_ms": int(flat.get("scan_interval_ms", 200)),
            "duplicate_suppression_ms": int(flat.get("duplicate_suppression_ms", 2000)),
        }
    }


@router.get("/rfid")
async def get_rfid_config() -> dict:
    """Return RFID service config (for Admin UI), flattened from reader object."""
    path = _config_path("rfid")
    if not path or not path.exists():
        logger.warning("config_not_available", service="rfid", path=str(path) if path else "none")
        raise HTTPException(
            status_code=503,
            detail="RFID config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _rfid_flatten(data)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="rfid", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read RFID config") from e


@router.put("/rfid")
async def update_rfid_config(body: dict) -> dict:
    """Update RFID service config (accepts flat body, writes nested reader)."""
    path = _config_path("rfid")
    if not path or not path.exists():
        raise HTTPException(status_code=503, detail="RFID config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        nested = _rfid_nest(body)
        path.write_text(json.dumps(nested, indent=2, ensure_ascii=False), encoding="utf-8")
        return _rfid_flatten(nested)
    except OSError as e:
        logger.error("config_write_failed", service="rfid", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write RFID config") from e
