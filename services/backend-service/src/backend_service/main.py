"""Main entry point for the Backend Service.

This module:
- Sets up structured logging
- Loads configuration
- Initializes database, MQTT, API
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from backend_service.app_factory import BackendService, setup_structlog
from backend_service.config import load_app_config

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Main async entry point."""
    config = load_app_config()
    setup_structlog(
        config.env.log_level,
        silence_loggers=["alembic.runtime.migration", "sqlalchemy.engine"],
    )

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
