"""Main entry point for the Audio Service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes the audio service
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import signal
import structlog
from shared_lib.logging import setup_structlog
import uvicorn
from .api.routes import create_app
from .config import load_app_config
from .config_schema import AppConfig
from .core import AudioService

logger = structlog.get_logger(__name__)


class AudioServiceRunner:
    """Top-level service runner following the standard service pattern."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._service = AudioService(config)
        self._shutdown_event = asyncio.Event()
        self._api_server: uvicorn.Server | None = None

    async def start(self) -> None:
        """Start the audio service and API server."""
        logger.debug("audio_service_starting")

        # Start the audio service (MQTT, VLC, etc.)
        await self._service.start()

        # Start FastAPI server
        await self._start_api_server()

        logger.info("audio_service_started")

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
        app = create_app(self._service, self.config)
        uvicorn_config = uvicorn.Config(
            app=app,
            host=self.config.env.audio_service_host,
            port=self.config.env.audio_service_port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uvicorn_config)
        asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=self.config.env.audio_service_port)

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the audio service gracefully."""
        logger.info("audio_service_stopping")

        # Stop API server
        if self._api_server:
            self._api_server.should_exit = True
            logger.debug("api_server_stopped")

        # Shutdown the audio service
        await self._service.shutdown()

        logger.info("audio_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

async def main() -> None:
    """Main async entry point."""
    config = load_app_config()
    setup_structlog(config.env.log_level)

    logger.debug(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = AudioServiceRunner(config)
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
    """Entry point for python -m audio_service."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise

if __name__ == "__main__":
    run()
