"""Main entry point for the LED service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes all components
- Handles graceful shutdown
- Runs the main service loop
- Provides FastAPI health check endpoint
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
import uvicorn

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, LEDServiceConfig
from .led_controller import LEDManager
from .mqtt_client import MQTTClient
from .state_manager import StateManager

logger = structlog.get_logger(__name__)

class LEDService:
    """Main LED service class."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the LED service.
        
        Args:
            config: Application configuration.
        """
        self.config = config
        self.config_manager = ConfigManager()
        self.led_manager = LEDManager()
        self.state_manager = StateManager(config.env.minabox_device_id)
        
        self.mqtt_client = MQTTClient(
            config=config,
            on_message_callback=self._handle_mqtt_message,
            on_config_update_callback=self._handle_config_update,
            on_config_reload_callback=self._handle_config_reload,
        )
        
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None

    async def start(self) -> None:
        """Start the LED service."""
        logger.info("led_service_starting")
        
        # Load initial LED configuration
        led_config = self.config_manager.load_config()
        self.led_manager.initialize_leds(led_config.leds)
        
        # Connect to MQTT
        await self.mqtt_client.connect()
        
        # Publish service-started event
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "led"},
        )
        
        # Start MQTT message loop
        self._mqtt_task = asyncio.create_task(self.mqtt_client.run())
        
        # Start FastAPI server
        await self._start_api_server()
        
        logger.info("led_service_started")

    async def _start_api_server(self) -> None:
        """Start the FastAPI server."""
        app = create_app(self.config, self.led_manager, self.mqtt_client)
        
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_config=None,  # Use our own logging
        )
        self._api_server = uvicorn.Server(config)
        
        # Run server in background task
        asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=8000)

    async def run(self) -> None:
        """Run the service until shutdown is requested."""
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the LED service gracefully."""
        logger.info("led_service_stopping")
        
        # Stop API server
        if self._api_server:
            self._api_server.should_exit = True
            logger.info("api_server_stopped")
        
        # Stop MQTT client
        await self.mqtt_client.stop()
        
        # Wait for MQTT task to finish (with timeout)
        if self._mqtt_task and not self._mqtt_task.done():
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("mqtt_task_timeout")
                self._mqtt_task.cancel()
        
        # Disconnect MQTT
        await self.mqtt_client.disconnect()
        
        # Clean up LEDs
        await self.led_manager.cleanup()
        
        logger.info("led_service_stopped")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_mqtt_message(self, topic: str, payload: bytes) -> None:
        """Handle incoming MQTT messages.
        
        Args:
            topic: The MQTT topic.
            payload: The message payload.
        """
        # Derive logical state
        logical_state = self.state_manager.derive_state(topic, payload)
        
        if logical_state:
            # Apply state to LEDs (async, so schedule it)
            asyncio.create_task(self.led_manager.apply_state(logical_state))

    def _handle_config_update(self, new_config: LEDServiceConfig) -> None:
        """Handle LED configuration updates from MQTT.
        
        Args:
            new_config: The new LED configuration.
        """
        try:
            # Persist config
            self.config_manager.update_config(new_config)
            
            # Re-initialize LEDs
            self.led_manager.initialize_leds(new_config.leds)
            
            # Restore system_online state – device is still running
            asyncio.create_task(self.led_manager.apply_state("system_online"))
            
            logger.info("config_hot_reload_success")
        except Exception as exc:
            logger.error(
                "config_hot_reload_failed",
                error=str(exc),
                exc_info=True,
            )
            raise

    def _handle_config_reload(self) -> None:
        """Handle config reload requests from MQTT."""
        try:
            # Reload from disk
            new_config = self.config_manager.reload_config()
            
            # Re-initialize LEDs
            self.led_manager.initialize_leds(new_config.leds)
            
            # Restore system_online state – device is still running
            asyncio.create_task(self.led_manager.apply_state("system_online"))
            
            logger.info("config_reload_success")
        except Exception as exc:
            logger.error(
                "config_reload_failed",
                error=str(exc),
                exc_info=True,
            )
            raise

def setup_logging(log_level: str) -> None:
    """Set up structured logging with the appropriate renderer.
    
    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
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

async def main() -> None:
    """Main async entry point."""
    # Load configuration
    config = load_app_config()
    
    # Setup logging
    setup_logging(config.env.log_level)
    
    logger.info(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )
    
    # Create service
    service = LEDService(config)
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler(sig: signal.Signals) -> None:
        logger.info("signal_received", signal=sig.name)
        service.request_shutdown()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
    
    try:
        # Start service
        await service.start()
        
        # Run until shutdown
        await service.run()
        
    except Exception as exc:
        logger.error(
            "service_error",
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        # Clean shutdown
        await service.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise
