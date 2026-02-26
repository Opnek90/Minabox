"""Main entry point for the button service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes GPIO inputs, MQTT, event processor, API
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

import structlog
import uvicorn

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, ButtonServiceConfig
from .core.events import RawButtonEvent
from .core.gpio_input_manager import GPIOInputManager
from .event_processor import run_event_processor
from .exceptions import GPIOInitError
from .mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)

class ButtonService:
    """Main button service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config_manager = ConfigManager()
        self._event_queue: asyncio.Queue[RawButtonEvent] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._processor_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._gpio_manager: GPIOInputManager | None = None

        self.mqtt_client = MQTTClient(
            config=config,
            on_config_update_callback=self._handle_config_update,
            on_config_reload_callback=self._handle_config_reload,
        )

    def _get_buttons_count(self) -> int:
        """Return current number of configured buttons (for health endpoint)."""
        cfg = self.config_manager.get_current_config()
        return len(cfg.buttons) if cfg else 0

    def _get_config(self) -> ButtonServiceConfig | None:
        """Return current button config (for event processor)."""
        return self.config_manager.get_current_config()

    async def start(self) -> None:
        """Start the button service."""
        logger.debug("button_service_starting")

        # Load initial button configuration
        buttons_config = self.config_manager.load_config()
        loop = asyncio.get_running_loop()

        # Initialize GPIO only if not disabled (avoids gpiozero fallback to sysfs in containers)
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
            except (GPIOInitError, Exception) as exc:
                logger.warning(
                    "gpio_init_skipped",
                    error=str(exc),
                    message="Running without button hardware; MQTT and API remain available.",
                )
                self._gpio_manager = None

        # Connect to MQTT
        await self.mqtt_client.connect()

        # Publish service-started event
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "button"},
        )

        # Start MQTT message loop
        self._mqtt_task = asyncio.create_task(self.mqtt_client.run())

        # Start event processor (FIFO → mapping → MQTT)
        self._processor_task = asyncio.create_task(
            run_event_processor(
                event_queue=self._event_queue,
                get_config=self._get_config,
                mqtt_client=self.mqtt_client,
                publish_raw_events=False,
                shutdown_event=self._shutdown_event,
            ),
        )

        # Start FastAPI server
        await self._start_api_server()

        logger.info("button_service_started")

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
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
        asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=8000)

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.debug("shutdown_requested")

    async def stop(self) -> None:
        """Stop the button service gracefully."""
        logger.info("button_service_stopping")

        # Stop API server
        if self._api_server:
            self._api_server.should_exit = True
            logger.debug("api_server_stopped")

        # Stop MQTT client loop
        await self.mqtt_client.stop()

        # Cancel event processor
        if self._processor_task and not self._processor_task.done():
            self._processor_task.cancel()
            try:
                await asyncio.wait_for(self._processor_task, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                logger.warning("processor_task_timeout")

        # Wait for MQTT task
        if self._mqtt_task and not self._mqtt_task.done():
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("mqtt_task_timeout")
                self._mqtt_task.cancel()

        await self.mqtt_client.disconnect()

        # Close GPIO devices
        if self._gpio_manager:
            self._gpio_manager.close()
            self._gpio_manager = None

        logger.info("button_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_config_update(self, new_config: ButtonServiceConfig) -> None:
        """Handle button configuration updates from MQTT."""
        try:
            self.config_manager.update_config(new_config)
            self._reinit_gpio()
            logger.debug("config_update_applied")
        except Exception as exc:
            logger.error(
                "config_update_failed",
                error=str(exc),
                exc_info=True,
            )
            raise

    def _handle_config_reload(self) -> None:
        """Handle config reload requests from MQTT."""
        try:
            self.config_manager.reload_config()
            self._reinit_gpio()
            logger.debug("config_reload_applied")
        except Exception as exc:
            logger.error(
                "config_reload_failed",
                error=str(exc),
                exc_info=True,
            )
            raise

    def _reinit_gpio(self) -> None:
        """Close current GPIO manager and start a new one with current config."""
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
        except (GPIOInitError, Exception) as exc:
            logger.warning(
                "gpio_reinit_skipped",
                error=str(exc),
            )
            self._gpio_manager = None

def setup_logging(log_level: str) -> None:
    """Set up structured logging (Framework.md: DEBUG = Console, INFO+ = JSON)."""
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
    """Main async entry point."""
    config = load_app_config()
    setup_logging(config.env.log_level)

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
            loop.add_signal_handler(
                sig,
                lambda s=sig: signal_handler(s),
            )
        except NotImplementedError:
            # e.g. Windows
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
    """Entry point for python -m button_service."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise

if __name__ == "__main__":
    run()
