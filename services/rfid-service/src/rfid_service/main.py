"""Main entry point for the RFID service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes RFID reader, MQTT, scan loop, API
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_schema import AppConfig
from .core import RFIDManager
from .infrastructure import MQTTClient, RFIDReader, create_reader

logger = structlog.get_logger(__name__)

class RFIDService:
    """Main RFID service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._scan_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._reader: RFIDReader | None = None
        self._manager: RFIDManager | None = None

        self.mqtt_client = MQTTClient(
            config=config,
            on_set_mode_callback=self._handle_set_mode,
        )

    async def start(self) -> None:
        """Start the RFID service."""
        logger.info("rfid_service_starting")

        try:
            # Initialize hardware reader
            self._reader = create_reader(self.config.rfid.reader)
            self._reader.initialize()

            # Connect to MQTT
            await self.mqtt_client.connect()

            # Publish service-started event
            device_id = self.config.env.minabox_device_id
            await self.mqtt_client.publish(
                f"minabox/{device_id}/system/service-started",
                {"service": "rfid"},
            )

            # Create and start manager
            self._manager = RFIDManager(self.config, self._reader, self.mqtt_client)
            await self._manager.start()

            # Start MQTT message loop
            self._mqtt_task = asyncio.create_task(self.mqtt_client.run())

            # Start scan loop
            self._scan_task = asyncio.create_task(self._manager.scan_loop())

            # Start FastAPI server
            await self._start_api_server()

            logger.info("rfid_service_started")
        except Exception as exc:
            logger.error("rfid_service_start_failed", error=str(exc), exc_info=True)
            await self.stop()
            raise

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
        app = create_app(self.config, self.mqtt_client)
        uvicorn_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uvicorn_config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=8000)

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the RFID service gracefully."""
        logger.info("rfid_service_stopping")

        # Stop API server and await its task
        if self._api_server:
            self._api_server.should_exit = True
        if self._uvicorn_task and not self._uvicorn_task.done():
            try:
                await asyncio.wait_for(self._uvicorn_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("api_server_stopped")

        # Stop manager (stops scanning)
        if self._manager:
            await self._manager.stop()

        # Stop MQTT client loop
        await self.mqtt_client.stop()

        # Cancel scan task
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            try:
                await asyncio.wait_for(self._scan_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Wait for MQTT task
        if self._mqtt_task and not self._mqtt_task.done():
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("mqtt_task_timeout")
                self._mqtt_task.cancel()

        await self.mqtt_client.disconnect()

        # Clean up hardware
        if self._reader:
            self._reader.cleanup()
            self._reader = None

        logger.info("rfid_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_set_mode(self, mode: str) -> None:
        """Handle set-mode command from MQTT.

        Uses call_soon_threadsafe because this callback may be invoked from a
        different thread (MQTT client thread) where no event loop is running.
        """
        if self._manager:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self._manager.set_mode(mode))
                )
            except RuntimeError:
                logger.warning("set_mode_no_event_loop", mode=mode)

async def main() -> None:
    """Main async entry point."""
    config = load_app_config()
    setup_structlog(config.env.log_level)

    logger.info(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = RFIDService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: int) -> None:
        logger.info("signal_received", signal=sig)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: signal_handler(s),
            )
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
    """Entry point for python -m rfid_service."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise

if __name__ == "__main__":
    run()
