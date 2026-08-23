"""Main entry point for the RFID service."""

from __future__ import annotations

import asyncio
import signal

import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_schema import AppConfig
from .core import RFIDManager
from .core.rfid_manager import Mode
from .infrastructure import MQTTClient, create_reader

logger = structlog.get_logger(__name__)


async def _cancel_task(task: asyncio.Task | None, timeout: float) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


class RFIDService:
    """Main RFID service class.

    Startup order matters: MQTT and the REST API come up first, and the reader
    is initialised inside the scan loop afterwards. Hardware that is missing or
    miswired therefore produces an observable error status instead of a process
    that dies before it can report anything.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._scan_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._manager: RFIDManager | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Strong references so fire-and-forget tasks are not garbage collected
        # while they are still running.
        self._pending_tasks: set[asyncio.Task] = set()

        self.mqtt_client = MQTTClient(
            config=config,
            on_set_mode_callback=self._handle_set_mode,
        )

    async def start(self) -> None:
        """Start the RFID service."""
        logger.info("rfid_service_starting")
        self._loop = asyncio.get_running_loop()

        try:
            # Connects in the background and retries forever, so an unreachable
            # broker no longer fails startup.
            self._mqtt_task = await self.mqtt_client.start()

            # remember=True: re-announced after a reconnect.
            await self.mqtt_client.publish(
                self.config.get_mqtt_topic("system", "service-started"),
                {"service": "rfid"},
                remember=True,
            )

            self._manager = RFIDManager(
                self.config,
                lambda: create_reader(self.config.rfid.reader),
                self.mqtt_client,
            )
            await self._manager.start()

            self._scan_task = asyncio.create_task(
                self._manager.scan_loop(), name="rfid-scan-loop"
            )

            await self._start_api_server()

            logger.info("rfid_service_started")
        except Exception as exc:
            logger.error("rfid_service_start_failed", error=str(exc), exc_info=True)
            await self.stop()
            raise

    async def _start_api_server(self) -> None:
        app = create_app(self.config, self.mqtt_client, lambda: self._manager)
        port = self.config.env.api_port
        uvicorn_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uvicorn_config)
        self._uvicorn_task = asyncio.create_task(
            self._api_server.serve(), name="rfid-api-server"
        )
        logger.info("api_server_started", port=port)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the RFID service gracefully."""
        logger.info("rfid_service_stopping")
        timeout = self.config.rfid.service.shutdown_timeout_s

        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task, timeout)
        logger.info("api_server_stopped")

        # Stop scanning before the manager publishes its farewell status, so no
        # tag event races the shutdown.
        if self._manager:
            self._manager.request_stop()
        await _cancel_task(self._scan_task, timeout)

        for task in list(self._pending_tasks):
            await _cancel_task(task, timeout)
        self._pending_tasks.clear()

        if self._manager:
            await self._manager.stop()

        await self.mqtt_client.stop()
        await _cancel_task(self._mqtt_task, timeout)
        await self.mqtt_client.disconnect()

        logger.info("rfid_service_stopped")

    def request_shutdown(self) -> None:
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_set_mode(self, mode: Mode) -> None:
        """Handle set-mode command from MQTT (thread-safe)."""
        loop = self._loop
        if self._manager is None or loop is None:
            logger.warning("set_mode_not_ready", mode=mode)
            return
        loop.call_soon_threadsafe(self._schedule_set_mode, mode)

    def _schedule_set_mode(self, mode: Mode) -> None:
        """Run the mode switch on the event loop, keeping a task reference."""
        if self._manager is None:
            return
        task = asyncio.create_task(self._manager.set_mode(mode), name="rfid-set-mode")
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)


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
            loop.add_signal_handler(sig, signal_handler, sig)
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
