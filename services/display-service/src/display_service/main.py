"""Main entry point for the display service."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import structlog
import uvicorn
from shared_lib.logging import setup_structlog

from .api.routes import create_app
from .config import load_app_config
from .config_manager import ConfigManager
from .config_schema import AppConfig, DisplayServiceConfig
from .core import StateManager
from .infrastructure import (
    MQTTClient,
    clear,
    is_available,
    show_areas,
    show_image,
    show_lines,
)
from .infrastructure import (
    init as display_init,
)
from .infrastructure import (
    shutdown as display_shutdown,
)
from .render.volume import VolumeView
from .render.volume import render as render_volume

logger = structlog.get_logger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")
SLEEP_TIMER_POLL_INTERVAL = 5.0
# Repeat and shuffle change when somebody presses a button, and the panel shows
# them as a single icon. One request every 5 seconds bought a latency nobody can
# perceive at a measured 12 ms of CPU per request.
SESSION_POLL_INTERVAL = 15.0
RENDER_INTERVAL = 1.0
# The render loop ticks every second, but the OLED shares /dev/i2c-1 with the
# PN532 RFID reader. Redrawing identical content just adds bus contention on the
# box's primary input path, and the clock element only resolves to HH:MM - so 59
# of 60 frames per minute used to be redundant. Frames are therefore only pushed
# when the rendered content actually changed, with a periodic forced redraw so a
# glitched display still heals itself.
FORCE_REDRAW_INTERVAL = 60.0
# How often the render loop retries opening the panel while there is none.
#
# init() used to be called exactly once, at startup. If the panel was not ready
# then - this container starts while the rest of the stack is still settling,
# and it shares the bus with the RFID reader - it stayed dark for the life of
# the process, and the "display re-appeared" branch below could never fire.
DISPLAY_INIT_RETRY_INTERVAL = 30.0
# How long the setup wizard's test pattern is held on the panel.
TEST_PATTERN_SECONDS = 6.0
# How long the volume overlay owns the panel after the last change.
HUD_SECONDS = 1.5
# A knob turn arrives as a burst of status messages, one per detent. Without a
# floor the loop would push a full frame for each of them and hold the I2C bus
# - shared with the RFID reader - for most of the turn.
MIN_REDRAW_INTERVAL = 0.15

_HEADER_MAX_ITEMS = 6
_BODY_MAX_ITEMS = 3

# ---------------------------------------------------------------------------
# Registry-Pattern for display element renderers (issue #26)
#
# Each entry maps an element type string to a callable with the signature:
#   (audio, sleep_timer, session, state_manager) -> dict | None
#
# Return None to skip the element (conditional types).
# Adding a new type only requires a new entry here — _build_areas() is
# never touched.
# ---------------------------------------------------------------------------


def _render_volume(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    vol = audio.get("volume", 0)
    return {"type": "text", "value": f"{vol}%"}


def _render_sleep_timer(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if sleep_timer.get("active") and sleep_timer.get("remaining_ms") is not None:
        remaining_ms = sleep_timer.get("remaining_ms") or 0
        minutes = max(0, (remaining_ms + 59999) // 60000)
        return {"type": "sleep_timer", "minutes": minutes}
    return None


def _render_mute(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if audio.get("muted"):
        return {"type": "icon", "value": "mute"}
    return None


def _render_play_state(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    state = audio.get("state", "stopped")
    if state == "playing":
        icon_val = "play"
    elif state == "paused":
        icon_val = "pause"
    else:
        icon_val = "stop"
    return {"type": "icon", "value": icon_val}


def _render_clock(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    return {"type": "text", "value": datetime.now().strftime("%H:%M")}


def _render_error_state(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if state_manager.has_error():
        return {"type": "icon", "value": "error"}
    return None


def _render_repeat(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if session.get("repeat_mode") == "all":
        return {"type": "icon", "value": "repeat"}
    return None


def _render_shuffle(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if session.get("shuffle"):
        return {"type": "icon", "value": "shuffle"}
    return None


def _render_bluetooth(
    audio: dict, sleep_timer: dict, session: dict, state_manager: Any
) -> dict | None:
    if audio.get("bluetooth_sink_available") and audio.get("multiple_output_devices"):
        return {"type": "icon", "value": "bluetooth"}
    return None


# fmt: off
_ELEMENT_RENDERERS: dict[
    str,
    Callable[[dict, dict, dict, Any], dict | None],
] = {
    "volume":      _render_volume,
    "sleep_timer": _render_sleep_timer,
    "mute":        _render_mute,
    "play_state":  _render_play_state,
    "clock":       _render_clock,
    "error_state": _render_error_state,
    "repeat":      _render_repeat,
    "shuffle":     _render_shuffle,
    "bluetooth":   _render_bluetooth,
}
# fmt: on


async def _cancel_task(task: asyncio.Task | None, timeout: float = 5.0) -> None:
    """Cancel an asyncio Task and wait for it to finish cleanly."""
    if task is None or task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.debug("task_cancel_timeout", task_name=task.get_name())


class DisplayService:
    """Main display service class."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config_manager = ConfigManager()
        self.state_manager = StateManager(config.env.minabox_device_id)
        self.mqtt_client = MQTTClient(
            config=config,
            on_message_callback=self._handle_mqtt_message,
            on_config_reload_callback=self._handle_config_reload,
        )
        self._shutdown_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None
        self._render_task: asyncio.Task | None = None
        self._sleep_poll_task: asyncio.Task | None = None
        self._session_poll_task: asyncio.Task | None = None
        self._uvicorn_task: asyncio.Task | None = None
        self._api_server: uvicorn.Server | None = None
        self._display_config: DisplayServiceConfig | None = None
        # Deadline up to which the render loop leaves the test pattern alone.
        self._test_pattern_until: float = 0.0
        # The volume overlay: what to draw, until when, and the last state we
        # saw, so a republished but unchanged status does not raise it again.
        self._hud_until: float = 0.0
        self._hud_view: VolumeView | None = None
        self._last_volume_key: tuple | None = None
        # Lets an incoming message pull the next frame forward instead of
        # waiting out the tick. A knob has to feel immediate.
        self._wake = asyncio.Event()

    async def start(self) -> None:
        """Start the display service."""
        logger.info("display_service_starting")
        self._display_config = self.config_manager.load_config()
        if self._display_config.enabled:
            display_init(
                self._display_config.i2c_bus,
                self._display_config.i2c_address,
            )
        self._warn_overcrowded_areas(self._display_config)
        # Connects in the background and retries forever, so an unreachable
        # broker no longer fails startup.
        self._mqtt_task = await self.mqtt_client.start()
        device_id = self.config.env.minabox_device_id
        await self.mqtt_client.publish(
            f"minabox/{device_id}/system/service-started",
            {"service": "display"},
            remember=True,
        )
        self._render_task = asyncio.create_task(self._render_loop())
        self._sleep_poll_task = asyncio.create_task(self._sleep_timer_poll_loop())
        self._session_poll_task = asyncio.create_task(self._session_poll_loop())
        await self._start_api_server()
        logger.info("display_service_started")

    async def _start_api_server(self) -> None:
        app = create_app(self.config, self.config_manager, self.mqtt_client, self)
        port = self.config.env.api_port
        server_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_config=None,
        )
        self._api_server = uvicorn.Server(server_config)
        self._uvicorn_task = asyncio.create_task(self._api_server.serve())
        logger.info("api_server_started", port=port)

    async def run(self) -> None:
        await self._shutdown_event.wait()
        logger.info("shutdown_requested")

    async def stop(self) -> None:
        """Stop the display service gracefully."""
        logger.info("display_service_stopping")
        if self._api_server:
            self._api_server.should_exit = True
        await _cancel_task(self._uvicorn_task)
        await self.mqtt_client.stop()
        await _cancel_task(self._render_task)
        await _cancel_task(self._sleep_poll_task)
        await _cancel_task(self._session_poll_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()
        # Blanks the panel and closes the I2C handle; a plain clear() left the
        # handle open until the process died.
        display_shutdown()
        logger.info("display_service_stopped")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _handle_mqtt_message(self, topic: str, payload: bytes) -> None:
        if topic.endswith("/audio/error") or topic.endswith("/system/service-error"):
            self.state_manager.set_error()
            return
        self.state_manager.update_audio(topic, payload)
        self._note_volume_change()

    def _note_volume_change(self) -> None:
        """Raise the volume overlay when the level or mute actually changed.

        audio/status is retained and republished for reasons that have nothing
        to do with volume, so the comparison is against the last level we saw
        rather than against the arrival of a message.
        """
        view = self.state_manager.get_volume_view()
        key = (view.clamped, view.min_volume, view.max_volume, view.muted)
        if self._last_volume_key is None:
            # The first status after a connect is the current state, not a
            # change - otherwise every restart flashes the overlay.
            self._last_volume_key = key
            return
        if key == self._last_volume_key:
            return
        self._last_volume_key = key
        self._raise_volume_hud(view)

    def _raise_volume_hud(self, view: VolumeView) -> None:
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop
            return
        self._hud_view = view
        self._hud_until = now + HUD_SECONDS
        self._wake.set()

    def _hud_deadline_active(self) -> bool:
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop
            return False
        return now < self._hud_until

    def _handle_config_reload(self) -> None:
        try:
            previous = self._display_config
            self._display_config = self.config_manager.reload_config()
            logger.info("config_reload_success")
            self._warn_overcrowded_areas(self._display_config)
            self._apply_hardware_config(previous, self._display_config)
            self._redraw_now()
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)

    @staticmethod
    def _apply_hardware_config(
        previous: DisplayServiceConfig | None,
        current: DisplayServiceConfig,
    ) -> None:
        """Bring the device in line with a freshly loaded config.

        A reload used to only redraw. So changing the I2C address in the WebUI
        kept talking to the old one, switching the display off left the last
        frame standing on the panel, and switching it on for a box that started
        with it off did nothing at all - all three until the next restart.
        """
        address_changed = previous is not None and (
            previous.i2c_bus != current.i2c_bus
            or previous.i2c_address != current.i2c_address
        )

        if address_changed and is_available():
            logger.info(
                "display_address_changed",
                bus=current.i2c_bus,
                address=current.i2c_address,
            )
            display_shutdown()

        if not current.enabled:
            if is_available():
                # Leaving the last frame up is the one outcome the user reads
                # as "the setting did not work".
                clear()
            return

        if not is_available():
            display_init(current.i2c_bus, current.i2c_address)

    def _redraw_now(self) -> None:
        """Push a frame immediately, unless the test pattern still owns the panel."""
        cfg = self._display_config
        if not is_available() or not cfg or not cfg.enabled:
            return
        if self._test_pattern_deadline_active() or self._hud_deadline_active():
            return
        areas = self._build_areas()
        if any(areas):
            show_areas(areas, font_size=cfg.font_size, font=cfg.font)

    def _test_pattern_deadline_active(self) -> bool:
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop either
            return False
        return now < self._test_pattern_until

    @staticmethod
    def _warn_overcrowded_areas(cfg: DisplayServiceConfig | None) -> None:
        if not cfg:
            return
        limits = {0: _HEADER_MAX_ITEMS, 1: _BODY_MAX_ITEMS, 2: _BODY_MAX_ITEMS}
        for area_idx, limit in limits.items():
            enabled_in_area = [
                e for e in cfg.elements if e.enabled and e.area == area_idx
            ]
            if len(enabled_in_area) > limit:
                types = [e.type for e in enabled_in_area]
                logger.warning(
                    "display_area_overcrowded",
                    area=area_idx,
                    configured=len(enabled_in_area),
                    limit=limit,
                    elements=types,
                    hint=(
                        f"Area {area_idx} has {len(enabled_in_area)} enabled "
                        f"elements but the renderer supports at most {limit}. "
                        "Items beyond the limit will be dropped at render time."
                    ),
                )

    def _build_areas(self) -> list[list[dict]]:
        """Build render areas using the _ELEMENT_RENDERERS registry (issue #26)."""
        cfg = self._display_config
        if not cfg or not cfg.enabled:
            return [[], [], []]
        enabled = [e for e in cfg.elements if e.enabled]
        if not enabled:
            return [[], [], []]

        by_area: list[list] = [[], [], []]
        for area_idx in (0, 1, 2):
            by_area[area_idx] = sorted(
                [e for e in enabled if e.area == area_idx],
                key=lambda e: e.order,
            )

        audio = self.state_manager.get_audio()
        sleep_timer = self.state_manager.get_sleep_timer()
        session = self.state_manager.get_session()

        result: list[list[dict]] = [[], [], []]
        for area_idx in (0, 1, 2):
            for el in by_area[area_idx]:
                renderer = _ELEMENT_RENDERERS.get(el.type)
                if renderer is None:
                    logger.warning("unknown_element_type", el_type=el.type)
                    continue

                item = renderer(audio, sleep_timer, session, self.state_manager)
                if item is None:
                    continue

                limit = _HEADER_MAX_ITEMS if area_idx == 0 else _BODY_MAX_ITEMS
                if len(result[area_idx]) >= limit:
                    logger.warning(
                        "display_area_item_dropped",
                        area=area_idx,
                        dropped_type=el.type,
                        limit=limit,
                    )
                    continue

                result[area_idx].append(item)

        return result

    async def _poll_backend(
        self,
        endpoint: str,
        interval: float,
        update_fn: Callable[[dict], None],
        error_event: str,
    ) -> None:
        """Generic backend polling helper (issue #24).

        The client lives for the whole loop. Building and tearing one down per
        poll was measurably expensive: httpcore runs an import lookup on every
        close, and with two loops polling every 5s that dominated this
        service's CPU time. Reusing it also keeps the connection alive.
        """
        async with httpx.AsyncClient(timeout=3.0) as client:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(interval)
                    try:
                        r = await client.get(f"{BACKEND_URL}{endpoint}")
                        if r.status_code == 200:
                            update_fn(r.json())
                    except (httpx.ConnectError, httpx.TimeoutException):
                        pass
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.debug(error_event, endpoint=endpoint, error=str(exc))

    async def _sleep_timer_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_sleep_timer(
                data.get("active", False),
                data.get("remaining_ms"),
            )

        await self._poll_backend(
            endpoint="/api/v1/audio/sleep-timer",
            interval=SLEEP_TIMER_POLL_INTERVAL,
            update_fn=_update,
            error_event="sleep_timer_poll_error",
        )

    async def _session_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_session(
                data.get("repeat_mode", "none"),
                data.get("shuffle", False),
            )

        await self._poll_backend(
            endpoint="/api/v1/audio/session",
            interval=SESSION_POLL_INTERVAL,
            update_fn=_update,
            error_event="session_poll_error",
        )

    @staticmethod
    def _render_fingerprint(areas: list[list[dict]], font_size: str, font: str) -> str:
        """Stable representation of everything that affects the rendered frame."""
        return json.dumps([areas, font_size, font], sort_keys=True, default=str)

    async def show_test_pattern(self) -> bool:
        """Show a short test pattern so the user can confirm the panel works.

        Returns False when no display is attached; the caller turns that into a
        404 rather than pretending the test ran.
        """
        if not is_available():
            return False
        cfg = self._display_config
        if not cfg or not cfg.enabled:
            return False

        # Take the lock before drawing - otherwise the render loop can slip in
        # between the draw and the lock.
        self._test_pattern_until = (
            asyncio.get_running_loop().time() + TEST_PATTERN_SECONDS
        )
        # The user asked to see the test pattern; a volume overlay left over
        # from a moment ago must not reappear on top of it when it expires.
        self._hud_until = 0.0
        self._hud_view = None
        try:
            show_lines(["Minabox", "Display OK"])
        except Exception as exc:
            self._test_pattern_until = 0.0
            logger.warning("display_test_pattern_failed", error=str(exc))
            return False
        logger.info("display_test_pattern_shown")
        return True

    async def _wait_for_work(self, timeout: float, last_draw: float) -> None:
        """Sleep until the next tick, or until something asks for a frame."""
        loop = asyncio.get_running_loop()
        if self._hud_view is not None:
            # Wake when the overlay expires rather than a whole tick later,
            # or it would sit on the panel for up to a second too long.
            timeout = min(timeout, max(0.05, self._hud_until - loop.time()))
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except TimeoutError:
            pass
        finally:
            self._wake.clear()
        # The floor applies however the wake-up came about, not just to the
        # ones a message triggered: a knob turn arrives as a burst of status
        # messages and every frame holds the I2C bus - shared with the RFID
        # reader - for 92 ms. At the normal one-second tick this costs
        # nothing, because the floor is long past by then.
        held = loop.time() - last_draw
        if held < MIN_REDRAW_INTERVAL:
            await asyncio.sleep(MIN_REDRAW_INTERVAL - held)

    async def _render_loop(self) -> None:
        last_fingerprint: str | None = None
        last_forced = 0.0
        last_draw = 0.0
        last_init_retry = 0.0
        was_available = False

        while not self._shutdown_event.is_set():
            try:
                await self._wait_for_work(RENDER_INTERVAL, last_draw)
                now = asyncio.get_running_loop().time()
                cfg = self._display_config

                if self._hud_view is not None and now >= self._hud_until:
                    # Expired. The frame underneath is pushed again by itself,
                    # because the fingerprint standing here is the overlay's
                    # and never equals the one built from the areas below.
                    #
                    # This is deliberately ahead of every other check: an
                    # overlay left standing keeps _wait_for_work() shortening
                    # its timeout to a past deadline, and a panel that is
                    # unplugged or switched off at that moment would spin the
                    # loop at 20 Hz for as long as it stayed away.
                    self._hud_view = None

                if not is_available():
                    was_available = False
                    if (
                        cfg
                        and cfg.enabled
                        and (now - last_init_retry) >= DISPLAY_INIT_RETRY_INTERVAL
                    ):
                        last_init_retry = now
                        # Quietly: the first failure was already reported at
                        # startup, and a box that simply has no panel must not
                        # write a warning every 30 seconds for years.
                        display_init(cfg.i2c_bus, cfg.i2c_address, log_failure=False)
                    continue

                if not was_available:
                    # Display (re-)appeared - the panel content is unknown, redraw.
                    last_fingerprint = None
                    was_available = True

                # Otherwise the test pattern would be overwritten by the normal
                # frame within a second and could not be read.
                if now < self._test_pattern_until:
                    last_fingerprint = None
                    continue

                if not cfg or not cfg.enabled:
                    continue

                if self._hud_view is not None:
                    fingerprint = f"hud:{self._hud_view}"
                    if fingerprint != last_fingerprint:
                        show_image(render_volume(self._hud_view))
                        last_fingerprint = fingerprint
                        last_draw = asyncio.get_running_loop().time()
                    continue

                areas = self._build_areas()
                if not any(areas):
                    continue

                fingerprint = self._render_fingerprint(areas, cfg.font_size, cfg.font)
                forced = (now - last_forced) >= FORCE_REDRAW_INTERVAL
                if fingerprint == last_fingerprint and not forced:
                    continue

                show_areas(
                    areas,
                    font_size=cfg.font_size,
                    font=cfg.font,
                )
                last_fingerprint = fingerprint
                last_draw = asyncio.get_running_loop().time()
                if forced:
                    last_forced = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("render_loop_error", error=str(exc))


async def main() -> None:
    # Logging first: the most consequential error this service can hit is an
    # unloadable config, and it used to be reported by an unconfigured logger.
    setup_structlog(os.environ.get("LOG_LEVEL", "INFO"))
    try:
        config = load_app_config()
    except Exception as exc:
        logger.error("config_load_failed", error=str(exc))
        raise
    setup_structlog(config.env.log_level)
    logger.info(
        "service_initializing",
        device_id=config.env.minabox_device_id,
        log_level=config.env.log_level,
    )
    service = DisplayService(config)
    loop = asyncio.get_running_loop()

    def signal_handler(sig: signal.Signals) -> None:
        logger.info("signal_received", signal=sig.name)
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            pass
    try:
        await service.start()
        await service.run()
    except Exception as exc:
        logger.error("service_error", error=str(exc), exc_info=True)
        raise
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception:
        logger.exception("service_crashed")
        raise
