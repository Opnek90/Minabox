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
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend_service.api import api_router
from backend_service.api.routes_auth import COOKIE_NAME
from backend_service.api.routes_audio import (
    set_mqtt_client as set_audio_mqtt_client,
    set_mqtt_handlers as set_audio_mqtt_handlers,
)
from backend_service.api.routes_config import set_mqtt_client as set_config_mqtt_client
from backend_service.api.routes_rfid import set_mqtt_client as set_rfid_mqtt_client
from backend_service.api.routes_system import set_mqtt_client as set_system_mqtt_client
from backend_service.api.websocket import websocket_endpoint, ws_manager
from backend_service.config_schema import AppConfig
from backend_service.core.auth import read_auth_settings, verify_session_token
from backend_service.core.db_manager import init_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import MQTTHandlers
from backend_service.core.podcast_fetcher import run_podcast_fetch_loop
from backend_service.core.temperature_logger import run_temperature_log_loop

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
        logger.info("backend_service_starting", version="0.1.0")

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
            self.config.get_mqtt_topic("rfid", "tag-removed"),
            self._mqtt_handlers.handle_rfid_tag_removed,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("audio", "status"),
            self._mqtt_handlers.handle_audio_status,
        )
        await self._mqtt_client.subscribe(
            self.config.get_mqtt_topic("button", "+"),
            self._mqtt_handlers.handle_button_action,
        )

        # Inject MQTT client and handlers into route modules
        set_audio_mqtt_client(self._mqtt_client)
        set_audio_mqtt_handlers(self._mqtt_handlers)
        set_config_mqtt_client(self._mqtt_client)
        set_rfid_mqtt_client(self._mqtt_client)
        set_system_mqtt_client(self._mqtt_client)

        # Publish current general config (e.g. log_level) as retained so other services get it on subscribe
        topic = get_mqtt_topic(self.config.env.minabox_device_id, "config", "general")
        await self._mqtt_client.publish(
            topic,
            {"log_level": self.config.env.log_level},
            qos=1,
            retain=True,
        )
        logger.debug("config_general_published_retained", topic=topic)

        # Start MQTT listening task
        self._mqtt_task = asyncio.create_task(self._mqtt_client.run())

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
            version="0.1.0",
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

        # Web auth: require session cookie for protected API paths
        @app.middleware("http")
        async def web_auth_middleware(request: Request, call_next):
            path = request.url.path
            if not path.startswith("/api/v1/"):
                return await call_next(request)
            if path in (
                "/api/v1/auth/config",
                "/api/v1/auth/login",
                "/api/v1/auth/logout",
            ):
                return await call_next(request)
            settings = read_auth_settings()
            auth_enabled = bool((settings.get("web_password_hash") or "").strip())
            if not auth_enabled:
                return await call_next(request)
            protected_areas = set(settings.get("protected_areas") or [])
            if not protected_areas:
                return await call_next(request)
            area = None
            if path.startswith("/api/v1/config") or path.startswith("/api/v1/system"):
                area = "admin"
            elif path.startswith("/api/v1/playlists") or path.startswith(
                "/api/v1/tracks"
            ) or path.startswith("/api/v1/streams") or path.startswith(
                "/api/v1/podcasts"
            ):
                area = "media"
            elif path.startswith("/api/v1/stats"):
                area = "dashboard"
            if area is None or area not in protected_areas:
                return await call_next(request)
            token = request.cookies.get(COOKIE_NAME)
            if not token or not verify_session_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            return await call_next(request)

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

        # Disconnect database
        if self._db:
            self._db.disconnect()

        logger.info("backend_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()


__all__ = ["BackendService", "setup_structlog"]
