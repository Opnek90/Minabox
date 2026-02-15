"""Main entry point for Backend Service."""

import asyncio
import logging
import os
import signal
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_service.api import api_router
from backend_service.api.routes_audio import set_mqtt_client as set_audio_mqtt_client
from backend_service.api.routes_system import set_mqtt_client as set_system_mqtt_client
from backend_service.api.websocket import websocket_endpoint, ws_manager
from backend_service.config import get_config
from backend_service.core.db_manager import init_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import MQTTHandlers

# Get log level from environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level_int = getattr(logging, LOG_LEVEL, logging.INFO)

# Configure structlog based on log level
# DEBUG mode: Console renderer (human-readable, for development)
# INFO and above: JSON renderer (structured, for production)
if LOG_LEVEL == "DEBUG":
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

logger = structlog.get_logger(__name__)

# Global instances
mqtt_client: MQTTClient | None = None
mqtt_handlers: MQTTHandlers | None = None
mqtt_task: asyncio.Task | None = None
shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager.

    Handles startup and shutdown tasks.
    """
    # Startup
    logger.info("backend_service_starting", version="0.1.0")

    global mqtt_client, mqtt_handlers, mqtt_task

    try:
        # Load config
        config = get_config()
        logger.info(
            "config_loaded",
            device_id=config.device_id,
            mqtt_broker=config.mqtt_broker,
            api_port=config.api_port,
        )

        # Initialize database
        logger.info("initializing_database", path=config.database_path)
        db = init_db(config.database_path)

        # Run migrations
        try:
            db.run_migrations()
        except Exception as e:
            logger.warning("migration_failed", error=str(e))

        # Initialize MQTT client
        logger.info("initializing_mqtt_client")
        mqtt_client = MQTTClient(config)
        await mqtt_client.connect()

        # Initialize MQTT handlers
        mqtt_handlers = MQTTHandlers(mqtt_client, ws_manager)

        # Subscribe to MQTT topics
        await mqtt_client.subscribe(
            config.get_mqtt_topic("rfid", "tag-scanned"),
            mqtt_handlers.handle_rfid_tag_scanned,
        )
        await mqtt_client.subscribe(
            config.get_mqtt_topic("rfid", "tag-scanned-learning"),
            mqtt_handlers.handle_rfid_tag_scanned_learning,
        )
        await mqtt_client.subscribe(
            config.get_mqtt_topic("audio", "status"),
            mqtt_handlers.handle_audio_status,
        )
        await mqtt_client.subscribe(
            config.get_mqtt_topic("button", "+"),
            mqtt_handlers.handle_button_action,
        )

        # Inject MQTT client into route modules
        set_audio_mqtt_client(mqtt_client)
        set_system_mqtt_client(mqtt_client)

        # Start MQTT listening task
        mqtt_task = asyncio.create_task(mqtt_client.start_listening())

        logger.info("backend_service_started_successfully")

        yield

    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise

    # Shutdown
    logger.info("backend_service_shutting_down")

    try:
        # Stop MQTT listening
        if mqtt_client:
            await mqtt_client.stop_listening()
            if mqtt_task:
                mqtt_task.cancel()
                try:
                    await mqtt_task
                except asyncio.CancelledError:
                    pass

            # Disconnect MQTT
            await mqtt_client.disconnect()

        # Disconnect database
        if db:
            db.disconnect()

        logger.info("backend_service_shutdown_complete")

    except Exception as e:
        logger.error("shutdown_error", error=str(e))


# Create FastAPI app
app = FastAPI(
    title="Minabox Backend Service",
    description="Central orchestration and data management for Minabox",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for WebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# WebSocket endpoint
app.add_websocket_route("/ws", websocket_endpoint)


def handle_shutdown(signum: int, frame: Any) -> None:
    """Handle shutdown signals.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_event.set()


# Register signal handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


async def main() -> None:
    """Run the FastAPI application."""
    config = get_config()

    # Configure uvicorn with matching log level
    uv_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.api_port,
        log_level=LOG_LEVEL.lower(),
        access_log=True,
    )
    server = uvicorn.Server(uv_config)

    # Run server with graceful shutdown
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        logger.info("server_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("application_terminated")
        sys.exit(0)
