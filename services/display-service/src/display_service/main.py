"""Main entry point for the display service."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime

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
RENDER_INTERVAL = 1.0

# Layout limits – must match DisplayRenderer slot counts
_HEADER_MAX_ITEMS = 6
_BODY_MAX_ITEMS = 3

# Element types whose rendered output depends on runtime state.
# These are "conditional" – they may produce 0 or 1 items at render time.
_CONDITIONAL_TYPES = frozenset({
    "sleep_timer", "mute", "error_state", "repeat", "shuffle", "bluetooth",
})


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
        self._api_server: uvicorn.Server | None = None
        self._display_config: DisplayServiceConfig | None = None

    async def start(self) -> None:
        """Start the display service."""
        logger.info("display_service_starting")
        self._display_config = self.config_manager.load_config()
        if self._display_config.enabled:
            display_init(
                self._display_config.i2c_bus,
                self._display_config.i2c_address,
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
        server_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_config=None,
        )
        self._api_server = uvicorn.Server(server_config)
        asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=8000)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        logger.info("display_service_stopping")
        if self._api_server:
            self._api_server.should_exit = True
        await self.mqtt_client.stop()
        if self._render_task and not self._render_task.done():
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass
        if self._sleep_poll_task and not self._sleep_poll_task.done():
            self._sleep_poll_task.cancel()
            try:
                await self._sleep_poll_task
            except asyncio.CancelledError:
                pass
        if self._session_poll_task and not self._session_poll_task.done():
            self._session_poll_task.cancel()
            try:
                await self._session_poll_task
            except asyncio.CancelledError:
                pass
        if self._mqtt_task and not self._mqtt_task.done():
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._mqtt_task.cancel()
            except asyncio.CancelledError:
                pass
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
        """Reload config from disk and redraw display immediately (hot reload)."""
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
                        font_size=getattr(cfg, "font_size", "medium"),
                        font=getattr(cfg, "font", "default"),
                    )
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)

    @staticmethod
    def _warn_overcrowded_areas(cfg: DisplayServiceConfig | None) -> None:
        """Emit a warning for any area whose enabled elements exceed the renderer limit.

        Body areas (1 & 2) hold at most 3 slots; the header (area 0) holds at most 6.
        Conditional elements (mute, shuffle, repeat, …) each *may* produce an item at
        runtime, so an area with more enabled elements than slots will silently drop
        low-priority items.  This warning makes that misconfiguration visible early.
        """
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
                        "Items beyond the limit will be dropped at render time. "
                        "Reduce the number of enabled elements or move some to another area."
                    ),
                )

    def _build_areas(self) -> list[list[dict]]:
        """Build header (area 0) + left (1) + right (2).

        Each area is capped at its renderer limit (_HEADER_MAX_ITEMS / _BODY_MAX_ITEMS)
        *after* evaluating runtime state, so conditional icons (shuffle, repeat, mute …)
        only count against the limit when they are actually active.  Items that exceed
        the cap are dropped with a warning so the renderer never silently clips them.
        """
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
                item: dict | None = None

                if el.type == "volume":
                    vol = audio.get("volume", 0)
                    item = {"type": "text", "value": f"{vol}%"}
                elif el.type == "sleep_timer":
                    if sleep_timer.get("active") and sleep_timer.get("remaining_ms") is not None:
                        remaining_ms = sleep_timer.get("remaining_ms") or 0
                        minutes = max(0, (remaining_ms + 59999) // 60000)
                        item = {"type": "sleep_timer", "minutes": minutes}
                elif el.type == "mute":
                    if audio.get("muted"):
                        item = {"type": "icon", "value": "mute"}
                elif el.type == "play_state":
                    state = audio.get("state", "stopped")
                    icon_val = "play" if state == "playing" else "pause" if state == "paused" else "stop"
                    item = {"type": "icon", "value": icon_val}
                elif el.type == "clock":
                    now = datetime.now()
                    item = {"type": "text", "value": now.strftime("%H:%M")}
                elif el.type == "error_state":
                    if self.state_manager.has_error():
                        item = {"type": "icon", "value": "error"}
                elif el.type == "repeat":
                    if session.get("repeat_mode") == "all":
                        item = {"type": "icon", "value": "repeat"}
                elif el.type == "shuffle":
                    if session.get("shuffle"):
                        item = {"type": "icon", "value": "shuffle"}
                elif el.type == "bluetooth":
                    if audio.get("bluetooth_sink_available") and audio.get("multiple_output_devices"):
                        item = {"type": "icon", "value": "bluetooth"}

                if item is None:
                    continue

                limit = _HEADER_MAX_ITEMS if area_idx == 0 else _BODY_MAX_ITEMS
                if len(result[area_idx]) >= limit:
                    logger.warning(
                        "display_area_item_dropped",
                        area=area_idx,
                        dropped_type=el.type,
                        limit=limit,
                        hint=(
                            f"Area {area_idx} is full ({limit} items). "
                            f"Element '{el.type}' was dropped. "
                            "Move it to another area or disable a lower-priority element."
                        ),
                    )
                    continue

                result[area_idx].append(item)

        return result

    async def _render_loop(self) -> None:
        """Periodically render display from state and config."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(RENDER_INTERVAL)
                if not is_available():
                    continue
                cfg = self._display_config
                if not cfg or not cfg.enabled:
                    continue
                areas = self._build_areas()
                if any(areas):
                    show_areas(
                        areas,
                        font_size=getattr(cfg, "font_size", "medium"),
                        font=getattr(cfg, "font", "default"),
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("render_loop_error", error=str(exc))

    async def _sleep_timer_poll_loop(self) -> None:
        """Poll backend for sleep timer status."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(SLEEP_TIMER_POLL_INTERVAL)
                async with httpx.AsyncClient(timeout=3.0) as client:
                    try:
                        r = await client.get(f"{BACKEND_URL}/api/v1/audio/sleep-timer")
                        if r.status_code == 200:
                            data = r.json()
                            self.state_manager.update_sleep_timer(
                                data.get("active", False),
                                data.get("remaining_ms"),
                            )
                    except (httpx.ConnectError, httpx.TimeoutException):
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("sleep_timer_poll_error", error=str(exc))

    async def _session_poll_loop(self) -> None:
        """Poll backend for session (repeat_mode, shuffle)."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(SLEEP_TIMER_POLL_INTERVAL)
                async with httpx.AsyncClient(timeout=3.0) as client:
                    try:
                        r = await client.get(f"{BACKEND_URL}/api/v1/audio/session")
                        if r.status_code == 200:
                            data = r.json()
                            self.state_manager.update_session(
                                data.get("repeat_mode", "none"),
                                data.get("shuffle", False),
                            )
                    except (httpx.ConnectError, httpx.TimeoutException):
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("session_poll_error", error=str(exc))


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
