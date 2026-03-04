"""Timer and Sleep MQTT handlers."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import structlog

from backend_service.core.sleep_settings import (
    read_bedtime_fade_settings,
    read_sleep_timer_minutes,
)

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)


class TimerHandler:
    def __init__(self, dispatcher: "MQTTHandlers") -> None:
        self.dispatcher = dispatcher
        self.sleep_timer_task: asyncio.Task | None = None
        self.sleep_timer_start_time: float = 0.0
        self.sleep_timer_duration_ms: int = 0
        self.bedtime_fade_task: asyncio.Task | None = None

    async def _trigger_daily_limit_fade(self) -> None:
        self._cancel_bedtime_fade()
        enabled, duration_min, interval_sec, step_pct = read_bedtime_fade_settings()
        if not enabled:
            self.dispatcher.mark_deliberate_stop()
            self.dispatcher.playback_intent_active = False
            await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
            return
        try:
            vol = self.dispatcher.audio_status_cache.get("volume")
            if vol is not None and isinstance(vol, (int, float)):
                initial_volume = max(0, min(100, int(vol)))
            else:
                initial_volume = 50
        except (TypeError, ValueError):
            initial_volume = 50
        self.bedtime_fade_task = asyncio.create_task(
            self._bedtime_fade_coroutine(initial_volume, duration_min, interval_sec, step_pct)
        )
        try:
            await self.bedtime_fade_task
        except asyncio.CancelledError:
            pass
        finally:
            self.bedtime_fade_task = None
        self.dispatcher.mark_deliberate_stop()
        self.dispatcher.playback_intent_active = False
        await self.dispatcher.mqtt_client.publish_audio_command("stop", {})

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
            try:
                vol = self.dispatcher.audio_status_cache.get("volume")
                if vol is not None and isinstance(vol, (int, float)):
                    initial_volume = max(0, min(100, int(vol)))
                else:
                    initial_volume = 50
            except (TypeError, ValueError):
                initial_volume = 50
            self.bedtime_fade_task = asyncio.create_task(
                self._bedtime_fade_coroutine(initial_volume, duration_min, interval_sec, step_pct)
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

    async def _bedtime_fade_coroutine(
        self, initial_volume: int, duration_minutes: int, interval_seconds: int, step_percent: float
    ) -> None:
        current = max(0, initial_volume)
        steps_total = max(1, int(duration_minutes * 60 / interval_seconds))
        step = max(0, min(100, int(step_percent)))
        try:
            for _ in range(steps_total):
                await asyncio.sleep(interval_seconds)
                if self.sleep_timer_task is None or self.sleep_timer_task.done():
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
            self.sleep_timer_task = None
            if self.dispatcher.websocket_manager:
                await self.dispatcher.websocket_manager.broadcast({
                    "type": "sleep_timer_status",
                    "data": {"active": False, "remaining_ms": None},
                })
