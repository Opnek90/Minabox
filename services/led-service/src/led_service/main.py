"""Main entry point for the LED service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes all components
- Handles graceful shutdown
- Runs the main service loop
- Provides FastAPI health check endpoint
"""

from __future__ import annotations

import asyncio
import signal

import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig
from .core import LEDManager, StateManager
from .infrastructure import MQTTClient

logger = structlog.get_logger(__name__)


class LEDService:
    """Main LED service class."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the LED service.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.config_manager = ConfigManager()
        self.led_manager = LEDManager(disable_gpio=config.env.disable_gpio)
        self.state_manager = StateManager(config.env.minabox_device_id)

        self.mqtt_client = MQTTClient(
            config=config,
            on_message_callback=self._handle_mqtt_message,
            on_config_reload_callback=self._handle_config_reload,
        )

        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None

    async def start(self) -> None:
        """Start the LED service."""
        logger.debug("led_service_starting")

        # Load initial LED configuration
        led_config = self.config_manager.load_config()
        await self.led_manager.initialize_leds(led_config.leds)

        # Start the supervised MQTT loop. It connects in the background and
        # retries forever, so an unreachable broker no longer fails startup.
        self._mqtt_task = await self.mqtt_client.start()

        # Publish service-started event (remembered, so it is re-announced
        # after a reconnect -- the broker may have been restarted).
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "led"},
            remember=True,
        )

        # Apply system_online as the only guaranteed initial state.
        # The RFID state (tag-scanned / tag-removed) is published by the
        # RFID-service on its own startup, so we do not assume it here.
        await self.led_manager.apply_state("system_online")

        # Start FastAPI server
        await self._start_api_server()

        logger.info("led_service_started")

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
        app = create_app(self.config, self.led_manager, self.mqtt_client)

        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_config=None,
        )
        self._api_server = uvicorn.Server(config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=8000)

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.debug("shutdown_requested")

    async def stop(self) -> None:
        """Stop the LED service gracefully."""
        logger.info("led_service_stopping")

        # Stop API server and await its task
        if self._api_server:
            self._api_server.should_exit = True
        if self._uvicorn_task and not self._uvicorn_task.done():
            try:
                await asyncio.wait_for(self._uvicorn_task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass
        logger.debug("api_server_stopped")

        # Stop MQTT client
        await self.mqtt_client.stop()

        # Wait for MQTT task to finish (with timeout)
        if self._mqtt_task and not self._mqtt_task.done():
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except TimeoutError:
                logger.warning("mqtt_task_timeout")
                self._mqtt_task.cancel()

        # Disconnect MQTT
        await self.mqtt_client.disconnect()

        # Clean up LEDs
        await self.led_manager.cleanup()

        logger.info("led_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    async def _handle_mqtt_message(self, topic: str, payload: bytes) -> None:
        """Handle one incoming MQTT message.

        Awaited by the MQTT client rather than dispatched into its own task.
        Loose tasks gave no ordering guarantee -- two states arriving together
        could interleave inside a controller -- and nothing held a reference to
        them, so the garbage collector was free to drop one mid-flight.

        Args:
            topic: The MQTT topic.
            payload: The message payload.
        """
        logical_state = self.state_manager.derive_state(topic, payload)
        if logical_state:
            await self.led_manager.apply_state(logical_state)

    async def _handle_config_reload(self) -> None:
        """Re-read leds.json and rebuild every controller.

        Raises on failure so the MQTT client can report it on config/response
        instead of acknowledging a reload that never happened.
        """
        new_config = self.config_manager.reload_config()
        await self.led_manager.initialize_leds(new_config.leds)
        await self.led_manager.apply_state("system_online")
        logger.debug("config_reload_success")


async def main() -> None:
    """Main async entry point."""
    config = load_app_config()
    setup_structlog(config.env.log_level)

    logger.debug(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = LEDService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: signal.Signals) -> None:
        logger.debug("signal_received", signal=sig.name)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await service.start()
        await service.run()
    except Exception as exc:
        logger.error(
            "service_error",
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise
