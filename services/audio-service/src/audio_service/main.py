"""Main entry point for the Audio Service.

Initializes logging, configuration, and starts the service.
"""

import asyncio
import logging
import signal
import sys

import structlog
import uvicorn
from fastapi import FastAPI

from .api import routes
from .config_manager import ConfigLoadError, ConfigManager
from .service import AudioService

# Global service instance for signal handlers
_service: AudioService | None = None
_shutdown_event: asyncio.Event | None = None


def setup_logging(log_level: str) -> None:
    """Configure structured logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level_int = getattr(logging, log_level, logging.INFO)

    # Choose renderer based on log level
    if log_level == "DEBUG":
        # Development: Human-readable console format
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Production: Structured JSON format
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


def create_app(config_manager: ConfigManager) -> FastAPI:
    """Create FastAPI application.

    Args:
        config_manager: Configuration manager instance

    Returns:
        FastAPI application instance
    """
    app = FastAPI(
        title="Minabox Audio Service",
        description="VLC-based audio player with MQTT control",
        version="0.1.0",
    )

    # Include API routes
    app.include_router(routes.router, prefix="/api/v1")

    return app


async def run_service(config_manager: ConfigManager) -> None:
    """Run the audio service.

    Args:
        config_manager: Configuration manager instance
    """
    global _service, _shutdown_event

    logger = structlog.get_logger(__name__)

    try:
        # Create service instance
        _service = AudioService(config_manager)

        # Set service reference for API routes
        routes.set_service(_service)

        # Create shutdown event
        _shutdown_event = asyncio.Event()

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: _shutdown_event.set())

        # Start service (this will block listening to MQTT)
        service_task = asyncio.create_task(_service.start())

        # Wait for shutdown signal
        await _shutdown_event.wait()

        logger.info("shutdown_signal_received")

        # Cancel service task
        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass

        # Shutdown service
        await _service.shutdown()

    except Exception as e:
        logger.error("service_run_failed", error=str(e))
        raise


async def start_fastapi_server(config_manager: ConfigManager) -> None:
    """Start FastAPI server in background.

    Args:
        config_manager: Configuration manager instance
    """
    config = config_manager.config.global_config
    app = create_app(config_manager)

    uvicorn_config = uvicorn.Config(
        app,
        host=config.audio_service_host,
        port=config.audio_service_port,
        log_config=None,  # Use our structlog configuration
    )

    server = uvicorn.Server(uvicorn_config)
    await server.serve()


async def main() -> None:
    """Main entry point."""
    logger = structlog.get_logger(__name__)

    try:
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.load()

        # Setup logging with configured level
        setup_logging(config.global_config.log_level)

        logger.info(
            "audio_service_initializing",
            device_id=config.global_config.minabox_device_id,
            mqtt_broker=config.global_config.mqtt_broker,
            log_level=config.global_config.log_level,
        )

        # Run FastAPI and service concurrently
        await asyncio.gather(
            start_fastapi_server(config_manager),
            run_service(config_manager),
        )

    except ConfigLoadError as e:
        logger.error("configuration_error", error=str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
