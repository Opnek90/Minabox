"""OLED display controller (SSD1306 over I2C) for rendering in 3 columns."""

from __future__ import annotations

import os
from typing import Any, List

import structlog

logger = structlog.get_logger(__name__)

_DEVICE = None

# Column layout: 128 / 3 ≈ 42px per column, 64px height, 4 slots of 16px
_COL_W = 42
_COL_H = 64
_COL_X = [0, 43, 86]
_SLOT_H = 16  # 64 / 4
_ICON_SIZE = 16

# Font size names -> pixel height
_FONT_SIZE_MAP = {"small": 8, "medium": 10, "large": 12}

# TTF paths to try for sans/mono
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
]

# 16x16 pixel icons: (x, y) in 0..15. mute = speaker + X; moon = crescent
_ICON_MUTE = [
    (2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (2, 10),
    (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (3, 9), (3, 10), (3, 11),
    (4, 4), (4, 5), (4, 6), (4, 7), (4, 8), (4, 9), (4, 10), (4, 11),
    (5, 5), (5, 6), (5, 7), (5, 8), (5, 9), (5, 10),
    (6, 6), (6, 7), (6, 8), (6, 9),
    (7, 7), (7, 8),
    (9, 5), (10, 6), (11, 7), (12, 8), (13, 9), (14, 10),
    (9, 10), (10, 9), (11, 8), (12, 7), (13, 6), (14, 5),
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


def _draw_icon(draw: Any, x: int, y: int, icon_name: str) -> None:
    """Draw a 16x16 icon at (x, y). icon_name: 'mute' or 'sleep_timer'."""
    points = _ICON_MUTE if icon_name == "mute" else _ICON_MOON if icon_name == "sleep_timer" else []
    for px, py in points:
        draw.point((x + px, y + py), fill="white")


def show_areas(
    areas: List[List[dict]],
    font_size: str = "medium",
    font: str = "default",
) -> None:
    """Render 3 columns. areas = [items_col0, items_col1, items_col2].
    Each item: {'type': 'text', 'value': '...'} or {'type': 'icon', 'value': 'mute'|'sleep_timer'}.
    Content is centered horizontally and vertically within each slot.
    """
    if _DEVICE is None:
        return
    max_chars_per_col = 6
    pil_font = _get_font(font_size, font)
    try:
        from luma.core.render import canvas

        with canvas(_DEVICE) as draw:
            draw.rectangle(_DEVICE.bounding_box, outline="black", fill="black")
            for col_idx, col_x in enumerate(_COL_X):
                if col_idx >= len(areas):
                    continue
                items = areas[col_idx][:4]
                for slot_idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    slot_y = slot_idx * _SLOT_H
                    if item.get("type") == "icon":
                        icon_val = item.get("value") or ""
                        if icon_val in ("mute", "sleep_timer"):
                            # Center 16x16 icon in slot (42 x 16)
                            icon_x = col_x + (_COL_W - _ICON_SIZE) // 2
                            icon_y = slot_y + (_SLOT_H - _ICON_SIZE) // 2
                            _draw_icon(draw, icon_x, icon_y, icon_val)
                    else:
                        text = (item.get("value") or "")[:max_chars_per_col]
                        if text and pil_font is not None:
                            # Measure text and center in slot
                            bbox = draw.textbbox((0, 0), text, font=pil_font)
                            tw = bbox[2] - bbox[0]
                            th = bbox[3] - bbox[1]
                            text_x = col_x + (_COL_W - tw) // 2
                            text_y = slot_y + (_SLOT_H - th) // 2
                            draw.text((text_x, text_y), text, fill="white", font=pil_font)
                        elif text:
                            text_x = col_x + (_COL_W - max_chars_per_col * 6) // 2
                            text_y = slot_y + (_SLOT_H - 10) // 2
                            draw.text((text_x, text_y), text, fill="white")
    except Exception as exc:
        logger.warning("display_show_failed", error=str(exc))


def is_available() -> bool:
    """Return True if display hardware was successfully initialized."""
    return _DEVICE is not None
