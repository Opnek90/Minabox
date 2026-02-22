"""Generate 16x16 default icon PNGs (clean vector-style). Run from repo root: python scripts/generate_icon_assets.py."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 16


def draw_icon_mute() -> Image.Image:
    """Mute: speaker body + diagonal mute bar (clear, icon-style)."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    # Speaker body (rounded rectangle left side)
    d.rectangle((2, 4, 6, 12), outline=1, fill=1)
    # Cone/triangle hint (small triangle)
    d.polygon([(6, 5), (6, 11), (10, 8)], outline=1, fill=1)
    # Mute slash through the icon
    d.line([(8, 3), (14, 13)], fill=1, width=2)
    d.line([(9, 3), (14, 12)], fill=1, width=1)
    d.line([(8, 4), (13, 13)], fill=1, width=1)
    return img


def draw_icon_moon() -> Image.Image:
    """Moon: crescent (outer circle minus inner circle)."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    # Outer circle (full moon)
    d.ellipse((0, 0, 15, 15), outline=1, fill=1)
    # Inner circle offset right+down to create crescent (overdraw with black)
    d.ellipse((4, 2, 15, 13), outline=0, fill=0)
    return img


def draw_icon_play() -> Image.Image:
    """Play: triangle pointing right."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    d.polygon([(5, 2), (5, 14), (13, 8)], outline=1, fill=1)
    return img


def draw_icon_pause() -> Image.Image:
    """Pause: two vertical bars."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    d.rectangle((4, 3, 6, 13), outline=1, fill=1)
    d.rectangle((10, 3, 12, 13), outline=1, fill=1)
    return img


def draw_icon_stop() -> Image.Image:
    """Stop: square."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    d.rectangle((4, 4, 12, 12), outline=1, fill=1)
    return img


def draw_icon_error() -> Image.Image:
    """Error: exclamation mark in circle."""
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    d.ellipse((1, 1, 14, 14), outline=1, fill=0)
    d.line([(8, 4), (8, 8)], fill=1, width=2)
    d.rectangle((6, 10, 10, 12), fill=1)
    return img


def main():
    base = Path(__file__).resolve().parent.parent / "src" / "display_service" / "assets" / "icons"
    base.mkdir(parents=True, exist_ok=True)
    icons = [
        ("icon_mute", draw_icon_mute),
        ("icon_moon", draw_icon_moon),
        ("icon_play", draw_icon_play),
        ("icon_pause", draw_icon_pause),
        ("icon_stop", draw_icon_stop),
        ("icon_error", draw_icon_error),
    ]
    for name, draw_fn in icons:
        img = draw_fn()
        img.save(base / f"{name}.png")
        print(f"Wrote {base / name}.png")
    print("Done.")


if __name__ == "__main__":
    main()
