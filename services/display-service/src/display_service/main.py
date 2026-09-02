"""Main entry point for the display service."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable
from dataclasses import replace
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
from .core.idle_animation import IdleAnimation
from .core.night import is_night
from .infrastructure import (
    MQTTClient,
    clear,
    is_available,
    set_contrast,
    set_visible,
    show_image,
    show_lines,
)
from .infrastructure import (
    init as display_init,
)
from .infrastructure import (
    shutdown as display_shutdown,
)
from .render.idle import render as render_idle
from .render.idle import strip_width as idle_strip_width
from .render.network import render_hotspot as render_net_hotspot
from .render.network import render_no_network as render_net_no_network
from .render.network import wander_offset as net_wander_offset
from .render.playing import PAUSED_SLEEP_PHASE_SECONDS, PlayingView
from .render.playing import render as render_playing
from .render.quota_over import render as render_quota_over
from .render.tag_blocked import render as render_tag_blocked
from .render.unknown_tag import render as render_unknown_tag
from .render.volume import VolumeView
from .render.volume import render as render_volume

logger = structlog.get_logger(__name__)


BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")
SLEEP_TIMER_POLL_INTERVAL = 5.0
# Repeat and shuffle change when somebody presses a button, and the panel shows
# them as a single icon. One request every 5 seconds bought a latency nobody can
# perceive at a measured 12 ms of CPU per request.
SESSION_POLL_INTERVAL = 15.0
# The network state changes on the scale of a router rebooting or a box being
# carried to another house. Polling it is only so the panel can show where to
# reach the box when the usual way is gone.
NETWORK_POLL_INTERVAL = 20.0
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
# The progress bar is redrawn when it has moved this many pixels, not on every
# tick. A full frame holds the I2C bus - shared with the RFID reader - for
# 92 ms, and a bar that advances pixel by pixel would ask for one every few
# seconds on a short track. Three pixels of a 118 px bar is a redraw roughly
# every fortieth of a track.
PROGRESS_QUANTUM_PX = 3
# How long an unknown figure stays on the panel. It reports an event, not a
# state: long enough to read, short enough that the box does not look stuck.
NOTICE_SECONDS = 4.0

# The three ways a figure can end in nothing happening. All have the same
# shape from where the child stands - something was put on the reader and the
# box stayed quiet - which is the shape a picture is actually good for.
NOTICE_UNKNOWN = "unknown_tag"
NOTICE_BLOCKED = "tag_blocked"
NOTICE_QUOTA = "quota_over"

# Only the blocked figure has anything to say about itself - it is the one the
# box actually recognises, and its name is worth putting on the panel.
_NOTICE_RENDERERS = {
    NOTICE_UNKNOWN: lambda _detail: render_unknown_tag(),
    NOTICE_BLOCKED: render_tag_blocked,
    NOTICE_QUOTA: lambda _detail: render_quota_over(),
}

# Which screen owns the panel, most insistent first. Written down rather than
# left implicit in a chain of early returns, because "what beats what" is the
# only thing that decides what a person actually sees.
SCREEN_TEST = "test_pattern"
SCREEN_HUD = "volume"
SCREEN_NOTICE = "notice"
SCREEN_PLAYING = "playing"
SCREEN_NETWORK = "network"
SCREEN_IDLE = "idle"



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
        self._network_poll_task: asyncio.Task | None = None
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
        self._last_play_state: str | None = None
        self._notice: tuple[str, str] | None = None
        self._notice_until: float = 0.0
        # Built on first use, because it needs a clock that only exists once
        # the loop is running.
        self._idle_animation: IdleAnimation | None = None
        # What the panel is currently set to, so the two commands that change
        # it are only sent when they would change something.
        self._contrast: int | None = None
        self._panel_visible = True
        # A track change has to pull the session poll forward: the title lives
        # in that response, and waiting out the interval would leave the
        # previous title on the panel.
        self._session_refresh = asyncio.Event()
        self._last_track_id: Any = None
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
        self._network_poll_task = asyncio.create_task(self._network_poll_loop())
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
        await _cancel_task(self._network_poll_task)
        await _cancel_task(self._mqtt_task)
        await self.mqtt_client.disconnect()
        # Blanks the panel and closes the I2C handle; a plain clear() left the
        # handle open until the process died.
        display_shutdown()
        logger.info("display_service_stopped")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _handle_mqtt_message(self, topic: str, payload: bytes) -> None:
        if topic.endswith("/rfid/unknown-tag"):
            self._raise_notice(NOTICE_UNKNOWN)
            return
        if topic.endswith("/rfid/tag-blocked"):
            self._raise_notice(NOTICE_BLOCKED, self._tag_name(payload))
            return
        if topic.endswith("/led/usage-denied"):
            self._raise_notice(NOTICE_QUOTA)
            return
        if topic.endswith("/rfid/tag-scanned") or topic.endswith("/rfid/tag-removed"):
            self._wave_hello()
            return
        if topic.endswith("/audio/error") or topic.endswith("/system/service-error"):
            self.state_manager.set_error()
            return
        self.state_manager.update_audio(topic, payload)
        self._note_volume_change()
        self._note_track_change()

    @staticmethod
    def _tag_name(payload: bytes) -> str:
        """The figure's name, if the message carries one worth showing."""
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            return ""
        return str(data.get("name") or "") if isinstance(data, dict) else ""

    def _raise_notice(self, kind: str, detail: str = "") -> None:
        """Something was put on the reader and the box is not going to play it."""
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop
            return
        self._notice = (kind, detail)
        self._notice_until = now + NOTICE_SECONDS
        self._wake.set()
        logger.info("notice_shown", kind=kind)

    def _wave_hello(self) -> None:
        """A figure arrived or left, and Knuffel has something to say about it.

        On arrival the greeting is usually cut short by playback taking the
        panel a few hundred milliseconds later; on removal it plays out, which
        is where it is actually seen.
        """
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop
            return
        self._idle(now).wave_now(now)
        self._wake.set()

    def _note_volume_change(self) -> None:
        """Raise the volume overlay when the level or mute actually changed.

        audio/status is retained and republished for reasons that have nothing
        to do with volume, so the comparison is against the last level we saw
        rather than against the arrival of a message.
        """
        audio = self.state_manager.get_audio()
        raw = audio["volume"]
        if not audio["min_volume"] <= raw <= audio["max_volume"]:
            # The audio service clamps every write into that range, so the box
            # cannot be at a level outside it. What arrives instead is libVLC
            # saying "ask me later" - 0 in the moment after play(), which used
            # to raise a full-screen overlay for putting a figure on the
            # reader. Fixed at the source too; this keeps the panel quiet if
            # anything like it comes back.
            logger.debug("volume_out_of_range_ignored", volume=raw)
            return

        view = self.state_manager.get_volume_view()
        key = (view.clamped, view.min_volume, view.max_volume, view.muted)
        state = audio.get("state")
        previous_state, self._last_play_state = self._last_play_state, state

        if self._last_volume_key is None:
            # The first status after a connect is the current state, not a
            # change - otherwise every restart flashes the overlay.
            self._last_volume_key = key
            return
        if key == self._last_volume_key:
            return
        self._last_volume_key = key

        if previous_state is not None and state != previous_state:
            # The overlay means "somebody just turned the knob". A message that
            # also changes the play state is reporting a playback event, and a
            # volume that moves with it is far more likely to be an artefact
            # than a gesture - which is exactly what it was: libVLC reports -1
            # once stop() releases the media, and that used to be published as
            # a drop to the quietest setting.
            logger.debug("volume_change_with_state_change_ignored", state=state)
            return
        self._raise_volume_hud(view)

    def _note_track_change(self) -> None:
        """Ask for a fresh session when the track changed, and redraw."""
        track_id = self.state_manager.get_audio().get("track_id")
        if track_id != self._last_track_id:
            self._last_track_id = track_id
            self._session_refresh.set()
        # Position, length and play state all arrive here, and all three are on
        # the playing screen.
        self._wake.set()

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
        """Ask the render loop for a frame now rather than at the next tick.

        It used to draw the widget grid here itself. That grid is no longer
        reachable - every state of the box now has a screen of its own - and
        drawing from two places would race the loop for the panel anyway. The
        loop owns the glass; this only wakes it.
        """
        self._wake.set()

    def _test_pattern_deadline_active(self) -> bool:
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:  # pragma: no cover - no loop, so no render loop either
            return False
        return now < self._test_pattern_until

    async def _poll_backend(
        self,
        endpoint: str,
        interval: float,
        update_fn: Callable[[dict], None],
        error_event: str,
        wake: asyncio.Event | None = None,
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
                    if wake is None:
                        await asyncio.sleep(interval)
                    else:
                        # Fifteen seconds is fine for repeat and shuffle, but
                        # not for the title: a new track would keep the old one
                        # on the panel for most of a minute.
                        try:
                            await asyncio.wait_for(wake.wait(), interval)
                        except TimeoutError:
                            pass
                        finally:
                            wake.clear()
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

    @staticmethod
    def _current_title(data: dict) -> str:
        """Title of the track marked current in the session queue."""
        for entry in data.get("queue") or []:
            if isinstance(entry, dict) and entry.get("is_current"):
                return str(entry.get("title") or "")
        return ""

    async def _session_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_session(
                data.get("repeat_mode", "none"),
                data.get("shuffle", False),
                self._current_title(data),
            )
            self._wake.set()

        await self._poll_backend(
            endpoint="/api/v1/audio/session",
            interval=SESSION_POLL_INTERVAL,
            update_fn=_update,
            error_event="session_poll_error",
            wake=self._session_refresh,
        )

    async def _network_poll_loop(self) -> None:
        def _update(data: dict) -> None:
            self.state_manager.update_network(data)
            # Switch to (or away from) the network screen without waiting out
            # the render tick.
            self._wake.set()

        await self._poll_backend(
            endpoint="/api/v1/system/network-status",
            interval=NETWORK_POLL_INTERVAL,
            update_fn=_update,
            error_event="network_poll_error",
        )

    @staticmethod
    def _playing_fingerprint(view: PlayingView) -> str:
        """Everything visible on the playing screen, and nothing else.

        The remaining time is a live number, so fingerprinting the view itself
        would redraw on every tick. What is actually on the panel is the text -
        which changes once a minute - and the bar, quantised to the pixel step
        it is drawn in.
        """
        # The active screen shows no text any more - only Knuffel's position
        # and whether he is walking or waving. Paused still animates its Zs, so
        # their phase is what is visible there.
        return "play:" + json.dumps(
            [
                view.title,
                view.paused,
                view.sleep_phase if view.paused else None,
                view.muted,
                round(view.fraction * 118 / PROGRESS_QUANTUM_PX),
                view.arriving and not view.paused,
            ],
            sort_keys=True,
            default=str,
        )

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

    def _current_screen(self, now: float) -> str:
        """Which screen owns the panel right now.

        One place, in order, rather than a chain of early returns: the test
        pattern was asked for and must not be stolen; the volume overlay
        reports a gesture just made; an unknown figure reports an event; after
        that it is simply whether something is playing.
        """
        if now < self._test_pattern_until:
            return SCREEN_TEST
        if self._hud_view is not None:
            return SCREEN_HUD
        if self._notice is not None and now < self._notice_until:
            return SCREEN_NOTICE
        if self.state_manager.is_playing():
            return SCREEN_PLAYING
        if self.state_manager.wants_network_screen():
            return SCREEN_NETWORK
        return SCREEN_IDLE

    def _apply_brightness(self, screen: str) -> bool:
        """Set contrast and visibility for the time of day. Returns "draw?".

        Off at night applies to the idle screen alone. Anything the box is
        actually doing - something playing, a hand on the knob, a figure on the
        reader - takes the panel back, because a dark panel in those moments
        looks like a broken box rather than a considerate one.
        """
        cfg = self._display_config
        if cfg is None:
            return True
        brightness = cfg.brightness
        night = is_night(
            datetime.now().time(), brightness.night_from, brightness.night_to
        )

        level = brightness.night if night else brightness.day
        if level != self._contrast:
            self._contrast = level
            set_contrast(level)
            logger.info("display_contrast_set", level=level, night=night)

        if self._idle_animation is not None:
            self._idle_animation.set_asleep(night)

        # The network screen blanks at night with the idle screen: if nobody is
        # awake to read the address, an hour-long lit panel is only burn-in. It
        # comes back in the morning, or the moment anything else takes over.
        night_off_screen = screen in (SCREEN_IDLE, SCREEN_NETWORK)
        visible = not (night and brightness.off_at_night and night_off_screen)
        if visible != self._panel_visible:
            self._panel_visible = visible
            set_visible(visible)
            logger.info("display_visibility_set", visible=visible)
        return visible

    def _idle_marks(self) -> tuple[str, ...]:
        """What is true but not worth a screen of its own.

        Both of these used to sit in the widget grid and went with it. An error
        is worth a corner mark and not a screen: the flag expires by itself,
        because nothing tells this service whether the thing is still wrong.
        """
        showing = []
        if self.state_manager.has_error():
            showing.append("error")
        if self.state_manager.get_sleep_timer()["active"]:
            showing.append("sleep_timer")
        if self.state_manager.get_network().get("mode") == "local_only":
            # Connected to the LAN but no way out. Not a screen - the box works
            # fine for local playback - but worth a corner mark.
            showing.append("no_internet")
        return tuple(showing)

    def _idle(self, now: float) -> IdleAnimation:
        if self._idle_animation is None:
            self._idle_animation = IdleAnimation(now=now)
        return self._idle_animation

    async def _wait_for_work(self, timeout: float, last_draw: float) -> None:
        """Sleep until the next tick, a deadline, or something asking to draw."""
        loop = asyncio.get_running_loop()
        now = loop.time()
        screen = self._current_screen(now)

        deadline = None
        if screen == SCREEN_HUD:
            deadline = self._hud_until
        elif screen == SCREEN_NOTICE:
            deadline = self._notice_until
        elif screen == SCREEN_IDLE:
            # Knuffel says when he next wants drawing - a breath, a blink, a
            # step. Between those there is nothing to do and the loop sleeps.
            deadline = self._idle(now).next_due()
        if deadline is not None:
            # Wake when it falls due rather than a whole tick later, and never
            # busy-spin on one that has already passed.
            timeout = min(timeout, max(0.02, deadline - now))

        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except TimeoutError:
            pass
        finally:
            self._wake.clear()

        # The floor applies however the wake-up came about: a knob turn arrives
        # as a burst of status messages, and every frame holds the I2C bus that
        # the RFID reader shares. At the normal one-second tick it costs
        # nothing, because the floor is long past by then.
        held = loop.time() - last_draw
        if held < MIN_REDRAW_INTERVAL:
            await asyncio.sleep(MIN_REDRAW_INTERVAL - held)

    def _screen_frame(self, screen: str, now: float) -> tuple[str, Any] | None:
        """Fingerprint and image for *screen*, or None if it draws nothing.

        The fingerprint is what is actually visible, never the live values
        behind it: a remaining time counted locally would otherwise ask for a
        frame on every tick.
        """
        if screen == SCREEN_HUD:
            view = self._hud_view
            # What the panel actually shows: mute, or one of five singing
            # levels. Most knob clicks on a wide range land in the same level
            # and change nothing here, so they cost no frame on the bus the
            # RFID reader shares - even though each still flashes the overlay.
            visible = "muted" if view.muted else f"L{view.level}"
            return f"hud:{visible}", render_volume(view)
        if screen == SCREEN_NOTICE:
            kind, detail = self._notice
            return f"notice:{kind}:{detail}", _NOTICE_RENDERERS[kind](detail)
        if screen == SCREEN_PLAYING:
            view = self.state_manager.get_playing_view()
            if view.paused:
                # Derived from the clock rather than counted up, so the rhythm
                # does not depend on how often this happens to be called.
                view = replace(
                    view,
                    sleep_phase=int(now / PAUSED_SLEEP_PHASE_SECONDS),
                )
            return self._playing_fingerprint(view), render_playing(view)
        if screen == SCREEN_NETWORK:
            net = self.state_manager.get_network()
            offset = net_wander_offset(now)
            if net.get("mode") == "hotspot":
                hs = net.get("hotspot") or {}
                ssid = hs.get("ssid") or net.get("ssid") or "Minabox-Setup"
                password = hs.get("password")
                url = net.get("manage_url")
                return (
                    f"net:hotspot:{ssid}:{password}:{url}:{offset}",
                    render_net_hotspot(ssid, password, url, offset=offset),
                )
            return f"net:no_network:{offset}", render_net_no_network(offset=offset)
        if screen == SCREEN_IDLE:
            animation = self._idle(now)
            showing = self._idle_marks()
            animation.set_reserved(idle_strip_width(showing), now)
            animation.advance(now)
            pose = animation.pose()
            return (
                f"idle:{pose.x},{pose.y},{pose.mood},{showing}",
                render_idle(pose, showing),
            )
        return None

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
                    # Expired. Dropped here, ahead of every other check, so a
                    # panel that is unplugged at this moment cannot leave the
                    # loop waking against a deadline in the past.
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

                if not cfg or not cfg.enabled:
                    continue

                screen = self._current_screen(now)
                if not self._apply_brightness(screen):
                    # Panel off for the night, and nothing is going on. Whatever
                    # was last drawn is still in its buffer for when it wakes.
                    continue
                if screen == SCREEN_TEST:
                    # It was asked for and is drawn elsewhere; leave it alone.
                    last_fingerprint = None
                    continue

                drawn = self._screen_frame(screen, now)
                if drawn is None:
                    continue
                fingerprint, image = drawn

                forced = (now - last_forced) >= FORCE_REDRAW_INTERVAL
                if fingerprint == last_fingerprint and not forced:
                    continue

                show_image(image)
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
