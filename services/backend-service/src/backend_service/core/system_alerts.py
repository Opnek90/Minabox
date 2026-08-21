"""Aktive Systemwarnungen fuer den Hinweisbalken der Oberflaeche.

Vorher hielt der Temperatur-Logger eine einzige Warnung in einer
Modulvariablen. Das reicht, solange es nur eine Sorte gibt - sobald eine
zweite dazukommt, verdraengt die eine die andere: eine voruebergehende
Temperaturwarnung haette die dauerhafte Meldung ueber eine unpassende
Datenbank ueberschrieben, und beim Abkuehlen waere gar keine mehr uebrig.

Deshalb liegen die Warnungen hier nach Kennung getrennt, und ``get_current_alert``
zeigt die schwerwiegendste. Der Balken zeigt weiterhin nur eine - aber die
richtige.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Je hoeher, desto wichtiger - entscheidet, welche Warnung der Balken zeigt.
_SEVERITY = {"info": 0, "warning": 1, "error": 2}

_alerts: dict[str, dict[str, Any]] = {}


def set_alert(code: str, level: str, message: str) -> dict[str, Any]:
    """Eine Warnung setzen oder aktualisieren. `message` ist ein i18n-Schluessel."""
    alert = {"code": code, "level": level, "message": message}
    _alerts[code] = alert
    logger.info("system_alert_set", code=code, level=level)
    return alert


def clear_alert(code: str) -> bool:
    """Eine Warnung zuruecknehmen. True, wenn es sie gab."""
    if _alerts.pop(code, None) is not None:
        logger.info("system_alert_cleared", code=code)
        return True
    return False


def get_current_alert() -> dict[str, Any] | None:
    """Die schwerwiegendste aktive Warnung, oder None."""
    if not _alerts:
        return None
    return max(_alerts.values(), key=lambda a: _SEVERITY.get(a.get("level", "info"), 0))


def get_all_alerts() -> list[dict[str, Any]]:
    """Alle aktiven Warnungen, schwerwiegendste zuerst."""
    return sorted(
        _alerts.values(),
        key=lambda a: _SEVERITY.get(a.get("level", "info"), 0),
        reverse=True,
    )


def clear_all() -> None:
    """Alles zuruecksetzen - fuer Tests."""
    _alerts.clear()
