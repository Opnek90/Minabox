"""Main entry point for the button service."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, ButtonServiceConfig
from .core.events import RawButtonEvent
from .core.event_processor import run_event_processor
from .core.gpio_input_manager import GPIOInputManager
from .exceptions import GPIOInitError
from .infrastructure import MQTTClient

logger = structlog.get_logger(__name__)


async def _cancel_task(task: asyncio.Task | None, timeout: float = 5.0) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


class ButtonService:
    """Main button service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config_manager = ConfigManager()
        self._event_queue: asyncio.Queue[RawButtonEvent] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._processor_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._gpio_manager: GPIOInputManager | None = None

        self.mqtt_client = MQTTClient(
            config=config,
            on_config_update_callback=self._handle_config_update,
            on_config_reload_callback=self._handle_config_reload,
        )

    def _get_buttons_count(self) -> int:
        cfg = self.config_manager.get_current_config()
        return len(cfg.buttons) if cfg else 0

    def _get_config(self) -> ButtonServiceConfig | None:
        return self.config_manager.get_current_config()

    async def start(self) -> None:
        """Start the button service."""
        logger.debug("button_service_starting")

        buttons_config = self.config_manager.load_config()
        loop = asyncio.get_running_loop()

        disable_gpio = os.environ.get("DISABLE_GPIO", "false").strip().lower() in ("true", "1")
        if disable_gpio:
            logger.info("gpio_disabled_by_config", message="DISABLE_GPIO=true; running without button hardware.")
            self._gpio_manager = None
        else:
            try:
                self._gpio_manager = GPIOInputManager(
                    config=buttons_config,
                    event_queue=self._event_queue,
                    loop=loop,
                )
                self._gpio_manager.start()
            except Exception as exc:
                logger.warning(
                    "gpio_init_skipped",
                    error=str(exc),
                    message="Running without button hardware; MQTT and API remain available.",
                )
                self._gpio_manager = None

        await self.mqtt_client.connect()

        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "button"},
        )

        self._mqtt_task = asyncio.create_task(self.mqtt_client.run())

        self._processor_task = asyncio.create_task(
            run_event_processor(
                event_queue=self._event_queue,
                get_config=self._get_config,
                mqtt_client=self.mqtt_client,
                shutdown_event=self._shutdown_event,
            ),
        )

        await self._start_api_server()

        logger.info("button_service_started")

    async def _start_api_server(self) -> None:
        app = create_app(
            self.config,
            self.mqtt_client,
            get_buttons_count=self._get_buttons_count,
        )
        uvicorn_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uvicorn_config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=8000)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.debug("shutdown_requested")

    async def stop(self) -> None:
        """Stop the button service gracefully."""
        logger.info("button_service_stopping")

        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task)
        logger.debug("api_server_stopped")

        await self.mqtt_client.stop()
        await _cancel_task(self._processor_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()

        if self._gpio_manager:
            self._gpio_manager.close()
            self._gpio_manager = None

        logger.info("button_service_stopped")

    def request_shutdown(self) -> None:
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_config_update(self, new_config: ButtonServiceConfig) -> None:
        try:
            self.config_manager.update_config(new_config)
            self._reinit_gpio()
            logger.debug("config_update_applied")
        except Exception as exc:
            logger.error("config_update_failed", error=str(exc), exc_info=True)
            raise

    def _handle_config_reload(self) -> None:
        try:
            self.config_manager.reload_config()
            self._reinit_gpio()
            logger.debug("config_reload_applied")
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)
            raise

    def _reinit_gpio(self) -> None:
        if os.environ.get("DISABLE_GPIO", "false").strip().lower() in ("true", "1"):
            return
        cfg = self.config_manager.get_current_config()
        if not cfg:
            return
        if self._gpio_manager:
            self._gpio_manager.close()
            self._gpio_manager = None
        try:
            loop = asyncio.get_running_loop()
            self._gpio_manager = GPIOInputManager(
                config=cfg,
                event_queue=self._event_queue,
                loop=loop,
            )
            self._gpio_manager.start()
            logger.debug("gpio_reinitialized", buttons_count=len(cfg.buttons))
        except Exception as exc:
            logger.warning("gpio_reinit_skipped", error=str(exc))
            self._gpio_manager = None


async def main() -> None:
    config = load_app_config()
    setup_structlog(config.env.log_level)

    logger.debug(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = ButtonService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: int) -> None:
        logger.debug("signal_received", signal=sig)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            break

    try:
        await service.start()
        await service.run()
    except Exception as exc:
        logger.error("service_error", error=str(exc), exc_info=True)
        raise
    finally:
        await service.stop()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise


if __name__ == "__main__":
    run()
