"""Main entry point for the Backend Service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes database, MQTT, API
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_service.api import api_router
from backend_service.api.routes_audio import set_mqtt_client as set_audio_mqtt_client
from backend_service.api.routes_config import set_mqtt_client as set_config_mqtt_client
from backend_service.api.routes_rfid import set_mqtt_client as set_rfid_mqtt_client
from backend_service.api.routes_system import set_mqtt_client as set_system_mqtt_client
from backend_service.api.websocket import websocket_endpoint, ws_manager
from backend_service.config import load_app_config
from backend_service.config_schema import AppConfig
from backend_service.core.db_manager import init_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)

class BackendService:
    """Main backend service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._mqtt_client: MQTTClient | None = None
        self._mqtt_handlers: MQTTHandlers | None = None
        self._mqtt_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._db = None

    async def start(self) -> None:
        """Start the backend service."""
        logger.info("backend_service_starting", version="0.1.0")

        # Initialize database
        logger.info("initializing_database", path=self.config.database_path)
        self._db = init_db(self.config.database_path)

        try:
            self._db.run_migrations()
        except Exception as exc:
            logger.warning("migration_failed", error=str(exc))

        # Initialize MQTT client
        logger.info("initializing_mqtt_client")
        self._mqtt_client = MQTTClient(self.config)
        await self._mqtt_client.connect()

        # Initialize MQTT handlers
        self._mqtt_handlers = MQTTHandlers(self._mqtt_client, ws_manager)

        # Subscribe to MQTT topics
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("rfid", "tag-scanned"),
            self._mqtt_handlers.handle_rfid_tag_scanned,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("rfid", "tag-scanned-learning"),
            self._mqtt_handlers.handle_rfid_tag_scanned_learning,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("audio", "status"),
            self._mqtt_handlers.handle_audio_status,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("button", "+"),
            self._mqtt_handlers.handle_button_action,
        )

        # Inject MQTT client into route modules
        set_audio_mqtt_client(self._mqtt_client)
        set_config_mqtt_client(self._mqtt_client)
        set_rfid_mqtt_client(self._mqtt_client)
        set_system_mqtt_client(self._mqtt_client)

        # Start MQTT listening task
        self._mqtt_task = asyncio.create_task(self._mqtt_client.run())

        # Start FastAPI server
        await self._start_api_server()

        logger.info("backend_service_started_successfully")

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
        app = self._create_app()
        uv_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=self.config.api_port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uv_config)
        asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=self.config.api_port)

    def _create_app(self) -> FastAPI:
        """Create the FastAPI application."""
        app = FastAPI(
            title="Minabox Backend Service",
            description="Central orchestration and data management for Minabox",
            version="0.1.0",
        )

        # CORS middleware for WebUI
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Root-level health check (Framework standard: /health)
        @app.get("/health")
        async def root_health_check():
            mqtt_connected = self._mqtt_client.is_connected if self._mqtt_client else False
            db_ok = self._db is not None
            status = "healthy" if (mqtt_connected and db_ok) else "unhealthy"
            return {
                "status": status,
                "service": "backend",
                "device_id": self.config.device_id,
                "mqtt_connected": mqtt_connected,
                "database_connected": db_ok,
                "mqtt_broker": self.config.mqtt_broker,
                "mqtt_port": self.config.mqtt_port,
            }

        # Include API routes
        app.include_router(api_router)

        # WebSocket endpoint
        app.add_websocket_route("/ws", websocket_endpoint)

        return app

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the backend service gracefully."""
        logger.info("backend_service_stopping")

        # Stop API server
        if self._api_server:
            self._api_server.should_exit = True
            logger.info("api_server_stopped")

        # Stop MQTT
        if self._mqtt_client:
            await self._mqtt_client.stop()
            if self._mqtt_task:
                self._mqtt_task.cancel()
                try:
                    await self._mqtt_task
                except asyncio.CancelledError:
                    pass
            await self._mqtt_client.disconnect()

        # Disconnect database
        if self._db:
            self._db.disconnect()

        logger.info("backend_service_stopped")

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

    logger.info(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = BackendService(config)
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
    """Entry point for python -m backend_service."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise

if __name__ == "__main__":
    run()
