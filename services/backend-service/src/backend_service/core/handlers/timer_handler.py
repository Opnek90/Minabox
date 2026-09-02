"""Timer and Sleep MQTT handlers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

import backend_service.core.db_manager as _db_module
from backend_service.core import announcements
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.session_manager import session_manager
from backend_service.core.sleep_settings import (
    read_bedtime_fade_settings,
    read_sleep_timer_minutes,
)
from backend_service.core.usage_limits import (
    minutes_until_usage_window_ends,
    read_allowed_usage_times,
    read_daily_limit_settings,
)

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)


class TimerHandler:
    def __init__(self, dispatcher: MQTTHandlers) -> None:
        self.dispatcher = dispatcher
        self.sleep_timer_task: asyncio.Task | None = None
        self.sleep_timer_start_time: float = 0.0
        self.sleep_timer_duration_ms: int = 0
        self.bedtime_fade_task: asyncio.Task | None = None
        self.loop_guard_task: asyncio.Task | None = None
        self.limit_warning_task: asyncio.Task | None = None
        #: Volume before the running fade started, restored once it is over.
        self.volume_before_fade: int | None = None

    # -- Loop guard ---------------------------------------------------------
    #
    # Kicks in once a session starts repeating itself. Without it a card left
    # on the reader keeps the box playing indefinitely. Deliberately a timer
    # rather than a check at the track boundary: a long audiobook on repeat
    # would otherwise overshoot the limit by its own length.

    def cancel_loop_guard(self) -> None:
        """Stop the running loop guard, if any."""
        task = self.loop_guard_task
        self.loop_guard_task = None
        if task and not task.done():
            task.cancel()

    def start_loop_guard(self, minutes: int, session: Any) -> None:
        """Fade out and stop after `minutes` of continuous repetition."""
        self.cancel_loop_guard()
        if minutes <= 0:
            return
        self.loop_guard_task = asyncio.create_task(
            self._loop_guard_coroutine(minutes, session)
        )
        logger.info("loop_guard_started", minutes=minutes)

    async def _loop_guard_coroutine(self, minutes: int, session: Any) -> None:
        try:
            await asyncio.sleep(minutes * 60)
        except asyncio.CancelledError:
            logger.debug("loop_guard_cancelled")
            return
        # Clear the handle before stopping: fade_out_and_stop marks a deliberate
        # stop, which cancels the loop guard -- and that must not cancel us.
        self.loop_guard_task = None
        if session_manager.session is not session:
            logger.debug("loop_guard_skipped_session_changed")
            return
        if session.repeat_mode != "all":
            # Repeat was switched off at the player in the meantime; there is
            # no runaway loop left to cut short.
            logger.debug("loop_guard_skipped_repeat_off")
            return
        if not self.dispatcher.playback_intent_active:
            logger.debug("loop_guard_skipped_not_playing")
            return
        logger.info("loop_guard_fired", minutes=minutes)
        await self.fade_out_and_stop("loop_guard")

    # -- Spoken warning before the listening time is over -------------------
    #
    # The limits themselves are enforced elsewhere and need no timer: the daily
    # cap is checked when a card is scanned and again at every track boundary,
    # and a window that has closed refuses the next card. A *warning* has no
    # such moment to hang off - it has to arrive while the music is still
    # playing, which is what this timer is for. Without it the box simply goes
    # quiet mid-story, which is the part that upsets a four-year-old, not the
    # limit.

    def cancel_limit_warning(self) -> None:
        """Drop a pending warning - playback ended, or the numbers moved."""
        task = self.limit_warning_task
        self.limit_warning_task = None
        if task and not task.done():
            task.cancel()

    def minutes_of_listening_left(self, now: datetime) -> int | None:
        """Minutes until this box stops on its own, or None when nothing will.

        The earlier of the two limits wins: a daily cap with 40 minutes left
        does not matter when the allowed window closes in five.
        """
        remaining: list[int] = []

        daily_enabled, daily_minutes = read_daily_limit_settings()
        if daily_enabled and _db_module.db_manager:
            session = _db_module.db_manager.get_session()
            try:
                listened = get_today_listened_minutes(session)
            finally:
                session.close()
            remaining.append(max(0, daily_minutes - listened))

        window = minutes_until_usage_window_ends(now, read_allowed_usage_times())
        if window is not None:
            remaining.append(window)

        return min(remaining) if remaining else None

    def start_limit_warning(self) -> None:
        """Schedule the warning for this listening session, if one is due."""
        self.cancel_limit_warning()
        settings = announcements.read_settings()
        if not settings.allows("limit_warning") or settings.limit_warning_minutes <= 0:
            return

        left = self.minutes_of_listening_left(datetime.now())
        if left is None:
            return
        warn_at = settings.limit_warning_minutes
        if left <= warn_at:
            # Already inside the warning window - and past it is not a warning
            # any more, it is the limit doing its own job.
            if left <= 0:
                return
            delay_sec, minutes = 0.0, left
        else:
            delay_sec, minutes = (left - warn_at) * 60.0, warn_at

        self.limit_warning_task = asyncio.create_task(
            self._limit_warning_coroutine(delay_sec, minutes)
        )
        logger.info("limit_warning_scheduled", in_minutes=left - minutes)

    async def _limit_warning_coroutine(self, delay_sec: float, minutes: int) -> None:
        try:
            await asyncio.sleep(delay_sec)
        except asyncio.CancelledError:
            logger.debug("limit_warning_cancelled")
            return
        self.limit_warning_task = None
        if not self.dispatcher.playback_intent_active:
            # Stopped in the meantime by hand. Nothing is about to be taken
            # away, so there is nothing to warn about.
            logger.debug("limit_warning_skipped_not_playing")
            return
        await announcements.announce(
            self.dispatcher.mqtt_client, "limit_warning", minutes=minutes
        )

    async def _restore_volume(self) -> None:
        """Put the volume back after a fade.

        A fade ends at (or near) zero. Without this the box stays mute after
        every sleep timer, daily limit or loop guard -- and the next morning it
        looks broken rather than quiet.
        """
        volume = self.volume_before_fade
        self.volume_before_fade = None
        if not volume:
            return
        await self.dispatcher.mqtt_client.publish_audio_command(
            "set-volume", {"volume": volume}
        )
        logger.info("volume_restored_after_fade", volume=volume)

    def _current_volume(self) -> int:
        """Volume to start a fade from; 50 when the audio status is unknown."""
        try:
            vol = self.dispatcher.audio_status_cache.get("volume")
            if isinstance(vol, (int, float)):
                return max(0, min(100, int(vol)))
        except (TypeError, ValueError):
            pass
        return 50

    async def fade_out_and_stop(self, reason: str) -> None:
        """Fade the volume down and then stop playback.

        Used wherever the box ends playback on its own (daily limit reached,
        loop guard tripped). With the bedtime fade switched off this is a plain
        stop, same as before.
        """
        self._cancel_bedtime_fade()
        self.cancel_limit_warning()
        if reason == "daily_limit":
            # Said before the fade, not after the silence: the point is that
            # the music stopping was a decision, not a fault. The loop guard
            # gets no phrase - "that is it for today" would be a lie, the box
            # only cut a card that had been repeating for hours.
            await announcements.announce(
                self.dispatcher.mqtt_client, "limit_reached"
            )
        enabled, duration_min, interval_sec, step_pct = read_bedtime_fade_settings()
        if enabled:
            self.volume_before_fade = self._current_volume()
            task = asyncio.create_task(
                self._bedtime_fade_coroutine(
                    self.volume_before_fade,
                    duration_min,
                    interval_sec,
                    step_pct,
                    # The content can run out while we are still fading -- the
                    # track boundary then stops the box on its own. Without this
                    # the fade would keep turning the volume down afterwards.
                    should_continue=lambda: self.dispatcher.playback_intent_active,
                )
            )
            self.bedtime_fade_task = task
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                if self.bedtime_fade_task is task:
                    self.bedtime_fade_task = None
        self.dispatcher.mark_deliberate_stop()
        self.dispatcher.playback_intent_active = False
        await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
        await self._restore_volume()
        logger.info("faded_out_and_stopped", reason=reason, faded=enabled)

    async def _trigger_daily_limit_fade(self) -> None:
        await self.fade_out_and_stop("daily_limit")

    def get_sleep_timer_status(self) -> dict[str, Any]:
        if self.sleep_timer_task and not self.sleep_timer_task.done():
            elapsed_ms = int((time.time() - self.sleep_timer_start_time) * 1000)
            remaining_ms = max(0, self.sleep_timer_duration_ms - elapsed_ms)
            return {"active": True, "remaining_ms": remaining_ms}
        return {"active": False, "remaining_ms": None}

    def _cancel_bedtime_fade(self) -> None:
        if self.bedtime_fade_task and not self.bedtime_fade_task.done():
            self.bedtime_fade_task.cancel()
            self.bedtime_fade_task = None

    async def start_sleep_timer(self, minutes: int) -> None:
        if self.sleep_timer_task and not self.sleep_timer_task.done():
            self.sleep_timer_task.cancel()
            try:
                await self.sleep_timer_task
            except asyncio.CancelledError:
                pass
        self._cancel_bedtime_fade()
        self.sleep_timer_task = asyncio.create_task(self._sleep_timer_coroutine(minutes))
        enabled, duration_min, interval_sec, step_pct = read_bedtime_fade_settings()
        if enabled:
            self.volume_before_fade = self._current_volume()
            self.bedtime_fade_task = asyncio.create_task(
                self._bedtime_fade_coroutine(
                    self.volume_before_fade,
                    duration_min,
                    interval_sec,
                    step_pct,
                    should_continue=self._sleep_timer_running,
                )
            )

    async def cancel_sleep_timer(self) -> None:
        self._cancel_bedtime_fade()
        if self.sleep_timer_task and not self.sleep_timer_task.done():
            self.sleep_timer_task.cancel()
            try:
                await self.sleep_timer_task
            except asyncio.CancelledError:
                pass

    async def _handle_sleep_timer_toggle(self) -> None:
        if self.sleep_timer_task and not self.sleep_timer_task.done():
            await self.cancel_sleep_timer()
        else:
            minutes = read_sleep_timer_minutes()
            await self.start_sleep_timer(minutes)

    def _sleep_timer_running(self) -> bool:
        return self.sleep_timer_task is not None and not self.sleep_timer_task.done()

    async def _bedtime_fade_coroutine(
        self,
        initial_volume: int,
        duration_minutes: int,
        interval_seconds: int,
        step_percent: float,
        should_continue: Callable[[], bool] | None = None,
    ) -> None:
        """Step the volume down over `duration_minutes`.

        `should_continue` aborts the fade when the reason for it disappears --
        the sleep-timer path passes its own timer state. Without it the fade
        runs to the end; callers that await it (`fade_out_and_stop`) have no
        separate timer to key off, and checking the sleep timer there would end
        the fade before it ever changed the volume.
        """
        current = max(0, initial_volume)
        steps_total = max(1, int(duration_minutes * 60 / interval_seconds))
        step = max(0, min(100, int(step_percent)))
        try:
            for _ in range(steps_total):
                await asyncio.sleep(interval_seconds)
                if should_continue is not None and not should_continue():
                    return
                current = max(0, current - step)
                await self.dispatcher.mqtt_client.publish_audio_command("set-volume", {"volume": current})
                if current <= 0:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self.bedtime_fade_task = None

    async def _sleep_timer_coroutine(self, minutes: int) -> None:
        self.sleep_timer_start_time = time.time()
        self.sleep_timer_duration_ms = minutes * 60_000
        logger.info("sleep_timer_started", minutes=minutes)

        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast({
                "type": "sleep_timer_status",
                "data": {"active": True, "remaining_ms": self.sleep_timer_duration_ms},
            })
        try:
            await asyncio.sleep(minutes * 60)
            self.dispatcher.mark_deliberate_stop()
            self.dispatcher.playback_intent_active = False
            await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
            logger.info("sleep_timer_fired", minutes=minutes)
        except asyncio.CancelledError:
            logger.info("sleep_timer_cancelled")
        finally:
            self._cancel_bedtime_fade()
            await self._restore_volume()
            self.sleep_timer_task = None
            if self.dispatcher.websocket_manager:
                await self.dispatcher.websocket_manager.broadcast({
                    "type": "sleep_timer_status",
                    "data": {"active": False, "remaining_ms": None},
                })
