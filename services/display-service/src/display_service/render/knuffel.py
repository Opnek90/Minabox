"""Knuffel, the creature on the idle screen.

Drawn filled rather than outlined: on an OLED the lit area is what carries,
and black eyes cut into it read better at thirty pixels than white strokes on
black. Everything is relative to a 40-unit grid, so the same shape works at 28
px on the idle screen and at 44 px when it is puzzled about a figure.

The moods are the whole trick. Eyes are what make something look alive, and a
blink costs about twenty bytes on the bus - one page of the eye row - which is
nothing next to the 1024 of a whole frame.
"""

from __future__ import annotations

from typing import Any

AWAKE = "awake"
BLINK = "blink"
ASLEEP = "asleep"
PUZZLED = "puzzled"
WAVE_UP = "wave_up"
WAVE_DOWN = "wave_down"

MOODS = (AWAKE, BLINK, ASLEEP, PUZZLED, WAVE_UP, WAVE_DOWN)
WAVING = (WAVE_UP, WAVE_DOWN)

# Everything below is in fortieths of the sprite's size.
_GRID = 40.0

# Waving needs room beside him: an arm tucked inside the body outline is
# swallowed by it, and one drawn past the sprite box is silently clipped by
# PIL. So he is wider while waving, and callers reserve the difference.
WAVE_OVERHANG_UNITS = 10


def wave_overhang(size: int) -> int:
    """Extra pixels to the right that a waving Knuffel needs."""
    return round(WAVE_OVERHANG_UNITS * size / _GRID)


def draw(canvas: Any, x: int, y: int, size: int, mood: str = AWAKE) -> None:
    """Draw Knuffel with the top left of his box at (x, y), *size* px across."""
    unit = size / _GRID

    def point(a: float, b: float) -> tuple[int, int]:
        return round(x + a * unit), round(y + b * unit)

    def box(a: float, b: float, c: float, d: float) -> list[tuple[int, int]]:
        return [point(a, b), point(c, d)]

    def stroke() -> int:
        return max(1, round(2 * unit))

    if mood in WAVING:
        # Arm first, so the body draws over the shoulder end of it.
        # Both phases keep the hand clear of the body and near the head: a
        # hand tilting beside the face reads as waving, one dropped alongside
        # the body reads as an arm that has been swallowed by it.
        high = mood == WAVE_UP
        canvas.line(
            [point(33, 17), point(45, 5) if high else point(47, 15)],
            fill=1,
            width=max(2, round(4 * unit)),
        )
        canvas.ellipse(
            box(41, 1, 49, 9) if high else box(43, 11, 50, 19), fill=1
        )

    canvas.ellipse(box(4, 0, 15, 13), fill=1)   # left ear
    canvas.ellipse(box(25, 0, 36, 13), fill=1)  # right ear
    canvas.ellipse(box(2, 8, 38, 36), fill=1)   # body
    canvas.ellipse(box(7, 32, 17, 39), fill=1)  # left foot
    canvas.ellipse(box(23, 32, 33, 39), fill=1)  # right foot

    eyes = (point(12, 19), point(28, 19))
    radius = max(1, round(3 * unit))

    if mood in WAVING:
        for cx, cy in eyes:
            canvas.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius], fill=0
            )
        mx, my = point(20, 26)
        canvas.arc(
            [
                mx - round(5 * unit),
                my - round(4 * unit),
                mx + round(5 * unit),
                my + round(3 * unit),
            ],
            start=20,
            end=160,
            fill=0,
            width=stroke(),
        )
        return

    if mood == BLINK:
        for cx, cy in eyes:
            canvas.line([(cx - radius, cy), (cx + radius, cy)], fill=0, width=stroke())
        return

    if mood == ASLEEP:
        for cx, cy in eyes:
            canvas.arc(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                start=0,
                end=180,
                fill=0,
                width=stroke(),
            )
        return

    for cx, cy in eyes:
        canvas.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=0)

    if mood == PUZZLED:
        # One raised brow. A mouth as well would be mud at this size.
        bx, by = point(25, 12)
        canvas.line(
            [(bx, by), (bx + round(9 * unit), by - round(3 * unit))],
            fill=0,
            width=stroke(),
        )
        return

    mx, my = point(20, 26)
    canvas.arc(
        [
            mx - round(5 * unit),
            my - round(4 * unit),
            mx + round(5 * unit),
            my + round(3 * unit),
        ],
        start=20,
        end=160,
        fill=0,
        width=stroke(),
    )


def sleep_marks(canvas: Any, x: int, baseline: int, font_for: Any) -> None:
    """Three rising z's, each larger than the last."""
    for offset_x, offset_y, size in ((0, 0, 8), (7, -8, 11), (17, -18, 14)):
        canvas.text(
            (x + offset_x, baseline + offset_y),
            "z",
            fill=1,
            font=font_for(size),
            anchor="ls",
        )
