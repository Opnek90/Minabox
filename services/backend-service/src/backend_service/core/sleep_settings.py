"""Sleep timer and bedtime fade, read from general_settings.json."""

from __future__ import annotations

from backend_service.core.general_settings import read_general_settings

DEFAULT_SLEEP_TIMER_MINUTES = 30
DEFAULT_FADE_DURATION_MINUTES = 15
DEFAULT_FADE_INTERVAL_SECONDS = 30
DEFAULT_FADE_STEP_PERCENT = 2.0


def read_sleep_timer_minutes() -> int:
    """How long the physical sleep-timer button switches on for."""
    try:
        raw = read_general_settings().get(
            "sleep_timer_minutes", DEFAULT_SLEEP_TIMER_MINUTES
        )
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_SLEEP_TIMER_MINUTES


def read_bedtime_fade_settings() -> tuple[bool, int, int, float]:
    """Bedtime fade parameters.

    Returns:
        (enabled, duration_min, interval_sec, step_pct)
    """
    data = read_general_settings()
    try:
        return (
            bool(data.get("bedtime_fade_enabled", False)),
            max(1, int(data.get("bedtime_fade_duration_minutes", DEFAULT_FADE_DURATION_MINUTES))),
            max(5, int(data.get("bedtime_fade_interval_seconds", DEFAULT_FADE_INTERVAL_SECONDS))),
            max(0.5, min(50.0, float(data.get("bedtime_fade_step_percent", DEFAULT_FADE_STEP_PERCENT)))),
        )
    except (TypeError, ValueError):
        return (
            False,
            DEFAULT_FADE_DURATION_MINUTES,
            DEFAULT_FADE_INTERVAL_SECONDS,
            DEFAULT_FADE_STEP_PERCENT,
        )


__all__ = [
    "read_bedtime_fade_settings",
    "read_sleep_timer_minutes",
]
