"""REST API endpoints for reading/writing other services' config (Admin UI)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile
from shared_lib.logging import setup_structlog
from shared_lib.mqtt import get_mqtt_topic

from backend_service.api.websocket import ws_manager
from backend_service.config import get_config
from backend_service.core.api_errors import ApiError
from backend_service.core.debug_export.runtime_buffers import structlog_ring_processor
from backend_service.core.json_store import write_json_atomic
from backend_service.core.playback_settings import (
    DEFAULT_END_BEHAVIOR,
    DEFAULT_LOOP_GUARD_MINUTES,
    DEFAULT_PLAYLIST_SHUFFLE,
    clamp_end_behavior,
    clamp_loop_guard_minutes,
)
from backend_service.core.uploads import (
    clamp_upload_size_mb,
    max_upload_size_mb,
    read_image_upload,
)

# Static files directory (shared with static mount in main.py)
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))

logger = structlog.get_logger(__name__)
router = APIRouter()

_mqtt_client = None


def set_mqtt_client(client: Any) -> None:
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
    "rfid_tag_blocked",
    "button_pressed",
    "backend_unreachable",
    "usage_denied",
]

# All LED pattern types.
# Source of truth: led_service/config_schema.py PatternType
# NOTE: 'glow' uses PWMLED (Software PWM) for a smooth breathing effect.
_LED_PATTERN_TYPES: list[str] = ["solid", "blink", "pulse", "off", "glow"]

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
    resume_on_tag_rescan = True
    playback_end_behavior = DEFAULT_END_BEHAVIOR
    playback_loop_guard_minutes = DEFAULT_LOOP_GUARD_MINUTES
    playlist_shuffle = DEFAULT_PLAYLIST_SHUFFLE
    auto_update_check_enabled = False
    # Read through the same helper the upload path uses, so the value shown in
    # the WebUI is exactly the one that will be enforced.
    upload_size_mb = max_upload_size_mb()
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
            resume_on_tag_rescan = bool(data.get("resume_on_tag_rescan", True))
            playback_end_behavior = clamp_end_behavior(data.get("playback_end_behavior"))
            if "playback_loop_guard_minutes" in data:
                playback_loop_guard_minutes = clamp_loop_guard_minutes(
                    data["playback_loop_guard_minutes"]
                )
            auto_update_check_enabled = bool(data.get("auto_update_check_enabled", False))
            playlist_shuffle = bool(data.get("playlist_shuffle", DEFAULT_PLAYLIST_SHUFFLE))
            if "max_upload_size_mb" in data:
                upload_size_mb = clamp_upload_size_mb(data["max_upload_size_mb"])
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
        "resume_on_tag_rescan": resume_on_tag_rescan,
        "playback_end_behavior": playback_end_behavior,
        "playback_loop_guard_minutes": playback_loop_guard_minutes,
        "playlist_shuffle": playlist_shuffle,
        "allowed_usage_times": allowed_usage_times,
        "auto_update_check_enabled": auto_update_check_enabled,
        "max_upload_size_mb": upload_size_mb,
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
        "resume_on_tag_rescan",
        "playback_end_behavior",
        "playback_loop_guard_minutes",
        "playlist_shuffle",
        "allowed_usage_times",
        "auto_update_check_enabled",
        "max_upload_size_mb",
        # Setup wizard (docs/services/webui/Setup-Wizard.md). Without these
        # keys the filter below drops them silently, and the wizard would come
        # back on every visit.
        "setup_completed",
        "setup_version",
    }
    data = {k: v for k, v in body.items() if k in allowed}
    if "log_level" in data:
        data["log_level"] = str(data["log_level"]).upper()
    if "disable_gpio" in data:
        data["disable_gpio"] = bool(data["disable_gpio"])
    if "setup_completed" in data:
        data["setup_completed"] = bool(data["setup_completed"])
    if "setup_version" in data:
        data["setup_version"] = max(0, int(data["setup_version"]))
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
    if "resume_on_tag_rescan" in data:
        data["resume_on_tag_rescan"] = bool(data.get("resume_on_tag_rescan", True))
    if "playback_end_behavior" in data:
        data["playback_end_behavior"] = clamp_end_behavior(data["playback_end_behavior"])
    if "playback_loop_guard_minutes" in data:
        data["playback_loop_guard_minutes"] = clamp_loop_guard_minutes(
            data["playback_loop_guard_minutes"]
        )
    if "allowed_usage_times" in data:
        raw = data["allowed_usage_times"]
        data["allowed_usage_times"] = _validate_allowed_usage_times(raw if isinstance(raw, list) else [])
    if "playlist_shuffle" in data:
        data["playlist_shuffle"] = bool(data["playlist_shuffle"])
    if "auto_update_check_enabled" in data:
        data["auto_update_check_enabled"] = bool(data["auto_update_check_enabled"])
    if "max_upload_size_mb" in data:
        data["max_upload_size_mb"] = clamp_upload_size_mb(data["max_upload_size_mb"])
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
        write_json_atomic(GENERAL_SETTINGS_PATH, to_write)
    except OSError as e:
        logger.error("general_config_write_failed", error=str(e))
        raise ApiError(status_code=500, code="general_settings_write_failed", detail="Failed to write general settings") from e
    # Return current display values (saved values overlay)
    out = _general_settings_read()
    out.update(data)

    # Live-update log level in this process and broadcast to other services
    if "log_level" in data:
        # Without extra_processors, switching the log level would silently
        # detach the debug export's ring buffer.
        setup_structlog(
            data["log_level"],
            silence_loggers=["alembic.runtime.migration", "sqlalchemy.engine"],
            extra_processors=[structlog_ring_processor],
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


# What each service config must structurally look like: the top-level key it
# cannot do without, and its type.
#
# Deliberately not the Pydantic models in models/schemas_config.py - those
# describe something else entirely (a `brightness` field for LEDs, for
# instance, where the real file holds a list of LEDs with GPIO pins and
# bindings). Validating against them would reject every legitimate save.
#
# A structural check is enough for what goes wrong in practice: a body that
# lost its content on the way and would leave the other service with a config
# it cannot start from.
_CONFIG_SHAPE: dict[str, tuple[str, type]] = {
    "leds": ("leds", list),
    "buttons": ("buttons", list),
    "display": ("elements", list),
}


def _validate_config_shape(service: str, body: dict) -> None:
    """Reject a config body that would leave the service unable to start."""
    expected = _CONFIG_SHAPE.get(service)
    if expected is None:
        return
    key, kind = expected
    value = body.get(key)
    if not isinstance(value, kind):
        logger.warning(
            "config_rejected_bad_shape",
            service=service,
            expected_key=key,
            expected_type=kind.__name__,
            got=type(value).__name__,
        )
        raise ApiError(
            status_code=422,
            code="config_invalid",
            detail=f"{service} config must contain '{key}' as a {kind.__name__}",
        )


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
        raise ApiError(
            status_code=503,
            code="audio_config_unavailable",
            detail="Audio config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="audio", error=str(e))
        raise ApiError(status_code=500, code="audio_config_read_failed", detail="Failed to read audio config") from e


@router.put("/audio")
async def update_audio_config(body: dict) -> dict:
    """Update audio service config. Merges body with existing config so partial updates (e.g. only max_volume from parent dashboard) do not wipe other keys like enabled_output_devices or device_display_names."""
    path = _config_path("audio")
    if not path or not path.exists():
        raise ApiError(status_code=503, code="audio_config_unavailable", detail="Audio config not available")
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
        write_json_atomic(path, merged)
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("audio", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("audio_config_reload_published", topic=topic)
        # Without this push an open player page never learns about new volume
        # limits and keeps the old slider range until it is reloaded.
        await ws_manager.broadcast({"type": "audio_config", "data": merged})
        return merged
    except OSError as e:
        logger.error("config_write_failed", service="audio", error=str(e))
        raise ApiError(status_code=500, code="audio_config_write_failed", detail="Failed to write audio config") from e


@router.get("/leds")
async def get_leds_config() -> dict:
    """Return LED service config (for Admin UI)."""
    path = _config_path("leds")
    if not path or not path.exists():
        logger.warning("config_not_available", service="leds", path=str(path) if path else "none")
        raise ApiError(
            status_code=503,
            code="led_config_unavailable",
            detail="LED config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="leds", error=str(e))
        raise ApiError(status_code=500, code="led_config_read_failed", detail="Failed to read LED config") from e


@router.put("/leds")
async def update_leds_config(body: dict) -> dict:
    """Update LED service config."""
    path = _config_path("leds")
    if not path or not path.exists():
        raise ApiError(status_code=503, code="led_config_unavailable", detail="LED config not available")
    _validate_config_shape("leds", body)
    try:
        write_json_atomic(path, body)
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("led", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("led_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="leds", error=str(e))
        raise ApiError(status_code=500, code="led_config_write_failed", detail="Failed to write LED config") from e


@router.post("/leds/test")
async def test_led(body: dict) -> dict:
    """Trigger a brief LED flash for testing via the LED service REST API."""
    led_id = body.get("led_id")
    if not led_id:
        raise ApiError(status_code=422, code="led_id_required", detail="led_id is required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post("http://led:8000/test", json={"led_id": led_id})
        if response.status_code == 404:
            raise ApiError(status_code=404, code="led_not_found", detail=response.json().get("detail", "LED not found"))
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        logger.warning("led_service_unreachable", led_id=led_id)
        raise ApiError(status_code=503, code="led_service_unreachable", detail="LED service not reachable") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("led_test_failed", led_id=led_id, error=str(e))
        raise ApiError(status_code=500, code="led_test_failed", detail="LED test failed") from e


@router.get("/buttons")
async def get_buttons_config() -> dict:
    """Return button service config (for Admin UI)."""
    path = _config_path("buttons")
    if not path or not path.exists():
        logger.warning("config_not_available", service="buttons", path=str(path) if path else "none")
        raise ApiError(
            status_code=503,
            code="button_config_unavailable",
            detail="Button config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="buttons", error=str(e))
        raise ApiError(status_code=500, code="button_config_read_failed", detail="Failed to read button config") from e


@router.put("/buttons")
async def update_buttons_config(body: dict) -> dict:
    """Update button service config."""
    path = _config_path("buttons")
    if not path or not path.exists():
        raise ApiError(status_code=503, code="button_config_unavailable", detail="Button config not available")
    _validate_config_shape("buttons", body)
    try:
        write_json_atomic(path, body)
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("button", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("button_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="buttons", error=str(e))
        raise ApiError(status_code=500, code="button_config_write_failed", detail="Failed to write button config") from e


@router.post("/display/test")
async def test_display() -> dict:
    """Show a brief test pattern on the OLED via the display service REST API."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post("http://display:8000/test")
        if response.status_code == 404:
            raise ApiError(
                status_code=404,
                code="display_not_available",
                detail=response.json().get("detail", "Display not available"),
            )
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        logger.warning("display_service_unreachable")
        raise ApiError(
            status_code=503, code="display_service_unreachable", detail="Display service not reachable"
        ) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("display_test_failed", error=str(e))
        raise ApiError(status_code=500, code="display_test_failed", detail="Display test failed") from e


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
        raise ApiError(
            status_code=503,
            code="display_config_unavailable",
            detail="Display config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="display", error=str(e))
        raise ApiError(status_code=500, code="display_config_read_failed", detail="Failed to read display config") from e


@router.put("/display")
async def update_display_config(body: dict) -> dict:
    """Update display service config."""
    path = _config_path("display")
    if path is None:
        raise ApiError(status_code=503, code="display_config_unavailable", detail="Display config not available")
    _validate_config_shape("display", body)
    try:
        write_json_atomic(path, body)
        if _mqtt_client is not None:
            config = get_config()
            topic = config.get_mqtt_topic("display", "config/reload")
            await _mqtt_client.publish(topic, {})
            logger.info("display_config_reload_published", topic=topic)
        return body
    except OSError as e:
        logger.error("config_write_failed", service="display", error=str(e))
        raise ApiError(status_code=500, code="display_config_write_failed", detail="Failed to write display config") from e


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
        raise ApiError(
            status_code=503,
            code="rfid_config_unavailable",
            detail="RFID config not available (CONFIG_SERVICES_PATH not mounted?)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _rfid_flatten(data)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("config_read_failed", service="rfid", error=str(e))
        raise ApiError(status_code=500, code="rfid_config_read_failed", detail="Failed to read RFID config") from e


@router.put("/rfid")
async def update_rfid_config(body: dict) -> dict:
    """Update RFID service config (accepts flat body, writes nested reader)."""
    path = _config_path("rfid")
    if not path or not path.exists():
        raise ApiError(status_code=503, code="rfid_config_unavailable", detail="RFID config not available")
    try:
        # Merge, do not replace: _rfid_nest only builds the `reader` block, and
        # writing that alone used to drop the `modes` and `service` sections the
        # RFID service also reads from this file.
        current: dict = {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (json.JSONDecodeError, OSError):
            pass
        nested = {**current, **_rfid_nest(body)}
        write_json_atomic(path, nested)
        return _rfid_flatten(nested)
    except OSError as e:
        logger.error("config_write_failed", service="rfid", error=str(e))
        raise ApiError(status_code=500, code="rfid_config_write_failed", detail="Failed to write RFID config") from e


# ---------------------------------------------------------------------------
# Logo endpoints
# ---------------------------------------------------------------------------

@router.post("/logo")
async def upload_logo(file: UploadFile = File(...)) -> dict:
    """Upload a custom logo image (stored as /data/static/logo.png)."""
    content = await read_image_upload(file)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    logo_path = STATIC_DIR / "logo.png"
    try:
        logo_path.write_bytes(content)
        logger.info("logo_uploaded", size=len(content))
        return {"url": "/static/logo.png"}
    except OSError as e:
        logger.error("logo_upload_failed", error=str(e))
        raise ApiError(status_code=500, code="logo_save_failed", detail="Failed to save logo") from e


@router.delete("/logo")
async def delete_logo() -> dict:
    """Remove the custom logo."""
    logo_path = STATIC_DIR / "logo.png"
    if logo_path.exists():
        logo_path.unlink()
        logger.info("logo_deleted")
    return {"deleted": True}
