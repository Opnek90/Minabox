"""Main entry point for the display service."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

import httpx
import structlog
import uvicorn

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, DisplayServiceConfig
from .display_controller import clear, init as display_init, is_available, show_areas
from .mqtt_client import MQTTClient
from .state_manager import StateManager

logger = structlog.get_logger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")
SLEEP_TIMER_POLL_INTERVAL = 5.0
RENDER_INTERVAL = 1.0


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
        await self.mqtt_client.connect()
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "display"},
        )
        self._mqtt_task = asyncio.create_task(self.mqtt_client.run())
        self._render_task = asyncio.create_task(self._render_loop())
        self._sleep_poll_task = asyncio.create_task(self._sleep_timer_poll_loop())
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
        self.state_manager.update_audio(topic, payload)

    def _handle_config_reload(self) -> None:
        """Reload config from disk and redraw display immediately (hot reload)."""
        try:
            self._display_config = self.config_manager.reload_config()
            logger.info("config_reload_success")
            # Redraw immediately so changes are visible without waiting for next render tick
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

    def _build_areas(self) -> list[list[dict]]:
        """Build 3 columns (areas) from current config and state. Mute/sleep_timer = icon."""
        cfg = self._display_config
        if not cfg or not cfg.enabled:
            return [[], [], []]
        enabled = [e for e in cfg.elements if e.enabled]
        if not enabled:
            return [[], [], []]
        by_area: list[list] = [[], [], []]
        for area_idx in (0, 1, 2):
            area_el = sorted(
                [e for e in enabled if e.area == area_idx],
                key=lambda e: e.order,
            )
            by_area[area_idx] = area_el
        audio = self.state_manager.get_audio()
        sleep_timer = self.state_manager.get_sleep_timer()
        result: list[list[dict]] = [[], [], []]
        for area_idx in (0, 1, 2):
            for el in by_area[area_idx]:
                if el.type == "volume":
                    vol = audio.get("volume", 0)
                    result[area_idx].append({"type": "text", "value": f"{vol}%"})
                elif el.type == "sleep_timer":
                    if sleep_timer.get("active") and sleep_timer.get("remaining_ms") is not None:
                        result[area_idx].append({"type": "icon", "value": "sleep_timer"})
                elif el.type == "mute":
                    if audio.get("muted"):
                        result[area_idx].append({"type": "icon", "value": "mute"})
                elif el.type == "play_state":
                    state = audio.get("state", "stopped")
                    result[area_idx].append({"type": "text", "value": state[:5]})
                elif el.type == "clock":
                    now = datetime.now(timezone.utc)
                    result[area_idx].append({"type": "text", "value": now.strftime("%H:%M")})
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


def setup_logging(log_level: str) -> None:
    log_level_int = getattr(logging, log_level, logging.INFO)
    if log_level == "DEBUG":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


async def main() -> None:
    config = load_app_config()
    setup_logging(config.env.log_level)
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
