"""Application factory and service setup for the Backend Service.

Contains the `BackendService` orchestration class and logging setup.
The `main.py` module is kept as a thin runtime entrypoint.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog
from shared_lib.logging import setup_structlog
from shared_lib.mqtt import get_mqtt_topic
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend_service import __version__
from backend_service.api import api_router
from backend_service.api.routes_audio import (
    set_mqtt_client as set_audio_mqtt_client,
    set_mqtt_handlers as set_audio_mqtt_handlers,
)
from backend_service.api.routes_config import set_mqtt_client as set_config_mqtt_client
from backend_service.api.routes_rfid import set_mqtt_client as set_rfid_mqtt_client
from backend_service.api.routes_system import set_mqtt_client as set_system_mqtt_client
from backend_service.api.websocket import websocket_endpoint, ws_manager
from backend_service.config_schema import AppConfig
from backend_service.core.db_manager import init_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import MQTTHandlers
from backend_service.core.podcast_fetcher import run_podcast_fetch_loop
from backend_service.api.routes_host import close_host_helper_client
from backend_service.core.temperature_logger import run_temperature_log_loop
from backend_service.middleware.auth import web_auth_middleware

logger = structlog.get_logger(__name__)


class BackendService:
    """Main backend service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._mqtt_client: MQTTClient | None = None
        self._mqtt_handlers: MQTTHandlers | None = None
        self._mqtt_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._db = None
        self._podcast_fetch_task: asyncio.Task | None = None
        self._temperature_log_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the backend service."""
        logger.info("backend_service_starting", version=__version__)

        # Initialize database
        logger.debug("initializing_database", path=self.config.database_path)
        self._db = init_db(self.config.database_path)

        try:
            self._db.run_migrations()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("migration_failed", error=str(exc))

        # Ensure audio storage path exists (fail fast if volume is not writable)
        try:
            Path(self.config.audio_storage_path).mkdir(parents=True, exist_ok=True)
        except OSError as e:  # pragma: no cover - environment-dependent
            logger.warning(
                "audio_storage_path_unusable",
                path=self.config.audio_storage_path,
                error=str(e),
                hint=(
                    "Ensure volume is mounted read-write and host path is writable "
                    "(e.g. chown 1000:1000)."
                ),
            )

        # Initialize MQTT client
        logger.debug("initializing_mqtt_client")
        self._mqtt_client = MQTTClient(self.config)
        # Connects in the background and retries forever. Startup must not
        # depend on the broker being reachable -- that dependency is what took
        # the services down when the broker restarted.
        self._mqtt_task = await self._mqtt_client.start()

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
            self.config.get_mqtt_topic("rfid", "tag-removed"),
            self._mqtt_handlers.handle_rfid_tag_removed,
        )
        # Retained topic: the RFID service publishes it on every change and at
        # startup, so a reconnecting backend learns the current card state
        # immediately. Needed for the "repeat while the card lies there" mode.
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("rfid", "presence"),
            self._mqtt_handlers.handle_rfid_presence,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("audio", "status"),
            self._mqtt_handlers.handle_audio_status,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("audio", "position-report"),
            self._mqtt_handlers.handle_audio_position_report,
        )
        # button/+ catches all mapped action topics (play-pause, volume-up, …)
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("button", "+"),
            self._mqtt_handlers.handle_button_action,
        )
        # button/raw-event is published for every physical press, regardless of
        # action mapping — used by the WebUI hardware test-mode.
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("button", "raw-event"),
            self._mqtt_handlers.handle_button_raw_event,
        )

        # Inject MQTT client and handlers into route modules
        set_audio_mqtt_client(self._mqtt_client)
        set_audio_mqtt_handlers(self._mqtt_handlers)
        set_config_mqtt_client(self._mqtt_client)
        set_rfid_mqtt_client(self._mqtt_client)
        set_system_mqtt_client(self._mqtt_client)

        # Publish current general config (e.g. log_level) as retained so other
        # services get it on subscribe. publish_state() does not raise and is
        # replayed after a reconnect, so a broker outage neither fails startup
        # nor loses the retained value when the broker comes back.
        topic = get_mqtt_topic(self.config.env.minabox_device_id, "config", "general")
        await self._mqtt_client.publish_state(
            topic,
            {"log_level": self.config.env.log_level},
            qos=1,
            retain=True,
        )
        logger.debug("config_general_published_retained", topic=topic)

        # Start podcast RSS fetch loop (daily)
        self._podcast_fetch_task = asyncio.create_task(run_podcast_fetch_loop(self._db))

        # Start temperature log loop (sample + overheating alert)
        self._temperature_log_task = asyncio.create_task(
            run_temperature_log_loop(
                self._db,
                self._mqtt_client,
                self.config.device_id,
                self.config.get_mqtt_topic,
                ws_manager.broadcast,
            )
        )

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
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=self.config.api_port)

    def _create_app(self) -> FastAPI:
        """Create the FastAPI application."""
        app = FastAPI(
            title="Minabox Backend Service",
            description="Central orchestration and data management for Minabox",
            version=__version__,
        )

        # CORS middleware: origins are loaded from config to allow per-environment
        # restriction. Use CORS_ALLOWED_ORIGINS=['*'] in .env for local dev;
        # in production set the actual frontend URL (e.g. http://minabox.local).
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.env.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Web auth middleware (extracted to middleware/auth.py for testability)
        app.add_middleware(BaseHTTPMiddleware, dispatch=web_auth_middleware)

        # Root-level health check (Framework standard: /health)
        @app.get("/health")
        async def root_health_check():
            mqtt_connected = self._mqtt_client.is_connected if self._mqtt_client else False
            db_ok = self._db is not None
            # Startup/readiness: API is usable once DB is up; MQTT can lag behind.
            if db_ok and mqtt_connected:
                status = "healthy"
            elif db_ok:
                status = "degraded"
            else:
                status = "unhealthy"
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

        # Serve user-uploaded static files (logo, playlist covers, …)
        static_dir = Path(os.environ.get("STATIC_DIR", "/data/static"))
        static_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        return app

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the backend service gracefully."""
        logger.info("backend_service_stopping")

        # Stop API server and await its task
        if self._api_server:
            self._api_server.should_exit = True
        if self._uvicorn_task and not self._uvicorn_task.done():
            try:
                await asyncio.wait_for(self._uvicorn_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("api_server_stopped")

        # Stop podcast fetch task
        if self._podcast_fetch_task:
            self._podcast_fetch_task.cancel()
            try:
                await self._podcast_fetch_task
            except asyncio.CancelledError:
                pass

        # Stop temperature log task
        if self._temperature_log_task:
            self._temperature_log_task.cancel()
            try:
                await self._temperature_log_task
            except asyncio.CancelledError:
                pass

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

        # Close the pooled Host-Helper HTTP client
        await close_host_helper_client()

        # Disconnect database
        if self._db:
            self._db.disconnect()

        logger.info("backend_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()


__all__ = ["BackendService", "setup_structlog"]
