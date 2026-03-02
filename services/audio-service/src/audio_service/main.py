"""Main entry point for the Audio Service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes the audio service
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Dict

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from .api import routes
from .config import load_app_config
from .config_schema import AppConfig
from .core import AudioService

logger = structlog.get_logger(__name__)

def create_app(service: AudioService, config: AppConfig) -> FastAPI:
    """Create FastAPI application with health endpoint at root level.

    Args:
        service: AudioService instance.
        config: Application configuration.

    Returns:
        FastAPI application instance.
    """
    app = FastAPI(
        title="Minabox Audio Service",
        description="VLC-based audio player with MQTT control",
        version="0.1.0",
    )

    @app.get("/health")
    async def health_check() -> Dict[str, object]:
        """Health check endpoint."""
        mqtt_connected = service.is_mqtt_connected()
        vlc_initialized = service.is_vlc_initialized()
        status = "healthy" if (mqtt_connected and vlc_initialized) else "degraded"

        return {
            "status": status,
            "service": "audio",
            "device_id": config.env.minabox_device_id,
            "uptime_seconds": service.get_uptime(),
            "mqtt_connected": mqtt_connected,
            "vlc_initialized": vlc_initialized,
            "mqtt_broker": config.env.mqtt_broker,
            "mqtt_port": config.env.mqtt_port,
        }

    # Include additional API routes under /api/v1
    app.include_router(routes.router, prefix="/api/v1")

    return app

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

        # Set service reference for legacy API routes
        routes.set_service(self._service)

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
