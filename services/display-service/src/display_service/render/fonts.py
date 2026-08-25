"""Font lookup for the screen renderers.

The image installs ``fonts-dejavu-core`` and nothing else, so exactly four
faces exist: Sans and Serif, each regular and bold. Anything outside that list
would silently fall back to PIL's 11 px bitmap default, which is why the
renderers ask for a weight rather than a font name.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REGULAR = "regular"
BOLD = "bold"

# Tried in order; the second path covers distributions that drop the
# "truetype" level (Arch, some minimal images).
_FACES: dict[str, tuple[str, ...]] = {
    REGULAR: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ),
    BOLD: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ),
}

_cache: dict[tuple[str, int], Any] = {}
_warned: set[str] = set()


def get(weight: str, size: int) -> Any:
    """Return a PIL font for *weight* at *size* pixels.

    Falls back to the bitmap default rather than raising: a HUD in the wrong
    font is still readable, a traceback in the render loop is not.
    """
    key = (weight, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    from PIL import ImageFont

    for path in _FACES.get(weight, ()):
        if not os.path.isfile(path):
            continue
        try:
            font = ImageFont.truetype(path, size)
        except Exception as exc:
            logger.warning("font_load_failed", path=path, error=str(exc))
            continue
        _cache[key] = font
        return font

    if weight not in _warned:
        _warned.add(weight)
        logger.warning(
            "font_missing",
            weight=weight,
            searched=list(_FACES.get(weight, ())),
            hint="Install fonts-dejavu-core; falling back to the bitmap default.",
        )
    font = ImageFont.load_default()
    _cache[key] = font
    return font


def reset_cache() -> None:
    """Drop cached faces. Only tests need this."""
    _cache.clear()
    _warned.clear()
