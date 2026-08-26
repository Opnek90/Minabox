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


def sleep_z(draw: Any, x: int, y: int, size: int) -> None:
    """A single "Z" in a *size* x *size* box with its top left at (x, y).

    Drawn from three strokes rather than set as text: a font glyph small enough
    to sit beside a 27 px creature comes out as a grey smudge on a 1-bit panel,
    while three lines stay a Z down to about six pixels.
    """
    stroke = max(1, round(size / 6))
    right = x + size - 1
    bottom = y + size - 1
    draw.line([(x, y), (right, y)], fill=1, width=stroke)
    draw.line([(right, y), (x, bottom)], fill=1, width=stroke)
    draw.line([(x, bottom), (right, bottom)], fill=1, width=stroke)


# Where the three Zs sit relative to the anchor, and how big each one is.
# They climb to the right and grow as they go - the small one has just left
# him, the big one is furthest away.
_SLEEP_Z_STEPS = ((0, 12, 5), (8, 6, 7), (18, 0, 10))


def sleep_zs(draw: Any, x: int, y: int, count: int) -> None:
    """Up to three rising Zs, with the smallest at (x, y + 12).

    *count* is which phase of the loop this is: one Z, then two, then three,
    then round again. That is the whole animation - on a panel that cannot fade
    anything out, appearing one after another is what reads as breathing.
    """
    for index in range(max(0, min(count, len(_SLEEP_Z_STEPS)))):
        dx, dy, size = _SLEEP_Z_STEPS[index]
        sleep_z(draw, x + dx, y + dy, size)


SLEEP_ZS_WIDTH = _SLEEP_Z_STEPS[-1][0] + _SLEEP_Z_STEPS[-1][2]
SLEEP_ZS_HEIGHT = _SLEEP_Z_STEPS[0][1] + _SLEEP_Z_STEPS[0][2]
SLEEP_ZS_PHASES = len(_SLEEP_Z_STEPS)


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


def _ellipsize(
    draw: Any, text: str, font: Any, max_width: int, *, force: bool = False
) -> str:
    """Return *text*, trimmed and marked with an ellipsis if it does not fit."""
    if not force and text_width(draw, text, font) <= max_width:
        return text
    trimmed = text
    while trimmed and text_width(draw, trimmed + "…", font) > max_width:
        trimmed = trimmed[:-1]
    return trimmed.rstrip() + "…"


def wrap(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    """Break *text* into at most *max_lines* lines of at most *max_width* px.

    Wrapping is against measured pixel width, not a character count: "Ein Lama
    in Yokohama" and "MMMMMMMMMMMMMMMMMMMM" are the same length and nowhere
    near the same width.

    Every returned line is guaranteed to fit *max_width*, including the case of
    a single word wider than the whole line. That guarantee is what callers
    rely on to decide whether a font size works - without it, an over-wide word
    came back unmarked and was drawn off the edge of the panel.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    index = 0
    while index < len(words) and len(lines) < max_lines:
        word = words[index]
        candidate = f"{current} {word}".strip()
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
            index += 1
        elif current:
            # Break before this word and try it again on the next line.
            lines.append(current)
            current = ""
        else:
            # One word, too wide even alone. Take it and let the trim below
            # deal with it, or this loop never advances.
            lines.append(word)
            index += 1
    if current and len(lines) < max_lines:
        lines.append(current)
        current = ""

    leftover = bool(current) or index < len(words)
    lines = [_ellipsize(draw, line, font, max_width) for line in lines] or [""]
    if leftover and not lines[-1].endswith("…"):
        lines[-1] = _ellipsize(draw, lines[-1], font, max_width, force=True)
    return lines


def block_height(size: int, line_count: int, line_gap: int = 2) -> int:
    """Height of *line_count* lines set at *size*, from cap top to last baseline."""
    return size + max(0, line_count - 1) * (size + line_gap)


def fit_lines(
    draw: Any,
    text: str,
    max_width: int,
    max_lines: int,
    sizes: tuple[int, ...],
    weight: str,
    *,
    max_height: int | None = None,
    line_gap: int = 2,
) -> tuple[Any, list[str], int]:
    """Largest size from *sizes* in which *text* fits whole; the last otherwise.

    This is what lets a short title be big and a long one still be complete:
    a one-liner comes back large, "Das Lied von der Raupe Nimmersatt" at 12 px
    on two lines, and neither is cut.

    ``max_height`` is not optional in spirit. Checking only the width picks a
    size whose lines then do not fit the band they were meant for, and the
    caller silently drops the ones that overflow - which is how the second line
    of every two-line title went missing the first time round.
    """
    from . import fonts

    for size in sizes:
        font = fonts.get(weight, size)
        lines = wrap(draw, text, font, max_width, max_lines)
        if lines[-1].endswith("…"):
            continue
        if max_height is not None:
            if block_height(size, len(lines), line_gap) > max_height:
                continue
        return font, lines, size
    size = sizes[-1]
    font = fonts.get(weight, size)
    return font, wrap(draw, text, font, max_width, max_lines), size
