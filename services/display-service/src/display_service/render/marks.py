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
