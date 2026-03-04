"""Main entry point for the RFID service."""

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


async def _cancel_task(task: asyncio.Task | None, timeout: float = 5.0) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


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
            self._reader = create_reader(self.config.rfid.reader)
            self._reader.initialize()

            await self.mqtt_client.connect()

            device_id = self.config.env.minabox_device_id
            await self.mqtt_client.publish(
                f"minabox/{device_id}/system/service-started",
                {"service": "rfid"},
            )

            self._manager = RFIDManager(self.config, self._reader, self.mqtt_client)
            await self._manager.start()

            self._mqtt_task = asyncio.create_task(self.mqtt_client.run())
            self._scan_task = asyncio.create_task(self._manager.scan_loop())

            await self._start_api_server()

            logger.info("rfid_service_started")
        except Exception as exc:
            logger.error("rfid_service_start_failed", error=str(exc), exc_info=True)
            await self.stop()
            raise

    async def _start_api_server(self) -> None:
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
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the RFID service gracefully."""
        logger.info("rfid_service_stopping")

        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task)
        logger.info("api_server_stopped")

        if self._manager:
            await self._manager.stop()

        await self.mqtt_client.stop()
        await _cancel_task(self._scan_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()

        if self._reader:
            self._reader.cleanup()
            self._reader = None

        logger.info("rfid_service_stopped")

    def request_shutdown(self) -> None:
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_set_mode(self, mode: str) -> None:
        """Handle set-mode command from MQTT (thread-safe)."""
        if self._manager:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self._manager.set_mode(mode))
                )
            except RuntimeError:
                logger.warning("set_mode_no_event_loop", mode=mode)


async def main() -> None:
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
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise


if __name__ == "__main__":
    run()
