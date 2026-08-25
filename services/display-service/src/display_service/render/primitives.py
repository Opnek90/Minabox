"""Drawing helpers shared by the screen renderers.

Everything here works on a mode-'1' image: fill=1 is a lit pixel, fill=0 is
off. Coordinates are inclusive pixel positions, the way PIL's ImageDraw
treats them.
"""

from __future__ import annotations

from typing import Any

WIDTH = 128
HEIGHT = 64


def new_frame(width: int = WIDTH, height: int = HEIGHT) -> tuple[Any, Any]:
    """Return a blank (image, draw) pair for one panel frame."""
    from PIL import Image, ImageDraw

    img = Image.new("1", (width, height), 0)
    return img, ImageDraw.Draw(img)


def text_width(draw: Any, text: str, font: Any) -> int:
    """Rendered width in pixels, measured rather than estimated."""
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def draw_text(draw: Any, xy: tuple[int, int], text: str, font: Any) -> None:
    """Draw *text* with its left edge and baseline at *xy*.

    Baseline anchoring is what keeps a 34 px number and a 13 px unit sitting on
    the same line without hand-tuned offsets per font size.
    """
    draw.text(xy, text, fill=1, font=font, anchor="ls")


def speaker(draw: Any, x: int, y: int, size: int, *, muted: bool = False) -> None:
    """A speaker glyph in a *size* x *size* box with its top left at (x, y)."""
    s = size
    draw.polygon(
        [
            (x, round(y + s * 0.30)),
            (x, round(y + s * 0.70)),
            (round(x + s * 0.25), round(y + s * 0.70)),
            (round(x + s * 0.55), y + s),
            (round(x + s * 0.55), y),
            (round(x + s * 0.25), round(y + s * 0.30)),
        ],
        fill=1,
    )
    if muted:
        width = max(2, s // 6)
        draw.line(
            [
                (round(x + s * 0.66), round(y + s * 0.16)),
                (x + s, round(y + s * 0.84)),
            ],
            fill=1,
            width=width,
        )
        return
    for radius in (0.20, 0.38):
        draw.arc(
            [
                round(x + s * 0.50),
                round(y + s * (0.5 - radius)),
                round(x + s * (0.70 + radius * 1.6)),
                round(y + s * (0.5 + radius)),
            ],
            start=-55,
            end=55,
            fill=1,
            width=2,
        )


def blocks(
    draw: Any,
    box: tuple[int, int, int, int],
    count: int,
    filled: int,
    *,
    gap: int = 3,
) -> None:
    """Draw *count* equal blocks across *box*, the first *filled* of them solid.

    The blocks are laid out on fractional boundaries and rounded per edge, so
    the row always ends exactly on the right edge of *box* however awkward the
    division is - eight blocks over 122 px do not divide evenly.
    """
    x0, y0, x1, y1 = box
    if count <= 0:
        return
    span = x1 - x0
    block_w = (span - gap * (count - 1)) / count
    for i in range(count):
        left = x0 + i * (block_w + gap)
        edges = (round(left), y0, round(left + block_w), y1)
        if i < filled:
            draw.rectangle(edges, fill=1)
        else:
            draw.rectangle(edges, outline=1, width=1)


def bar(
    draw: Any,
    box: tuple[int, int, int, int],
    fraction: float,
    *,
    radius: int = 2,
) -> None:
    """Draw a rounded outline filled to *fraction* (0.0-1.0) of its width."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=1, width=1)
    inner = round((x1 - x0 - 4) * max(0.0, min(1.0, fraction)))
    if inner > 0:
        draw.rectangle([x0 + 2, y0 + 2, x0 + 2 + inner, y1 - 2], fill=1)


def draw_text_centered(
    draw: Any, text: str, font: Any, baseline_y: int, *, width: int = WIDTH
) -> None:
    """Draw *text* horizontally centred, sitting on *baseline_y*."""
    x = (width - text_width(draw, text, font)) // 2
    draw_text(draw, (x, baseline_y), text, font)


def draw_text_right(
    draw: Any, text: str, font: Any, right_x: int, baseline_y: int
) -> None:
    """Draw *text* with its right edge at *right_x*, sitting on *baseline_y*."""
    draw_text(draw, (right_x - text_width(draw, text, font), baseline_y), text, font)
