"""Active system alerts for the notice bar in the WebUI.

The temperature logger used to keep a single alert in a module variable. That
works while there is only one kind - as soon as a second appears, one displaces
the other: a passing temperature warning would overwrite the standing notice
about an incompatible database, and once the box cooled down there would be
none left at all.

So alerts live here keyed by code, and ``get_current_alert`` returns the most
severe one. The bar still shows a single alert - but the right one.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Higher wins: this decides which alert the bar shows.
_SEVERITY = {"info": 0, "warning": 1, "error": 2}

_alerts: dict[str, dict[str, Any]] = {}


def set_alert(code: str, level: str, message: str) -> dict[str, Any]:
    """Raise or update an alert. `message` is an i18n key, not display text."""
    alert = {"code": code, "level": level, "message": message}
    _alerts[code] = alert
    logger.info("system_alert_set", code=code, level=level)
    return alert


def clear_alert(code: str) -> bool:
    """Withdraw an alert. True when there was one."""
    if _alerts.pop(code, None) is not None:
        logger.info("system_alert_cleared", code=code)
        return True
    return False


def get_current_alert() -> dict[str, Any] | None:
    """The most severe active alert, or None."""
    if not _alerts:
        return None
    return max(_alerts.values(), key=lambda a: _SEVERITY.get(a.get("level", "info"), 0))


def get_all_alerts() -> list[dict[str, Any]]:
    """Every active alert, most severe first."""
    return sorted(
        _alerts.values(),
        key=lambda a: _SEVERITY.get(a.get("level", "info"), 0),
        reverse=True,
    )


def clear_all() -> None:
    """Drop everything - for tests."""
    _alerts.clear()
