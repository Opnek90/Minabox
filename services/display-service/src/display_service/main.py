"""Main entry point for the display service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import datetime
from typing import Any, Callable

import httpx
import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, DisplayServiceConfig
from .core import StateManager
from .infrastructure import MQTTClient, clear, init as display_init, is_available, show_areas

logger = structlog.get_logger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")
SLEEP_TIMER_POLL_INTERVAL = 5.0
SESSION_POLL_INTERVAL = 5.0
RENDER_INTERVAL = 1.0
# The render loop ticks every second, but the OLED shares /dev/i2c-1 with the
# PN532 RFID reader. Redrawing identical content just adds bus contention on the
# box's primary input path, and the clock element only resolves to HH:MM - so 59
# of 60 frames per minute used to be redundant. Frames are therefore only pushed
# when the rendered content actually changed, with a periodic forced redraw so a
# glitched display still heals itself.
FORCE_REDRAW_INTERVAL = 60.0

_HEADER_MAX_ITEMS = 6
_BODY_MAX_ITEMS = 3

_CONDITIONAL_TYPES = frozenset({
    "sleep_timer", "mute", "error_state", "repeat", "shuffle", "bluetooth",
})

# ---------------------------------------------------------------------------
# Registry-Pattern for display element renderers (issue #26)
#
# Each entry maps an element type string to a callable with the signature:
#   (audio, sleep_timer, session, state_manager) -> dict | None
#
# Return None to skip the element (conditional types).
# Adding a new type only requires a new entry here — _build_areas() is
# never touched.
# ---------------------------------------------------------------------------

def _render_volume(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    vol = audio.get("volume", 0)
    return {"type": "text", "value": f"{vol}%"}


def _render_sleep_timer(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if sleep_timer.get("active") and sleep_timer.get("remaining_ms") is not None:
        remaining_ms = sleep_timer.get("remaining_ms") or 0
        minutes = max(0, (remaining_ms + 59999) // 60000)
        return {"type": "sleep_timer", "minutes": minutes}
    return None


def _render_mute(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if audio.get("muted"):
        return {"type": "icon", "value": "mute"}
    return None


def _render_play_state(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    state = audio.get("state", "stopped")
    icon_val = "play" if state == "playing" else "pause" if state == "paused" else "stop"
    return {"type": "icon", "value": icon_val}


def _render_clock(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    return {"type": "text", "value": datetime.now().strftime("%H:%M")}


def _render_error_state(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if state_manager.has_error():
        return {"type": "icon", "value": "error"}
    return None


def _render_repeat(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if session.get("repeat_mode") == "all":
        return {"type": "icon", "value": "repeat"}
    return None


def _render_shuffle(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if session.get("shuffle"):
        return {"type": "icon", "value": "shuffle"}
    return None


def _render_bluetooth(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if audio.get("bluetooth_sink_available") and audio.get("multiple_output_devices"):
        return {"type": "icon", "value": "bluetooth"}
    return None


_ELEMENT_RENDERERS: dict[
    str,
    Callable[[dict, dict, dict, Any], dict | None],
] = {
    "volume":      _render_volume,
    "sleep_timer": _render_sleep_timer,
    "mute":        _render_mute,
    "play_state":  _render_play_state,
    "clock":       _render_clock,
    "error_state": _render_error_state,
    "repeat":      _render_repeat,
    "shuffle":     _render_shuffle,
    "bluetooth":   _render_bluetooth,
}


async def _cancel_task(task: asyncio.Task | None, timeout: float = 5.0) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


class DisplayService:
    """Main display service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config_manager = ConfigManager()
        self.state_manager = StateManager(config.env.minabox_device_id)
        self.mqtt_client = MQTTClient(
            config=config,
            on_message_callback=self._handle_mqtt_message,
            on_config_reload_callback=self._handle_config_reload,
        )
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._render_task: asyncio.Task | None = None
        self._sleep_poll_task: asyncio.Task | None = None
        self._session_poll_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._display_config: DisplayServiceConfig | None = None

    async def start(self) -> None:
        """Start the display service."""
        logger.info("display_service_starting")
        self._display_config = self.config_manager.load_config()
        if self._display_config.enabled:
            try:
                display_init(
                    self._display_config.i2c_bus,
                    self._display_config.i2c_address,
                )
            except Exception as exc:
                logger.warning(
                    "display_init_failed",
                    error=str(exc),
                    hint="Display disabled. Check I2C bus configuration.",
                )
        self._warn_overcrowded_areas(self._display_config)
        await self.mqtt_client.connect()
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "display"},
        )
        self._mqtt_task = asyncio.create_task(self.mqtt_client.run())
        self._render_task = asyncio.create_task(self._render_loop())
        self._sleep_poll_task = asyncio.create_task(self._sleep_timer_poll_loop())
        self._session_poll_task = asyncio.create_task(self._session_poll_loop())
        await self._start_api_server()
        logger.info("display_service_started")

    async def _start_api_server(self) -> None:
        app = create_app(self.config, self.config_manager, self.mqtt_client)
        port = self.config.env.api_port
        server_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(server_config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=port)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the display service gracefully."""
        logger.info("display_service_stopping")
        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task)
        await self.mqtt_client.stop()
        await _cancel_task(self._render_task)
        await _cancel_task(self._sleep_poll_task)
        await _cancel_task(self._session_poll_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()
        if is_available():
            clear()
        logger.info("display_service_stopped")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _handle_mqtt_message(self, topic: str, payload: bytes) -> None:
        if topic.endswith("/audio/error") or topic.endswith("/system/service-error"):
            self.state_manager.set_error()
            return
        self.state_manager.update_audio(topic, payload)

    def _handle_config_reload(self) -> None:
        try:
            self._display_config = self.config_manager.reload_config()
            logger.info("config_reload_success")
            self._warn_overcrowded_areas(self._display_config)
            if is_available() and self._display_config and self._display_config.enabled:
                cfg = self._display_config
                areas = self._build_areas()
                if any(areas):
                    show_areas(
                        areas,
                        font_size=cfg.font_size,
                        font=cfg.font,
                    )
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)

    @staticmethod
    def _warn_overcrowded_areas(cfg: DisplayServiceConfig | None) -> None:
        if not cfg:
            return
        limits = {0: _HEADER_MAX_ITEMS, 1: _BODY_MAX_ITEMS, 2: _BODY_MAX_ITEMS}
        for area_idx, limit in limits.items():
            enabled_in_area = [
                e for e in cfg.elements if e.enabled and e.area == area_idx
            ]
            if len(enabled_in_area) > limit:
                types = [e.type for e in enabled_in_area]
                logger.warning(
                    "display_area_overcrowded",
                    area=area_idx,
                    configured=len(enabled_in_area),
                    limit=limit,
                    elements=types,
                    hint=(
                        f"Area {area_idx} has {len(enabled_in_area)} enabled elements but "
                        f"the renderer supports at most {limit}. "
                        "Items beyond the limit will be dropped at render time."
                    ),
                )

    def _build_areas(self) -> list[list[dict]]:
        """Build render areas using the _ELEMENT_RENDERERS registry (issue #26)."""
        cfg = self._display_config
        if not cfg or not cfg.enabled:
            return [[], [], []]
        enabled = [e for e in cfg.elements if e.enabled]
        if not enabled:
            return [[], [], []]

        by_area: list[list] = [[], [], []]
        for area_idx in (0, 1, 2):
            by_area[area_idx] = sorted(
                [e for e in enabled if e.area == area_idx],
                key=lambda e: e.order,
            )

        audio = self.state_manager.get_audio()
        sleep_timer = self.state_manager.get_sleep_timer()
        session = self.state_manager.get_session()

        result: list[list[dict]] = [[], [], []]
        for area_idx in (0, 1, 2):
            for el in by_area[area_idx]:
                renderer = _ELEMENT_RENDERERS.get(el.type)
                if renderer is None:
                    logger.warning("unknown_element_type", el_type=el.type)
                    continue

                item = renderer(audio, sleep_timer, session, self.state_manager)
                if item is None:
                    continue

                limit = _HEADER_MAX_ITEMS if area_idx == 0 else _BODY_MAX_ITEMS
                if len(result[area_idx]) >= limit:
                    logger.warning(
                        "display_area_item_dropped",
                        area=area_idx,
                        dropped_type=el.type,
                        limit=limit,
                    )
                    continue

                result[area_idx].append(item)

        return result

    async def _poll_backend(
        self,
        endpoint: str,
        interval: float,
        update_fn: Callable[[dict], None],
        error_event: str,
    ) -> None:
        """Generic backend polling helper (issue #24).

        The client lives for the whole loop. Building and tearing one down per
        poll was measurably expensive: httpcore runs an import lookup on every
        close, and with two loops polling every 5s that dominated this
        service's CPU time. Reusing it also keeps the connection alive.
        """
        async with httpx.AsyncClient(timeout=3.0) as client:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(interval)
                    try:
                        r = await client.get(f"{BACKEND_URL}{endpoint}")
                        if r.status_code == 200:
                            update_fn(r.json())
                    except (httpx.ConnectError, httpx.TimeoutException):
                        pass
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.debug(error_event, endpoint=endpoint, error=str(exc))

    async def _sleep_timer_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_sleep_timer(
                data.get("active", False),
                data.get("remaining_ms"),
            )
        await self._poll_backend(
            endpoint="/api/v1/audio/sleep-timer",
            interval=SLEEP_TIMER_POLL_INTERVAL,
            update_fn=_update,
            error_event="sleep_timer_poll_error",
        )

    async def _session_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_session(
                data.get("repeat_mode", "none"),
                data.get("shuffle", False),
            )
        await self._poll_backend(
            endpoint="/api/v1/audio/session",
            interval=SESSION_POLL_INTERVAL,
            update_fn=_update,
            error_event="session_poll_error",
        )

    @staticmethod
    def _render_fingerprint(areas: list[list[dict]], font_size: str, font: str) -> str:
        """Stable representation of everything that affects the rendered frame."""
        return json.dumps([areas, font_size, font], sort_keys=True, default=str)

    async def _render_loop(self) -> None:
        last_fingerprint: str | None = None
        last_forced = 0.0
        was_available = False

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(RENDER_INTERVAL)
                available = is_available()
                if not available:
                    was_available = False
                    continue
                if not was_available:
                    # Display (re-)appeared - the panel content is unknown, redraw.
                    last_fingerprint = None
                    was_available = True

                cfg = self._display_config
                if not cfg or not cfg.enabled:
                    continue
                areas = self._build_areas()
                if not any(areas):
                    continue

                fingerprint = self._render_fingerprint(areas, cfg.font_size, cfg.font)
                now = asyncio.get_running_loop().time()
                forced = (now - last_forced) >= FORCE_REDRAW_INTERVAL
                if fingerprint == last_fingerprint and not forced:
                    continue

                show_areas(
                    areas,
                    font_size=cfg.font_size,
                    font=cfg.font,
                )
                last_fingerprint = fingerprint
                if forced:
                    last_forced = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("render_loop_error", error=str(exc))


async def main() -> None:
    config = load_app_config()
    setup_structlog(config.env.log_level)
    logger.info(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )
    service = DisplayService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: signal.Signals) -> None:
        logger.info("signal_received", signal=sig.name)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            pass
    try:
        await service.start()
        await service.run()
    except Exception as exc:
        logger.error("service_error", error=str(exc), exc_info=True)
        raise
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise
