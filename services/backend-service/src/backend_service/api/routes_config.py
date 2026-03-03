"""REST API endpoints for reading/writing other services' config (Admin UI)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile
from shared_lib.logging import setup_structlog
from shared_lib.mqtt import get_mqtt_topic

from backend_service.config import get_config

# Static files directory (shared with static mount in main.py)
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))

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
    "usage_denied",
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
    "sleep_timer_toggle",
    "repeat_cycle",
    "shuffle_toggle",
    "next_output_device",
]

# All display element types (OLED display service).
# Source of truth: display-service config_schema.py
_DISPLAY_ELEMENT_TYPES: list[str] = [
    "volume",
    "sleep_timer",
    "mute",
    "play_state",
    "clock",
    "error_state",
    "repeat",
    "shuffle",
    "bluetooth",
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
    # Read from persisted overrides
    sleep_timer_minutes = 30
    bedtime_fade_enabled = False
    bedtime_fade_duration_minutes = 15
    bedtime_fade_interval_seconds = 30
    bedtime_fade_step_percent = 2.0
    allowed_usage_times: list[dict] = []
    usage_times_enabled = False
    daily_limit_enabled = False
    daily_limit_minutes = 120
    stop_playback_on_tag_remove = False
    if GENERAL_SETTINGS_PATH.exists():
        try:
            data = json.loads(GENERAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            sleep_timer_minutes = max(1, int(data.get("sleep_timer_minutes", 30)))
            bedtime_fade_enabled = bool(data.get("bedtime_fade_enabled", False))
            bedtime_fade_duration_minutes = max(1, int(data.get("bedtime_fade_duration_minutes", 15)))
            bedtime_fade_interval_seconds = max(5, int(data.get("bedtime_fade_interval_seconds", 30)))
            bedtime_fade_step_percent = max(0.5, min(50.0, float(data.get("bedtime_fade_step_percent", 2.0))))
            usage_times_enabled = bool(data.get("usage_times_enabled", False))
            daily_limit_enabled = bool(data.get("daily_limit_enabled", False))
            daily_limit_minutes = max(1, min(1440, int(data.get("daily_limit_minutes", 120))))
            stop_playback_on_tag_remove = bool(data.get("stop_playback_on_tag_remove", False))
            raw_times = data.get("allowed_usage_times")
            if isinstance(raw_times, list):
                allowed_usage_times = [
                    {"weekday": int(x.get("weekday", 0)), "start": str(x.get("start", "07:00")), "end": str(x.get("end", "19:00"))}
                    for x in raw_times
                    if isinstance(x, dict) and 0 <= x.get("weekday", 0) <= 6
                ]
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            pass
    return {
        "minabox_device_id": config.device_id,
        "log_level": config.env.log_level,
        "mqtt_broker": config.env.mqtt_broker,
        "mqtt_port": config.env.mqtt_port,
        "disable_gpio": os.environ.get("DISABLE_GPIO", "false").lower() in ("true", "1"),
        "sleep_timer_minutes": sleep_timer_minutes,
        "bedtime_fade_enabled": bedtime_fade_enabled,
        "bedtime_fade_duration_minutes": bedtime_fade_duration_minutes,
        "bedtime_fade_interval_seconds": bedtime_fade_interval_seconds,
        "bedtime_fade_step_percent": bedtime_fade_step_percent,
        "usage_times_enabled": usage_times_enabled,
        "daily_limit_enabled": daily_limit_enabled,
        "daily_limit_minutes": daily_limit_minutes,
        "stop_playback_on_tag_remove": stop_playback_on_tag_remove,
        "allowed_usage_times": allowed_usage_times,
    }


@router.get("/general")
async def get_general_config() -> dict:
    """Return general/minabox settings (device_id, log_level, MQTT, etc.) for Admin UI."""
    return _general_settings_read()


def _validate_allowed_usage_times(times: list) -> list[dict]:
    """Validate and normalize allowed_usage_times. weekday 0-6, start/end HH:MM."""
    result = []
    for x in times:
        if not isinstance(x, dict):
            continue
        wd = x.get("weekday", 0)
        try:
            wd = max(0, min(6, int(wd)))
        except (TypeError, ValueError):
            wd = 0
        start = str(x.get("start", "07:00"))[:5]
        end = str(x.get("end", "19:00"))[:5]
        result.append({"weekday": wd, "start": start, "end": end})
    return result


@router.put("/general")
async def update_general_config(body: dict) -> dict:
    """Update general settings. Persisted to /data/general_settings.json; takes effect after restart."""
    allowed = {
        "minabox_device_id", "log_level", "mqtt_broker", "mqtt_port", "disable_gpio", "sleep_timer_minutes",
        "bedtime_fade_enabled", "bedtime_fade_duration_minutes", "bedtime_fade_interval_seconds", "bedtime_fade_step_percent",
        "usage_times_enabled", "daily_limit_enabled", "daily_limit_minutes",
        "stop_playback_on_tag_remove",
        "allowed_usage_times",
    }
    data = {k: v for k, v in body.items() if k in allowed}
    if "log_level" in data:
        data["log_level"] = str(data["log_level"]).upper()
    if "disable_gpio" in data:
        data["disable_gpio"] = bool(data["disable_gpio"])
    if "sleep_timer_minutes" in data:
        data["sleep_timer_minutes"] = max(1, int(data["sleep_timer_minutes"]))
    if "bedtime_fade_enabled" in data:
        data["bedtime_fade_enabled"] = bool(data["bedtime_fade_enabled"])
    if "bedtime_fade_duration_minutes" in data:
        data["bedtime_fade_duration_minutes"] = max(1, int(data["bedtime_fade_duration_minutes"]))
    if "bedtime_fade_interval_seconds" in data:
        data["bedtime_fade_interval_seconds"] = max(5, int(data["bedtime_fade_interval_seconds"]))
    if "bedtime_fade_step_percent" in data:
        data["bedtime_fade_step_percent"] = max(0.5, min(50.0, float(data["bedtime_fade_step_percent"])))
    if "usage_times_enabled" in data:
        data["usage_times_enabled"] = bool(data["usage_times_enabled"])
    if "daily_limit_enabled" in data:
        data["daily_limit_enabled"] = bool(data["daily_limit_enabled"])
    if "daily_limit_minutes" in data:
        data["daily_limit_minutes"] = max(1, min(1440, int(data["daily_limit_minutes"])))
    if "stop_playback_on_tag_remove" in data:
        data["stop_playback_on_tag_remove"] = bool(data.get("stop_playback_on_tag_remove", False))
    if "allowed_usage_times" in data:
        raw = data["allowed_usage_times"]
        data["allowed_usage_times"] = _validate_allowed_usage_times(raw if isinstance(raw, list) else [])
    try:
        GENERAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Merge with existing file so partial updates (e.g. from Child or Control tab) do not drop other keys
        to_write = {}
        if GENERAL_SETTINGS_PATH.exists():
            try:
                to_write = json.loads(GENERAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        to_write.update(data)
        GENERAL_SETTINGS_PATH.write_text(
            json.dumps(to_write, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        logger.error("general_config_write_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write general settings") from e
    # Return current display values (saved values overlay)
    out = _general_settings_read()
    out.update(data)

    # Live-update log level in this process and broadcast to other services
    if "log_level" in data:
        setup_structlog(
            data["log_level"],
            silence_loggers=["alembic.runtime.migration", "sqlalchemy.engine"],
        )
    if _mqtt_client is not None:
        config = get_config()
        topic = get_mqtt_topic(config.env.minabox_device_id, "config", "general")
        payload = {"log_level": data.get("log_level", out.get("log_level", "INFO"))}
        await _mqtt_client.publish(topic, payload, qos=1, retain=True)
        logger.debug("config_general_published", topic=topic)

    return out

# Mapping: API segment -> (subdir, filename)
CONFIG_FILES = {
    "audio": ("audio", "audio.json"),
    "leds": ("led", "leds.json"),
    "buttons": ("button", "buttons.json"),
    "rfid": ("rfid", "rfid.json"),
    "display": ("display", "display.json"),
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
    """Update audio service config. Merges body with existing config so partial updates (e.g. only max_volume from parent dashboard) do not wipe other keys like enabled_output_devices or device_display_names."""
    path = _config_path("audio")
    if not path or not path.exists():
        raise HTTPException(status_code=503, detail="Audio config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current: dict = {}
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(current, dict):
                    current = {}
            except (json.JSONDecodeError, OSError):
                pass
        merged = {**current, **body}
        path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("audio", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("audio_config_reload_published", topic=topic)
        return merged
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
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("button", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("button_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="buttons", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write button config") from e


@router.get("/display/element-types")
async def get_display_element_types() -> list[str]:
    """Return all supported display element type identifiers."""
    return _DISPLAY_ELEMENT_TYPES


@router.get("/display")
async def get_display_config() -> dict:
    """Return display service config (for Admin UI)."""
    path = _config_path("display")
    if not path or not path.exists():
        logger.warning("config_not_available", service="display", path=str(path) if path else "none")
        raise HTTPException(
            status_code=503,
            detail="Display config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="display", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read display config") from e


@router.put("/display")
async def update_display_config(body: dict) -> dict:
    """Update display service config."""
    path = _config_path("display")
    if path is None:
        raise HTTPException(status_code=503, detail="Display config not available")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("display", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("display_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="display", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write display config") from e


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


# ---------------------------------------------------------------------------
# Logo endpoints
# ---------------------------------------------------------------------------

@router.post("/logo")
async def upload_logo(file: UploadFile = File(...)) -> dict:
    """Upload a custom logo image (stored as /data/static/logo.png)."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    logo_path = STATIC_DIR / "logo.png"
    try:
        content = await file.read()
        logo_path.write_bytes(content)
        logger.info("logo_uploaded", size=len(content))
        return {"url": "/static/logo.png"}
    except OSError as e:
        logger.error("logo_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to save logo") from e


@router.delete("/logo")
async def delete_logo() -> dict:
    """Remove the custom logo."""
    logo_path = STATIC_DIR / "logo.png"
    if logo_path.exists():
        logo_path.unlink()
        logger.info("logo_deleted")
    return {"deleted": True}
