"""Small glyphs for things that are true but not worth a screen.

The widget grid used to carry these in a corner. It is gone, and with it went
the only sign that an error had happened or that a sleep timer was running -
so they come back here, as marks on the idle screen rather than as screens of
their own.

Deliberately small and absent in the normal case. A full screen saying "Fehler"
would displace Knuffel for minutes over something that has usually recovered
already, and would claim more certainty than the service has: the error flag
expires by itself precisely because nothing tells us whether it is still wrong.
"""

from __future__ import annotations

from typing import Any

SIZE = 12
GAP = 3


def error(canvas: Any, x: int, y: int, size: int = SIZE) -> None:
    """An exclamation mark in a circle: something went wrong recently."""
    line = max(1, size // 10)
    canvas.ellipse([x, y, x + size - 1, y + size - 1], outline=1, width=line)
    x0 = x + size * 42 // 100
    x1 = x + size * 58 // 100
    canvas.rectangle([x0, y + size * 22 // 100, x1, y + size * 58 // 100], fill=1)
    canvas.rectangle([x0, y + size * 68 // 100, x1, y + size * 80 // 100], fill=1)


def sleep_timer(canvas: Any, x: int, y: int, size: int = SIZE) -> None:
    """A waning moon: the box will stop by itself."""
    canvas.ellipse([x, y, x + size - 1, y + size - 1], fill=1)
    canvas.ellipse(
        [x + size * 28 // 100, y - 1, x + size + size * 5 // 100, y + size * 75 // 100],
        fill=0,
    )


def no_internet(canvas: Any, x: int, y: int, size: int = SIZE) -> None:
    """A small globe with a stroke through it: on the LAN, but no way out."""
    line = max(1, size // 10)
    canvas.ellipse([x, y, x + size - 1, y + size - 1], outline=1, width=line)
    mid = y + size // 2
    canvas.line([x, mid, x + size - 1, mid], fill=1, width=line)
    canvas.ellipse(
        [x + size * 30 // 100, y, x + size * 70 // 100, y + size - 1],
        outline=1,
        width=line,
    )
    canvas.line(
        [(x + size - 1, y), (x, y + size - 1)],
        fill=1,
        width=max(2, size // 6),
    )


def barred(canvas: Any, x: int, y: int, size: int) -> None:
    """A circle with a stroke through it: this one, no."""
    line = max(2, size // 8)
    canvas.ellipse([x, y, x + size - 1, y + size - 1], outline=1, width=line)
    inset = size // 5
    canvas.line(
        [(x + inset, y + size - 1 - inset), (x + size - 1 - inset, y + inset)],
        fill=1,
        width=line,
    )


def locked(canvas: Any, x: int, y: int, size: int = SIZE) -> None:
    """A padlock: the box is being driven from the phone."""
    shackle_w = max(4, round(size * 0.5))
    shackle_x0 = x + (size - shackle_w) // 2
    shackle_x1 = shackle_x0 + shackle_w - 1
    body_top = y + round(size * 0.42)
    stroke = max(1, round(size * 0.14))
    canvas.arc(
        [shackle_x0, y, shackle_x1, body_top + stroke],
        start=180,
        end=360,
        fill=1,
        width=stroke,
    )
    canvas.line([(shackle_x0, (y + body_top) // 2), (shackle_x0, body_top)], fill=1, width=stroke)
    canvas.line([(shackle_x1, (y + body_top) // 2), (shackle_x1, body_top)], fill=1, width=stroke)
    bx0 = x + max(1, round(size * 0.12))
    bx1 = x + size - 1 - max(1, round(size * 0.12))
    canvas.rectangle([bx0, body_top, bx1, y + size - 1], fill=1)
    if size >= 18:
        # Cut a keyhole into the larger notice-sized lock.
        kx = (bx0 + bx1) // 2
        ky = body_top + (y + size - 1 - body_top) // 2
        kr = max(1, size // 10)
        canvas.ellipse([kx - kr, ky - kr - 1, kx + kr, ky + kr - 1], fill=0)
        canvas.line([(kx, ky), (kx, ky + kr + 2)], fill=0, width=max(1, kr))
