"""OLED display controller (SSD1306 over I2C): header (full width) + 2 columns."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)

_DEVICE = None

# Icons can be replaced by placing PNGs in assets/icons/ (relative to package root)
_ASSETS_ICONS: Path = Path(__file__).resolve().parent.parent / "assets" / "icons"
_ICON_CACHE: Dict[str, Any] = {}

# Layout: header row (full width) + 2 body columns
_HEADER_H = 16
_BODY_H = 64 - _HEADER_H  # 48
_COL_W = 64
_COL_X = [0, 64]
_SLOT_H = 16  # 48 / 3 slots per column
_SLOT_GAP = 4  # vertical gap between elements when more than one in left/right column
_ICON_SIZE = 16
_SLEEP_ICON_TEXT_GAP = 3  # px between moon icon and minutes text
_W = 128

# Font size names -> pixel height
_FONT_SIZE_MAP = {"small": 8, "medium": 10, "large": 12}

# TTF paths to try for sans/mono
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
]

# 16x16 pixel icons: (x, y) in 0..15. mute = speaker + diagonal slash; moon = crescent
_ICON_MUTE = [
    # Speaker body (rounded rect + cone)
    (1, 6), (1, 7), (1, 8), (1, 9),
    (2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (2, 10),
    (3, 5), (3, 6), (3, 7), (3, 8), (3, 9), (3, 10),
    (4, 5), (4, 6), (4, 7), (4, 8), (4, 9), (4, 10),
    (5, 6), (5, 7), (5, 8), (5, 9),
    # Diagonal slash (mute line, 2px thick)
    (6, 1), (7, 2), (8, 3), (9, 4), (10, 5), (11, 6), (12, 7), (13, 8), (14, 9), (15, 10),
    (6, 2), (7, 3), (8, 4), (9, 5), (10, 6), (11, 7), (12, 8), (13, 9), (14, 10), (15, 11),
]
_ICON_MOON = [
    (6, 2), (6, 3), (6, 4), (6, 5), (6, 6), (6, 7), (6, 8), (6, 9), (6, 10), (6, 11), (6, 12), (6, 13),
    (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (7, 6), (7, 7), (7, 8), (7, 9), (7, 10), (7, 11), (7, 12), (7, 13), (7, 14),
    (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 6), (8, 7), (8, 8), (8, 9), (8, 10), (8, 11), (8, 12), (8, 13), (8, 14),
    (9, 2), (9, 3), (9, 4), (9, 5), (9, 6), (9, 7), (9, 8), (9, 9), (9, 10), (9, 11), (9, 12), (9, 13),
    (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9), (10, 10), (10, 11), (10, 12),
    (11, 4), (11, 5), (11, 6), (11, 7), (11, 8), (11, 9), (11, 10), (11, 11),
    (12, 5), (12, 6), (12, 7), (12, 8), (12, 9), (12, 10),
    (13, 6), (13, 7), (13, 8), (13, 9),
    (14, 7), (14, 8),
]
# Repeat: circular arrows (simplified two curved arrows)
_ICON_REPEAT = [
    (2, 8), (3, 7), (4, 6), (5, 5), (6, 4), (7, 4), (8, 5), (9, 6), (10, 7), (11, 8),
    (3, 8), (4, 7), (5, 6), (6, 5), (7, 5), (8, 6), (9, 7), (10, 8),
    (10, 8), (11, 9), (12, 10), (13, 11), (14, 12), (13, 13), (12, 14), (11, 13), (10, 12), (9, 11),
    (10, 9), (11, 10), (12, 11), (13, 12), (12, 13), (11, 12),
]
# Shuffle: crossed arrows (simplified)
_ICON_SHUFFLE = [
    (2, 4), (3, 5), (4, 6), (5, 7), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4),
    (3, 4), (4, 5), (5, 6), (6, 7), (7, 6), (8, 5), (9, 4),
    (6, 8), (7, 9), (8, 10), (9, 11), (10, 12), (11, 11), (12, 10), (13, 9), (14, 8),
    (7, 9), (8, 10), (9, 11), (10, 10), (11, 9), (12, 8),
    (6, 8), (5, 9), (4, 10), (3, 11), (2, 12), (3, 13), (4, 12), (5, 11), (6, 10),
    (5, 9), (4, 10), (3, 11), (4, 12), (5, 11),
]
# Bluetooth: vertical bar + two triangles (classic B shape)
_ICON_BLUETOOTH = [
    (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (7, 6), (7, 7), (7, 8), (7, 9), (7, 10), (7, 11), (7, 12), (7, 13), (7, 14),
    (8, 3), (8, 4), (9, 4), (9, 5), (10, 5), (10, 6), (11, 6), (11, 7), (12, 7), (12, 8), (13, 8), (13, 9), (14, 9), (14, 10),
    (8, 11), (8, 12), (9, 11), (9, 12), (10, 10), (10, 11), (11, 9), (11, 10), (12, 8), (12, 9), (13, 7), (13, 8), (14, 6), (14, 7),
]


def init(i2c_bus: int, i2c_address: int) -> bool:
    """Initialize SSD1306 device. Returns True if successful."""
    global _DEVICE
    if _DEVICE is not None:
        return True
    try:
        from luma.core.interface.serial import i2c as luma_i2c
        from luma.oled.device import ssd1306

        serial = luma_i2c(port=i2c_bus, address=i2c_address)
        _DEVICE = ssd1306(serial)
        logger.info("display_initialized", bus=i2c_bus, address=i2c_address)
        return True
    except Exception as exc:
        logger.warning(
            "display_init_failed",
            bus=i2c_bus,
            address=i2c_address,
            error=str(exc),
        )
        return False


def clear() -> None:
    """Clear the display."""
    if _DEVICE is None:
        return
    try:
        from luma.core.render import canvas

        with canvas(_DEVICE) as draw:
            draw.rectangle(_DEVICE.bounding_box, outline="black", fill="black")
    except Exception as exc:
        logger.warning("display_clear_failed", error=str(exc))


def show_lines(lines: List[str]) -> None:
    """Render up to 4 lines of text (legacy single-column). No-op if display not available."""
    if _DEVICE is None:
        return
    max_lines = 4
    line_height = 14
    max_chars = 20
    display_lines = [s[:max_chars] if len(s) > max_chars else s for s in lines[:max_lines]]
    try:
        from luma.core.render import canvas

        with canvas(_DEVICE) as draw:
            for i, text in enumerate(display_lines):
                if text:
                    draw.text((0, i * line_height), text, fill="white")
    except Exception as exc:
        logger.warning("display_show_failed", error=str(exc))


def _get_font(
    font_size: str = "medium",
    font: str = "default",
) -> Any:
    """Return a PIL ImageFont. font_size: small|medium|large, font: default|sans|mono."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    size = _FONT_SIZE_MAP.get(font_size, 10)
    if font == "default":
        return ImageFont.load_default()
    want_mono = font == "mono"
    for path in _FONT_PATHS:
        if not os.path.isfile(path):
            continue
        is_mono = "Mono" in path
        if is_mono != want_mono:
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _icon_image_from_pixels(icon_name: str) -> Any:
    """Build a 16x16 mode-'1' PIL Image from pixel lists (fallback when no PNG)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    points = (
        _ICON_MUTE if icon_name == "mute"
        else _ICON_MOON if icon_name == "sleep_timer"
        else _ICON_REPEAT if icon_name == "repeat"
        else _ICON_SHUFFLE if icon_name == "shuffle"
        else _ICON_BLUETOOTH if icon_name == "bluetooth"
        else []
    )
    img = Image.new("1", (_ICON_SIZE, _ICON_SIZE), 0)
    for (px, py) in points:
        img.putpixel((px, py), 1)
    return img


def _get_icon_image(icon_name: str) -> Any:
    """Return a 16x16 mode-'1' PIL Image for the icon. Uses PNG from assets/icons if present."""
    if icon_name in _ICON_CACHE:
        return _ICON_CACHE[icon_name]
    try:
        from PIL import Image
    except ImportError:
        return _icon_image_from_pixels(icon_name)
    # icon_mute.png, icon_moon.png (sleep_timer uses moon)
    filename = "icon_moon.png" if icon_name == "sleep_timer" else f"icon_{icon_name}.png"
    path = _ASSETS_ICONS / filename
    from_file = path.is_file()
    if from_file:
        try:
            im = Image.open(path).convert("1")
            if im.size != (_ICON_SIZE, _ICON_SIZE):
                im = im.resize((_ICON_SIZE, _ICON_SIZE), Image.Resampling.NEAREST)
            _ICON_CACHE[icon_name] = im
            return im
        except Exception as exc:
            logger.debug("icon_load_failed", path=str(path), error=str(exc))
    fallback = _icon_image_from_pixels(icon_name)
    if fallback is not None:
        _ICON_CACHE[icon_name] = fallback
    return fallback


def _draw_item(
    img: Any,
    draw: Any,
    item: dict,
    x: int,
    y: int,
    slot_w: int,
    slot_h: int,
    pil_font: Any,
    max_chars: int = 10,
) -> int:
    """Draw one item (icon or text) at (x,y) in a slot of slot_w x slot_h. Returns width used."""
    if item.get("type") == "icon":
        icon_val = item.get("value") or ""
        icon_img = _get_icon_image(icon_val)
        if icon_img is not None:
            ix = x + (slot_w - _ICON_SIZE) // 2
            iy = y + (slot_h - _ICON_SIZE) // 2
            img.paste(icon_img, (ix, iy))
            return _ICON_SIZE
        return 0
    text = (item.get("value") or "")[:max_chars]
    if not text:
        return 0
    if pil_font is not None:
        bbox = draw.textbbox((0, 0), text, font=pil_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x + (slot_w - tw) // 2
        ty = y + (slot_h - th) // 2
        draw.text((tx, ty), text, fill="white", font=pil_font)
    else:
        tx = x + (slot_w - max_chars * 6) // 2
        ty = y + (slot_h - 10) // 2
        draw.text((tx, ty), text, fill="white")
    return min(len(text) * 6, slot_w)


def show_areas(
    areas: List[List[dict]],
    font_size: str = "medium",
    font: str = "default",
) -> None:
    """Render header (areas[0]) full width + 2 columns (areas[1], areas[2]).
    Each item: {'type': 'text', 'value': '...'}, {'type': 'icon', 'value': '...'}, or {'type': 'sleep_timer', 'minutes': N}.
    """
    if _DEVICE is None:
        return
    max_chars_col = 8
    pil_font = _get_font(font_size, font)
    try:
        from PIL import Image, ImageDraw

        bb = _DEVICE.bounding_box
        w = bb[2] - bb[0] + 1
        h = bb[3] - bb[1] + 1
        img = Image.new("1", (w, h), 0)
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, w - 1, h - 1), outline="black", fill="black")

        header_items = areas[0][:6] if len(areas) > 0 else []
        body_left = areas[1][:3] if len(areas) > 1 else []
        body_right = areas[2][:3] if len(areas) > 2 else []

        # Gap below header / above body so content is not on the separator
        _SEP_Y = _HEADER_H + 2  # 2px below header row so line is clearly separated
        _BODY_TOP = _SEP_Y + 5  # 5px below separator so body content has space
        _BODY_USABLE_H = h - _BODY_TOP

        # Header: center items. One item = center on full width; multiple = evenly distributed zones, each centered
        n_header = len([i for i in header_items if isinstance(i, dict)])
        if n_header > 0:
            zone_w = w // n_header
            for idx, item in enumerate(header_items):
                if not isinstance(item, dict):
                    continue
                zone_x = idx * zone_w
                if item.get("type") == "sleep_timer":
                    icon_img = _get_icon_image("sleep_timer")
                    mins = item.get("minutes", 0)
                    text = f"{mins}m"
                    text_w = 0
                    if pil_font and text:
                        bbox = draw.textbbox((0, 0), text, font=pil_font)
                        text_w = bbox[2] - bbox[0]
                    total_w = (_ICON_SIZE + _SLEEP_ICON_TEXT_GAP + text_w) if icon_img else text_w
                    hx = zone_x + (zone_w - total_w) // 2
                    if icon_img is not None:
                        img.paste(icon_img, (hx, (_HEADER_H - _ICON_SIZE) // 2))
                        hx += _ICON_SIZE + _SLEEP_ICON_TEXT_GAP
                    if pil_font and text:
                        th = bbox[3] - bbox[1]
                        draw.text((hx, (_HEADER_H - th) // 2), text, fill="white", font=pil_font)
                else:
                    _draw_item(img, draw, item, zone_x, 0, zone_w, _HEADER_H, pil_font, max_chars=6)

        # Separator: horizontal line with small gap below header
        draw.line([(0, _SEP_Y), (w - 1, _SEP_Y)], fill="white")
        # Separator: vertical line between left and right body
        draw.line([(64, _BODY_TOP), (64, h - 1)], fill="white")

        # Body: two columns, content vertically centered with top margin; gap between elements when >1
        for col_idx, (col_x, items) in enumerate([(0, body_left), (_COL_X[1], body_right)]):
            items = [i for i in items if isinstance(i, dict)]
            n_slots = len(items)
            if n_slots == 0:
                continue
            slot_step = _SLOT_H + (_SLOT_GAP if n_slots > 1 else 0)
            block_h = n_slots * _SLOT_H + ((n_slots - 1) * _SLOT_GAP if n_slots > 1 else 0)
            start_y = _BODY_TOP + (_BODY_USABLE_H - block_h) // 2
            for slot_idx, item in enumerate(items):
                slot_y = start_y + slot_idx * slot_step
                if item.get("type") == "sleep_timer":
                    icon_img = _get_icon_image("sleep_timer")
                    mins = item.get("minutes", 0)
                    text = f"{mins}m"
                    text_w = 0
                    if pil_font and text:
                        bbox = draw.textbbox((0, 0), text, font=pil_font)
                        text_w = bbox[2] - bbox[0]
                        th = bbox[3] - bbox[1]
                    total_w = (_ICON_SIZE + _SLEEP_ICON_TEXT_GAP + text_w) if icon_img else text_w
                    slot_start_x = col_x + (_COL_W - total_w) // 2
                    if icon_img is not None:
                        img.paste(icon_img, (slot_start_x, slot_y + (_SLOT_H - _ICON_SIZE) // 2))
                    if pil_font and text:
                        draw.text((slot_start_x + (_ICON_SIZE + _SLEEP_ICON_TEXT_GAP if icon_img else 0), slot_y + (_SLOT_H - th) // 2), text, fill="white", font=pil_font)
                else:
                    _draw_item(img, draw, item, col_x, slot_y, _COL_W, _SLOT_H, pil_font, max_chars_col)
        _DEVICE.display(img)
    except Exception as exc:
        logger.warning("display_show_failed", error=str(exc))


def is_available() -> bool:
    """Return True if display hardware was successfully initialized."""
    return _DEVICE is not None
