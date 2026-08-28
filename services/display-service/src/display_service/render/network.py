"""The screen for "you cannot reach this box the usual way right now".

Shown in two situations, and only these two:

* the fallback hotspot is up - the box lost its Wi-Fi and opened its own
  network so it stays reachable. Then the panel is the only place the SSID,
  the password and the address are written down, so all three go on it.
* there is no network at all - a short line, because there is nothing to act
  on yet; the host-helper brings the hotspot up on its own after a minute.

This screen has text where the rest of the display has almost none. That is
deliberate: an address is not a thing a picture can convey, and the person
reading it is an adult trying to get in, not the child the idle screen is for.

To spread OLED wear over a screen that can sit up for an hour, the whole block
creeps through a few vertical positions; the caller folds that offset into the
fingerprint so it is redrawn when it moves and not otherwise.
"""

from __future__ import annotations

from typing import Any

from . import fonts
from .primitives import WIDTH, draw_text_centered, new_frame, text_width

# Vertical positions the block cycles through, slowest first.
WANDER = (-2, 0, 2)
WANDER_PERIOD_S = 45.0


def wander_offset(now: float) -> int:
    """The current vertical nudge, in pixels. Keyed to a slow clock."""
    return WANDER[int(now / WANDER_PERIOD_S) % len(WANDER)]


def _fit(draw: Any, text: str, max_px: int, sizes: tuple[int, ...], weight: str) -> Any:
    """Largest font from *sizes* in which *text* fits *max_px*, else the last."""
    for size in sizes:
        font = fonts.get(weight, size)
        if text_width(draw, text, font) <= max_px:
            return font
    return fonts.get(weight, sizes[-1])


def _clip(draw: Any, text: str, font: Any, max_px: int) -> str:
    if text_width(draw, text, font) <= max_px:
        return text
    trimmed = text
    while trimmed and text_width(draw, trimmed + "…", font) > max_px:
        trimmed = trimmed[:-1]
    return trimmed + "…"


def render_hotspot(
    ssid: str, password: str | None, url: str | None, *, offset: int = 0
) -> Any:
    """SSID, password and address for the setup hotspot, stacked and centred."""
    img, draw = new_frame()
    inner = WIDTH - 8
    ssid = ssid or "Minabox-Setup"

    rows: list[tuple[str, tuple[int, ...], str]] = [
        ("Setup-WLAN", (12,), fonts.BOLD),
        (ssid, (13, 12, 11, 10), fonts.REGULAR),
    ]
    if password:
        rows.append((f"Code: {password}", (12, 11, 10), fonts.REGULAR))
    if url:
        rows.append((url, (12, 11, 10, 9), fonts.BOLD))

    # Even baselines across the usable height, then the wander offset. Every
    # line is clipped to the panel width - PIL would happily draw past the edge.
    baselines = _spread(len(rows))
    for (text, sizes, weight), baseline in zip(rows, baselines, strict=True):
        font = _fit(draw, text, inner, sizes, weight)
        line = _clip(draw, text, font, inner)
        draw_text_centered(draw, line, font, baseline + offset)
    return img


def _spread(count: int) -> list[int]:
    """`count` baselines from ~13 to ~60, roughly even."""
    top, bottom = 13, 60
    if count == 1:
        return [(top + bottom) // 2]
    step = (bottom - top) / (count - 1)
    return [round(top + i * step) for i in range(count)]


def render_no_network(*, offset: int = 0) -> Any:
    """A crossed-out signal and a short word. There is nothing to do yet."""
    img, draw = new_frame()
    cx = WIDTH // 2
    top = 6 + offset

    # Three rising arcs, largest last, struck through.
    for i, radius in enumerate((6, 13, 20)):
        y = top + 22
        draw.arc(
            [cx - radius, y - radius, cx + radius, y + radius],
            start=225,
            end=315,
            fill=1,
            width=2 + i // 2,
        )
    draw.ellipse([cx - 2, top + 20, cx + 2, top + 24], fill=1)
    draw.line([cx - 22, top + 2, cx + 22, top + 40], fill=1, width=3)

    draw_text_centered(draw, "Kein Netz", fonts.get(fonts.BOLD, 13), 60 + offset)
    return img
