"""RFID service entry point with graceful shutdown handling."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from typing import NoReturn

import structlog

from .config import get_config
from .hardware import create_reader
from .mqtt_client import MQTTClient
from .rfid_manager import RFIDManager

logger = structlog.get_logger(__name__)


def setup_logging() -> None:
    """Configure structured logging based on LOG_LEVEL environment variable."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_int = getattr(logging, log_level_name, logging.INFO)

    # Choose renderer based on log level
    if log_level_name == "DEBUG":
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


async def handle_commands(manager: RFIDManager, mqtt_client: MQTTClient) -> None:
    """Handle incoming MQTT commands."""
    logger.info("command_handler_started")
    async for message in mqtt_client.messages():
        # Je nach MQTT-Bibliothek muss hier ggf. .decode() auf topic/payload angewendet werden
        topic = str(message.topic)
        payload = message.payload.decode() if isinstance(message.payload, bytes) else message.payload

        if "cmd/set-mode" in topic:
            try:
                data = json.loads(payload)
                mode = data.get("mode")
                if mode in ("normal", "learning"):
                    logger.info("setting_mode", mode=mode)
                    await manager.set_mode(mode)
                else:
                    logger.warning("invalid_mode", mode=mode)
            except json.JSONDecodeError:
                logger.warning("invalid_command_json", payload=payload)


async def shutdown(
    manager: RFIDManager,
    mqtt_client: MQTTClient,
    reader,
    command_task: asyncio.Task | None = None,
) -> None:
    """Gracefully shutdown the service."""
    logger.info("shutdown_initiated")

    if command_task:
        command_task.cancel()

    # Stop manager first (stop publishing events)
    await manager.stop()

    # Disconnect MQTT
    await mqtt_client.disconnect()

    # Clean up hardware
    reader.cleanup()

    logger.info("shutdown_complete")


async def main() -> NoReturn:
    """Run the RFID service."""
    setup_logging()
    logger.info("rfid_service_starting")

    # Load configuration
    try:
        config = get_config()
    except Exception as exc:
        logger.error("config_load_failed", error=str(exc))
        sys.exit(1)

    # Create reader
    try:
        reader = create_reader(config.reader)
        reader.initialize()
    except Exception as exc:
        logger.error("reader_init_failed", error=str(exc))
        sys.exit(1)

    # Create MQTT client and connect
    mqtt_client = MQTTClient(config)
    try:
        await mqtt_client.connect()
    except Exception as exc:
        logger.error("mqtt_connect_failed", error=str(exc))
        reader.cleanup()
        sys.exit(1)

    # Create and start manager
    manager = RFIDManager(config, reader, mqtt_client)
    await manager.start()

    # --- NEU: MQTT Commands abonnieren ---
    await mqtt_client.subscribe("rfid/cmd/set-mode")
    command_task = asyncio.create_task(handle_commands(manager, mqtt_client))
    # --------------------------------------

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig):
        logger.info("signal_received", signal=sig)
        # Wir starten den Shutdown und stoppen den Loop
        asyncio.create_task(shutdown(manager, mqtt_client, reader, command_task))
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Run scan loop
    try:
        await manager.scan_loop()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as exc:
        logger.error("scan_loop_error", error=str(exc))
    finally:
        await shutdown(manager, mqtt_client, reader, command_task)

    logger.info("rfid_service_stopped")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass