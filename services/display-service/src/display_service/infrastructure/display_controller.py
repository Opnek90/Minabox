"""OLED display controller (SSD1306 over I2C): header (full width) + 2 columns."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Theme – single source of truth for all layout & visual constants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Theme:
    # Display dimensions
    width: int = 128
    height: int = 64

    # Header
    header_h: int = 16

    # Separator
    sep_padding_top: int = 1     # px gap between header content and separator line
    sep_padding_bottom: int = 2  # px gap between separator line and body content

    # Body columns
    col_w: int = 64              # each column is half the display
    col_padding_x: int = 4       # inner horizontal padding per column

    # Slots inside columns
    # slot_h=13, slot_gap=2 → 3 items = 13+2+13+2+13 = 43px = exact body height
    slot_h: int = 13
    slot_gap: int = 2            # vertical gap between slots when >1 item

    # Icons – sized to sit comfortably inside a 13px slot
    icon_size: int = 11
    sleep_icon_text_gap: int = 3

    # Font sizes (TTF pixel height)
    font_sizes: Dict[str, int] = field(default_factory=lambda: {
        "small": 9,
        "medium": 12,
        "large": 14,
    })

    # TTF/bitmap font search paths, tried in order per font name.
    # Install on Raspberry Pi OS:
    #   sudo apt install fonts-roboto fonts-ubuntu fonts-noto fonts-liberation fonts-terminus
    font_paths: Dict[str, List[str]] = field(default_factory=lambda: {
        "sans": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ],
        "mono": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        ],
        "roboto": [
            "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf",
            "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
            "/usr/share/fonts/TTF/Roboto-Regular.ttf",
        ],
        "ubuntu": [
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/TTF/Ubuntu-R.ttf",
        ],
        "noto": [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf",
            "/usr/share/fonts/TTF/NotoSans-Regular.ttf",
        ],
        "liberation": [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/LiberationSans-Regular.ttf",
        ],
        "terminus": [
            "/usr/share/fonts/truetype/terminus/TerminusTTF.ttf",
            "/usr/share/fonts/TTF/TerminusTTF.ttf",
            "/usr/share/fonts/truetype/terminus-font/TerminusTTF.ttf",
        ],
    })

    @property
    def sep_y(self) -> int:
        return self.header_h + self.sep_padding_top

    @property
    def body_top(self) -> int:
        return self.sep_y + 1 + self.sep_padding_bottom

    @property
    def body_h(self) -> int:
        return self.height - self.body_top


_DEFAULT_THEME = Theme()


# ---------------------------------------------------------------------------
# Icon renderer – draws vector icons via PIL ImageDraw primitives
# ---------------------------------------------------------------------------

class IconRenderer:
    """Draws vector icons using PIL ImageDraw primitives.

    All coordinates are normalised to a 0-1 unit square and scaled to the
    requested pixel size, so icons look sharp at any size.
    """

    def __init__(self, size: int) -> None:
        self._size = size

    def render(self, name: str) -> Optional[Any]:
        """Return a mode-'1' PIL Image for *name*, or None if unknown."""
        fn = getattr(self, f"_icon_{name}", None)
        if fn is None:
            logger.debug("icon_unknown", icon=name)
            return None
        try:
            from PIL import Image, ImageDraw
            img = Image.new("1", (self._size, self._size), 0)
            draw = ImageDraw.Draw(img)
            fn(img, draw, self._size)
            return img
        except Exception as exc:
            logger.warning("icon_render_failed", icon=name, error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _s(v: float, size: int) -> int:
        return round(v * (size - 1))

    @classmethod
    def _xy(cls, x: float, y: float, size: int) -> Tuple[int, int]:
        return cls._s(x, size), cls._s(y, size)

    @classmethod
    def _box(cls, x0: float, y0: float, x1: float, y1: float, size: int) -> Tuple[int, int, int, int]:
        return cls._s(x0, size), cls._s(y0, size), cls._s(x1, size), cls._s(y1, size)

    # ------------------------------------------------------------------
    # Icons
    # ------------------------------------------------------------------

    @classmethod
    def _icon_play(cls, img: Any, draw: Any, s: int) -> None:
        draw.polygon([
            cls._xy(0.15, 0.08, s),
            cls._xy(0.15, 0.92, s),
            cls._xy(0.88, 0.50, s),
        ], fill=1)

    @classmethod
    def _icon_pause(cls, img: Any, draw: Any, s: int) -> None:
        draw.rectangle(cls._box(0.15, 0.10, 0.38, 0.90, s), fill=1)
        draw.rectangle(cls._box(0.62, 0.10, 0.85, 0.90, s), fill=1)

    @classmethod
    def _icon_stop(cls, img: Any, draw: Any, s: int) -> None:
        draw.rectangle(cls._box(0.15, 0.15, 0.85, 0.85, s), fill=1)

    @classmethod
    def _icon_mute(cls, img: Any, draw: Any, s: int) -> None:
        draw.polygon([
            cls._xy(0.08, 0.35, s),
            cls._xy(0.08, 0.65, s),
            cls._xy(0.30, 0.65, s),
            cls._xy(0.50, 0.85, s),
            cls._xy(0.50, 0.15, s),
            cls._xy(0.30, 0.35, s),
        ], fill=1)
        lw = max(2, s // 7)
        draw.line([
            cls._xy(0.55, 0.10, s),
            cls._xy(0.95, 0.90, s),
        ], fill=1, width=lw)

    @classmethod
    def _icon_moon(cls, img: Any, draw: Any, s: int) -> None:
        draw.ellipse(cls._box(0.10, 0.05, 0.90, 0.95, s), fill=1)
        draw.ellipse(cls._box(0.28, 0.00, 1.05, 0.75, s), fill=0)

    @classmethod
    def _icon_sleep_timer(cls, img: Any, draw: Any, s: int) -> None:
        cls._icon_moon(img, draw, s)

    @classmethod
    def _icon_error(cls, img: Any, draw: Any, s: int) -> None:
        lw = max(1, s // 10)
        draw.ellipse(cls._box(0.05, 0.05, 0.95, 0.95, s), outline=1, width=lw)
        draw.rectangle(cls._box(0.42, 0.22, 0.58, 0.60, s), fill=1)
        draw.rectangle(cls._box(0.42, 0.68, 0.58, 0.80, s), fill=1)

    @classmethod
    def _icon_repeat(cls, img: Any, draw: Any, s: int) -> None:
        lw = max(1, s // 8)
        draw.arc(cls._box(0.10, 0.15, 0.90, 0.85, s), start=200, end=340, fill=1, width=lw)
        draw.arc(cls._box(0.10, 0.15, 0.90, 0.85, s), start=20, end=160, fill=1, width=lw)
        draw.polygon([
            cls._xy(0.82, 0.15, s),
            cls._xy(0.95, 0.28, s),
            cls._xy(0.72, 0.28, s),
        ], fill=1)
        draw.polygon([
            cls._xy(0.18, 0.85, s),
            cls._xy(0.05, 0.72, s),
            cls._xy(0.28, 0.72, s),
        ], fill=1)

    @classmethod
    def _icon_shuffle(cls, img: Any, draw: Any, s: int) -> None:
        lw = max(1, s // 8)
        draw.line([cls._xy(0.10, 0.20, s), cls._xy(0.90, 0.80, s)], fill=1, width=lw)
        draw.line([cls._xy(0.10, 0.80, s), cls._xy(0.90, 0.20, s)], fill=1, width=lw)
        draw.polygon([
            cls._xy(0.90, 0.20, s),
            cls._xy(0.72, 0.20, s),
            cls._xy(0.90, 0.38, s),
        ], fill=1)
        draw.polygon([
            cls._xy(0.90, 0.80, s),
            cls._xy(0.72, 0.80, s),
            cls._xy(0.90, 0.62, s),
        ], fill=1)

    @classmethod
    def _icon_bluetooth(cls, img: Any, draw: Any, s: int) -> None:
        lw = max(1, s // 8)
        cx = cls._s(0.46, s)
        draw.line([(cx, cls._s(0.08, s)), (cx, cls._s(0.92, s))], fill=1, width=lw)
        draw.line([cls._xy(0.46, 0.08, s), cls._xy(0.85, 0.38, s)], fill=1, width=lw)
        draw.line([cls._xy(0.85, 0.38, s), cls._xy(0.46, 0.50, s)], fill=1, width=lw)
        draw.line([cls._xy(0.46, 0.50, s), cls._xy(0.85, 0.62, s)], fill=1, width=lw)
        draw.line([cls._xy(0.85, 0.62, s), cls._xy(0.46, 0.92, s)], fill=1, width=lw)


# ---------------------------------------------------------------------------
# DisplayRenderer
# ---------------------------------------------------------------------------

class DisplayRenderer:
    """Stateful renderer for a single SSD1306 OLED device.

    Caches fonts and rendered icon images to avoid re-computation on every frame.
    The public interface (init / clear / show_lines / show_areas / is_available)
    is identical to the previous free-function API.
    """

    def __init__(self, device: Any, theme: Theme = _DEFAULT_THEME) -> None:
        self._device = device
        self._theme = theme
        self._font_cache: Dict[str, Any] = {}
        self._icon_cache: Dict[str, Any] = {}
        self._icon_renderer = IconRenderer(theme.icon_size)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def clear(self) -> None:
        try:
            from luma.core.render import canvas
            with canvas(self._device) as draw:
                draw.rectangle(self._device.bounding_box, outline="black", fill="black")
        except Exception as exc:
            logger.warning("display_clear_failed", error=str(exc))

    def show_lines(self, lines: List[str]) -> None:
        """Legacy single-column text renderer (up to 4 lines)."""
        try:
            from luma.core.render import canvas
            display_lines = [s[:20] for s in lines[:4]]
            with canvas(self._device) as draw:
                for i, text in enumerate(display_lines):
                    if text:
                        draw.text((0, i * 14), text, fill="white")
        except Exception as exc:
            logger.warning("display_show_failed", error=str(exc))

    def render(
        self,
        areas: List[List[dict]],
        font_size: str = "medium",
        font: str = "default",
    ) -> None:
        """Render header (areas[0]) + left column (areas[1]) + right column (areas[2])."""
        pil_font = self._get_font(font_size, font)
        t = self._theme

        try:
            from PIL import Image, ImageDraw

            img = Image.new("1", (t.width, t.height), 0)
            draw = ImageDraw.Draw(img)

            header_items = areas[0][:6] if len(areas) > 0 else []
            body_left    = areas[1][:3] if len(areas) > 1 else []
            body_right   = areas[2][:3] if len(areas) > 2 else []

            self._render_header(img, draw, header_items, pil_font)
            self._render_separator(draw)
            self._render_column(img, draw, body_left,  col_x=0,       pil_font=pil_font)
            self._render_column(img, draw, body_right, col_x=t.col_w, pil_font=pil_font)

            self._device.display(img)
        except Exception as exc:
            logger.warning("display_render_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Layout: header
    # ------------------------------------------------------------------

    def _render_header(
        self, img: Any, draw: Any, items: List[dict], pil_font: Any
    ) -> None:
        t = self._theme
        items = [i for i in items if isinstance(i, dict)]
        n = len(items)
        if not n:
            return
        zone_w = t.width // n
        for idx, item in enumerate(items):
            self._render_item_in_slot(
                img, draw, item,
                x=idx * zone_w, y=0,
                slot_w=zone_w, slot_h=t.header_h,
                pil_font=pil_font,
            )

    # ------------------------------------------------------------------
    # Layout: separator
    # ------------------------------------------------------------------

    def _render_separator(self, draw: Any) -> None:
        t = self._theme
        draw.line([(0, t.sep_y), (t.width - 1, t.sep_y)], fill="white")

    # ------------------------------------------------------------------
    # Layout: body column
    # ------------------------------------------------------------------

    def _render_column(
        self,
        img: Any,
        draw: Any,
        items: List[dict],
        col_x: int,
        pil_font: Any,
    ) -> None:
        t = self._theme
        items = [i for i in items if isinstance(i, dict)]
        n = len(items)
        if not n:
            return

        slot_step = t.slot_h + (t.slot_gap if n > 1 else 0)
        block_h   = n * t.slot_h + ((n - 1) * t.slot_gap if n > 1 else 0)
        start_y   = t.body_top + max(0, (t.body_h - block_h) // 2)
        usable_w  = t.col_w - 2 * t.col_padding_x

        for idx, item in enumerate(items):
            self._render_item_in_slot(
                img, draw, item,
                x=col_x + t.col_padding_x,
                y=start_y + idx * slot_step,
                slot_w=usable_w,
                slot_h=t.slot_h,
                pil_font=pil_font,
            )

    # ------------------------------------------------------------------
    # Item dispatch
    # ------------------------------------------------------------------

    def _render_item_in_slot(
        self,
        img: Any, draw: Any, item: dict,
        x: int, y: int,
        slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        t = item.get("type", "")
        if t == "icon":
            self._render_icon(img, draw, item.get("value", ""), x, y, slot_w, slot_h, pil_font)
        elif t == "sleep_timer":
            self._render_sleep_timer(img, draw, item.get("minutes", 0), x, y, slot_w, slot_h, pil_font)
        elif t == "text":
            self._render_text(draw, item.get("value", ""), x, y, slot_w, slot_h, pil_font)

    # ------------------------------------------------------------------
    # Item renderers
    # ------------------------------------------------------------------

    def _render_icon(
        self,
        img: Any, draw: Any, icon_name: str,
        x: int, y: int, slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        sz = self._theme.icon_size
        icon_img = self._get_icon(icon_name)
        if icon_img is not None:
            img.paste(icon_img, (x + (slot_w - sz) // 2, y + (slot_h - sz) // 2))
        else:
            self._render_text(draw, icon_name[:3].upper(), x, y, slot_w, slot_h, pil_font)

    def _render_sleep_timer(
        self,
        img: Any, draw: Any, minutes: int,
        x: int, y: int, slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        t = self._theme
        icon_img = self._get_icon("sleep_timer")
        text = f"{minutes}m"
        tw, th = self._measure_text(draw, text, pil_font)
        icon_part = (t.icon_size + t.sleep_icon_text_gap) if icon_img else 0
        total_w   = icon_part + tw
        sx        = x + max(0, (slot_w - total_w) // 2)
        cy        = y + slot_h // 2

        if icon_img:
            img.paste(icon_img, (sx, cy - t.icon_size // 2))
            sx += icon_part
        if text:
            ty = cy - th // 2
            if pil_font:
                draw.text((sx, ty), text, fill="white", font=pil_font)
            else:
                draw.text((sx, ty), text, fill="white")

    def _render_text(
        self,
        draw: Any, text: str,
        x: int, y: int, slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        if not text:
            return
        text = text[:10]
        tw, th = self._measure_text(draw, text, pil_font)
        tx = x + (slot_w - tw) // 2
        ty = y + (slot_h - th) // 2
        if pil_font:
            draw.text((tx, ty), text, fill="white", font=pil_font)
        else:
            draw.text((tx, ty), text, fill="white")

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------

    def _measure_text(self, draw: Any, text: str, font: Any) -> Tuple[int, int]:
        if not text:
            return 0, 0
        if font is None:
            return len(text) * 6, 10
        try:
            bb = draw.textbbox((0, 0), text, font=font)
            return bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            return len(text) * 6, 10

    def _get_font(self, font_size: str = "medium", font: str = "default") -> Any:
        key = f"{font_size}:{font}"
        if key not in self._font_cache:
            self._font_cache[key] = self._load_font(font_size, font)
        return self._font_cache[key]

    def _load_font(self, font_size: str, font: str) -> Any:
        try:
            from PIL import ImageFont
        except ImportError:
            return None

        size = self._theme.font_sizes.get(font_size, 12)

        if font == "default":
            return ImageFont.load_default()

        paths = self._theme.font_paths.get(font, [])
        for path in paths:
            if not os.path.isfile(path):
                continue
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

        logger.warning("font_not_found", font=font, searched=paths)
        return ImageFont.load_default()

    # ------------------------------------------------------------------
    # Icon helpers
    # ------------------------------------------------------------------

    def _get_icon(self, name: str) -> Any:
        if name not in self._icon_cache:
            self._icon_cache[name] = self._icon_renderer.render(name)
        return self._icon_cache[name]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_renderer: Optional[DisplayRenderer] = None


# ---------------------------------------------------------------------------
# Public API – identical to original free-function interface
# ---------------------------------------------------------------------------

def init(i2c_bus: int, i2c_address: int) -> bool:
    """Initialize SSD1306 device. Returns True if successful."""
    global _renderer
    if _renderer is not None:
        return True
    try:
        from luma.core.interface.serial import i2c as luma_i2c
        from luma.oled.device import ssd1306

        serial = luma_i2c(port=i2c_bus, address=i2c_address)
        device = ssd1306(serial)
        _renderer = DisplayRenderer(device)
        logger.info("display_initialized", bus=i2c_bus, address=i2c_address)
        return True
    except Exception as exc:
        logger.warning("display_init_failed", bus=i2c_bus, address=i2c_address, error=str(exc))
        return False


def clear() -> None:
    if _renderer is not None:
        _renderer.clear()


def show_lines(lines: List[str]) -> None:
    """Legacy single-column text renderer. No-op if display unavailable."""
    if _renderer is not None:
        _renderer.show_lines(lines)


def show_areas(
    areas: List[List[dict]],
    font_size: str = "medium",
    font: str = "default",
) -> None:
    """Render header (areas[0]) + left column (areas[1]) + right column (areas[2])."""
    if _renderer is not None:
        _renderer.render(areas, font_size=font_size, font=font)


def is_available() -> bool:
    """Return True if display hardware was successfully initialized."""
    return _renderer is not None
