"""Main entry point for the button service."""

from __future__ import annotations

import asyncio
import signal

import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, ButtonServiceConfig
from .core.event_processor import run_event_processor
from .core.events import RawButtonEvent
from .core.gpio_input_manager import GPIOInputManager
from .infrastructure import MQTTClient
from .models import HealthState

logger = structlog.get_logger(__name__)


async def _cancel_task(task: asyncio.Task | None, timeout: float = 5.0) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


class ButtonService:
    """Main button service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config_manager = ConfigManager()
        self._event_queue: asyncio.Queue[RawButtonEvent] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._processor_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._gpio_manager: GPIOInputManager | None = None
        self._config_error: str | None = None

        self.mqtt_client = MQTTClient(
            config=config,
            on_config_update_callback=self._handle_config_update,
            on_config_reload_callback=self._handle_config_reload,
        )

    def _get_buttons_count(self) -> int:
        cfg = self.config_manager.get_current_config()
        return len(cfg.buttons) if cfg else 0

    def _get_config(self) -> ButtonServiceConfig | None:
        return self.config_manager.get_current_config()

    def _get_health_state(self) -> HealthState:
        """Snapshot for /health: what is configured, and what actually runs."""
        gpio_enabled = not self.config.env.disable_gpio
        manager = self._gpio_manager
        return HealthState(
            buttons_configured=self._get_buttons_count(),
            buttons_available=manager.available_count if manager else 0,
            gpio_enabled=gpio_enabled,
            config_error=self._config_error,
        )

    def _load_buttons_config(self) -> ButtonServiceConfig:
        """Load buttons.json, or fall back to an empty set.

        A config the schema rejects used to end the process before the API was
        even up. With `restart: unless-stopped` that is a restart loop, and the
        WebUI -- the only way to repair the file -- goes with it. Coming up
        empty and reporting it on /health leaves a way back in.
        """
        try:
            config = self.config_manager.load_config()
        except Exception as exc:
            self._config_error = str(exc)
            logger.error(
                "config_load_failed",
                error=str(exc),
                message=(
                    "Starting without buttons. Fix config/buttons.json via the "
                    "WebUI (Admin -> Buttons); it is reloaded on save."
                ),
            )
            return ButtonServiceConfig()
        self._config_error = None
        return config

    async def start(self) -> None:
        """Start the button service."""
        logger.debug("button_service_starting")

        buttons_config = self._load_buttons_config()
        self._start_gpio(buttons_config)

        # Connects in the background and retries forever, so an unreachable
        # broker no longer fails startup.
        self._mqtt_task = await self.mqtt_client.start()

        # Use get_mqtt_topic() instead of manual f-string (issue #16).
        # remember=True: re-announced after a reconnect.
        await self.mqtt_client.publish(
            self.config.get_mqtt_topic("system", "service-started"),
            {"service": "button"},
            remember=True,
        )

        self._processor_task = asyncio.create_task(
            run_event_processor(
                event_queue=self._event_queue,
                get_config=self._get_config,
                mqtt_client=self.mqtt_client,
                shutdown_event=self._shutdown_event,
            ),
        )

        await self._start_api_server()

        logger.info("button_service_started")

    def _start_gpio(self, buttons_config: ButtonServiceConfig) -> None:
        """Bring up the input devices for the given configuration.

        Only a pin factory that cannot be created is fatal to the hardware
        layer; a single unavailable pin is skipped inside the manager. On
        failure the manager is closed before it is dropped -- dropping it
        without closing left the pins it had already claimed busy until the
        container was restarted.
        """
        if self.config.env.disable_gpio:
            logger.info(
                "gpio_disabled_by_config",
                message="DISABLE_GPIO=true; running without button hardware.",
            )
            self._gpio_manager = None
            return

        manager = GPIOInputManager(
            config=buttons_config,
            event_queue=self._event_queue,
            loop=asyncio.get_running_loop(),
        )
        try:
            manager.start()
        except Exception as exc:
            manager.close()
            logger.warning(
                "gpio_init_skipped",
                error=str(exc),
                message=(
                    "Running without button hardware; MQTT and API remain available."
                ),
            )
            self._gpio_manager = None
            return

        self._gpio_manager = manager

    async def _start_api_server(self) -> None:
        app = create_app(
            self.config,
            self.mqtt_client,
            get_health_state=self._get_health_state,
        )
        # Read port from config instead of hardcoding 8000 (issue #17)
        port = self.config.env.api_port
        uvicorn_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(uvicorn_config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.debug("api_server_started", port=port)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.debug("shutdown_requested")

    async def stop(self) -> None:
        """Stop the button service gracefully."""
        logger.info("button_service_stopping")

        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task)
        logger.debug("api_server_stopped")

        await self.mqtt_client.stop()
        await _cancel_task(self._processor_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()

        if self._gpio_manager:
            self._gpio_manager.close()
            self._gpio_manager = None

        logger.info("button_service_stopped")

    def request_shutdown(self) -> None:
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    def _handle_config_update(self, new_config: ButtonServiceConfig) -> None:
        try:
            self.config_manager.update_config(new_config)
            self._reinit_gpio()
            self._config_error = None
            logger.debug("config_update_applied")
        except Exception as exc:
            self._config_error = str(exc)
            logger.error("config_update_failed", error=str(exc), exc_info=True)
            raise

    def _handle_config_reload(self) -> None:
        try:
            self.config_manager.reload_config()
            self._reinit_gpio()
            self._config_error = None
            logger.debug("config_reload_applied")
        except Exception as exc:
            # The previous configuration keeps running, so the buttons still
            # work -- but what is on disk no longer matches, and the next
            # restart would come up empty. /health has to say so, because
            # config/response has no subscriber.
            self._config_error = str(exc)
            logger.error("config_reload_failed", error=str(exc), exc_info=True)
            raise

    def _reinit_gpio(self) -> None:
        if self.config.env.disable_gpio:
            return
        cfg = self.config_manager.get_current_config()
        if not cfg:
            return

        # Release the pins first, otherwise the new devices cannot claim them.
        if self._gpio_manager:
            self._gpio_manager.close()
            self._gpio_manager = None

        self._start_gpio(cfg)
        manager = self._gpio_manager
        logger.debug(
            "gpio_reinitialized",
            buttons_count=len(cfg.buttons),
            available=manager.available_count if manager else 0,
        )


async def main() -> None:
    config = load_app_config()
    setup_structlog(config.env.log_level)

    logger.debug(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )

    service = ButtonService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: int) -> None:
        logger.debug("signal_received", signal=sig)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise


if __name__ == "__main__":
    run()
