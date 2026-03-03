"""OLED display controller (SSD1306 over I2C): header (full width) + 2 columns."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
_ASSETS_ICONS: Path = Path(__file__).resolve().parent.parent / "assets" / "icons"

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

    # Separator line
    sep_padding_top: int = 1    # gap between last header pixel and separator line
    sep_padding_bottom: int = 3 # gap between separator line and first body pixel

    # Body columns
    col_w: int = 64             # each column is half the display width
    col_padding_x: int = 4      # left/right inner padding inside each column
    col_padding_y: int = 3      # top/bottom inner padding inside each column

    # Slots
    slot_h: int = 16
    slot_gap: int = 5           # vertical gap between slots when >1 item per column

    # Icons
    icon_size: int = 14         # render icons at 14x14 for a cleaner look
    sleep_icon_text_gap: int = 3

    # Font sizes (TTF pixel height)
    font_sizes: Dict[str, int] = field(default_factory=lambda: {
        "small": 9,
        "medium": 12,
        "large": 14,
    })

    # TTF font paths (tried in order)
    font_paths: List[str] = field(default_factory=lambda: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ])

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
# DisplayRenderer
# ---------------------------------------------------------------------------

class DisplayRenderer:
    """Stateful renderer for a single SSD1306 OLED device.

    Holds font and icon caches to avoid repeated disk I/O.
    Public interface mirrors the legacy free-function API.
    """

    def __init__(self, device: Any, theme: Theme = _DEFAULT_THEME) -> None:
        self._device = device
        self._theme = theme
        self._font_cache: Dict[str, Any] = {}
        self._icon_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Fill the display with black."""
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
            line_height = 14
            max_chars = 20
            display_lines = [s[:max_chars] for s in lines[:4]]
            with canvas(self._device) as draw:
                for i, text in enumerate(display_lines):
                    if text:
                        draw.text((0, i * line_height), text, fill="white")
        except Exception as exc:
            logger.warning("display_show_failed", error=str(exc))

    def render(self, areas: List[List[dict]], font_size: str = "medium", font: str = "default") -> None:
        """Render header (areas[0]) + left column (areas[1]) + right column (areas[2]).

        Each item dict:
          {'type': 'text',        'value': '...'}
          {'type': 'icon',        'value': 'play'|'pause'|'stop'|'mute'|...}
          {'type': 'sleep_timer', 'minutes': N}
        """
        t = self._theme
        pil_font = self._get_font(font_size, font)

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

    def _render_header(self, img: Any, draw: Any, items: List[dict], pil_font: Any) -> None:
        t = self._theme
        items = [i for i in items if isinstance(i, dict)]
        n = len(items)
        if n == 0:
            return
        zone_w = t.width // n
        for idx, item in enumerate(items):
            zone_x = idx * zone_w
            self._render_item_in_slot(
                img, draw, item,
                x=zone_x, y=0,
                slot_w=zone_w, slot_h=t.header_h,
                pil_font=pil_font,
            )

    # ------------------------------------------------------------------
    # Layout: separator line
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
        if n == 0:
            return

        slot_step = t.slot_h + (t.slot_gap if n > 1 else 0)
        block_h = n * t.slot_h + ((n - 1) * t.slot_gap if n > 1 else 0)
        # Vertically center the block within the usable body area
        start_y = t.body_top + max(0, (t.body_h - block_h) // 2)

        usable_w = t.col_w - 2 * t.col_padding_x

        for slot_idx, item in enumerate(items):
            slot_y = start_y + slot_idx * slot_step
            self._render_item_in_slot(
                img, draw, item,
                x=col_x + t.col_padding_x,
                y=slot_y,
                slot_w=usable_w,
                slot_h=t.slot_h,
                pil_font=pil_font,
            )

    # ------------------------------------------------------------------
    # Item rendering – dispatches by type
    # ------------------------------------------------------------------

    def _render_item_in_slot(
        self,
        img: Any,
        draw: Any,
        item: dict,
        x: int,
        y: int,
        slot_w: int,
        slot_h: int,
        pil_font: Any,
    ) -> None:
        item_type = item.get("type", "")
        if item_type == "icon":
            self._render_icon_item(img, draw, item.get("value", ""), x, y, slot_w, slot_h, pil_font)
        elif item_type == "sleep_timer":
            self._render_sleep_timer_item(img, draw, item.get("minutes", 0), x, y, slot_w, slot_h, pil_font)
        elif item_type == "text":
            self._render_text_item(draw, item.get("value", ""), x, y, slot_w, slot_h, pil_font)

    def _render_icon_item(
        self,
        img: Any,
        draw: Any,
        icon_name: str,
        x: int, y: int,
        slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        t = self._theme
        icon_img = self._get_icon(icon_name)
        if icon_img is not None:
            ix = x + (slot_w - t.icon_size) // 2
            iy = y + (slot_h - t.icon_size) // 2
            img.paste(icon_img, (ix, iy))
        else:
            # Graceful text fallback: show abbreviated icon name
            fallback = icon_name[:3].upper() if icon_name else "?"
            self._render_text_item(draw, fallback, x, y, slot_w, slot_h, pil_font)

    def _render_sleep_timer_item(
        self,
        img: Any,
        draw: Any,
        minutes: int,
        x: int, y: int,
        slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        t = self._theme
        icon_img = self._get_icon("sleep_timer")
        text = f"{minutes}m"

        text_w, text_h = self._measure_text(draw, text, pil_font)
        icon_part_w = (t.icon_size + t.sleep_icon_text_gap) if icon_img is not None else 0
        total_w = icon_part_w + text_w

        start_x = x + max(0, (slot_w - total_w) // 2)
        center_y = y + slot_h // 2

        if icon_img is not None:
            iy = center_y - t.icon_size // 2
            img.paste(icon_img, (start_x, iy))
            start_x += icon_part_w

        if text and pil_font is not None:
            ty = center_y - text_h // 2
            draw.text((start_x, ty), text, fill="white", font=pil_font)
        elif text:
            draw.text((start_x, center_y - 5), text, fill="white")

    def _render_text_item(
        self,
        draw: Any,
        text: str,
        x: int, y: int,
        slot_w: int, slot_h: int,
        pil_font: Any,
    ) -> None:
        if not text:
            return
        text = text[:10]
        if pil_font is not None:
            tw, th = self._measure_text(draw, text, pil_font)
            tx = x + (slot_w - tw) // 2
            ty = y + (slot_h - th) // 2
            draw.text((tx, ty), text, fill="white", font=pil_font)
        else:
            # PIL default font fallback
            tw = len(text) * 6
            tx = x + (slot_w - tw) // 2
            ty = y + (slot_h - 10) // 2
            draw.text((tx, ty), text, fill="white")

    # ------------------------------------------------------------------
    # Helpers: font & icon loading
    # ------------------------------------------------------------------

    def _measure_text(self, draw: Any, text: str, font: Any) -> tuple:
        """Return (width, height) of text with the given font."""
        if font is None:
            return len(text) * 6, 10
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            return len(text) * 6, 10

    def _get_font(self, font_size: str = "medium", font: str = "default") -> Any:
        """Return a cached PIL ImageFont."""
        cache_key = f"{font_size}:{font}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        result = self._load_font(font_size, font)
        self._font_cache[cache_key] = result
        return result

    def _load_font(self, font_size: str, font: str) -> Any:
        try:
            from PIL import ImageFont
        except ImportError:
            return None

        size = self._theme.font_sizes.get(font_size, 12)

        if font == "default":
            return ImageFont.load_default()

        want_mono = font == "mono"
        for path in self._theme.font_paths:
            if not os.path.isfile(path):
                continue
            if ("Mono" in path) != want_mono:
                continue
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

        return ImageFont.load_default()

    def _get_icon(self, icon_name: str) -> Any:
        """Return a cached icon_size x icon_size mode-'1' PIL Image, or None."""
        if icon_name in self._icon_cache:
            return self._icon_cache[icon_name]

        img = self._load_icon(icon_name)
        self._icon_cache[icon_name] = img
        return img

    def _load_icon(self, icon_name: str) -> Optional[Any]:
        """Load icon PNG from assets. Returns None if unavailable."""
        try:
            from PIL import Image
        except ImportError:
            return None

        filename = "icon_moon.png" if icon_name == "sleep_timer" else f"icon_{icon_name}.png"
        path = _ASSETS_ICONS / filename
        if not path.is_file():
            logger.debug("icon_not_found", icon=icon_name, path=str(path))
            return None
        try:
            size = self._theme.icon_size
            im = Image.open(path).convert("1")
            if im.size != (size, size):
                im = im.resize((size, size), Image.Resampling.LANCZOS)
            return im
        except Exception as exc:
            logger.debug("icon_load_failed", icon=icon_name, path=str(path), error=str(exc))
            return None


# ---------------------------------------------------------------------------
# Module-level device & renderer (singleton)
# ---------------------------------------------------------------------------

_renderer: Optional[DisplayRenderer] = None


# ---------------------------------------------------------------------------
# Public API  (unchanged from original – main.py imports these)
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
        logger.warning(
            "display_init_failed",
            bus=i2c_bus,
            address=i2c_address,
            error=str(exc),
        )
        return False


def clear() -> None:
    """Clear the display."""
    if _renderer is not None:
        _renderer.clear()


def show_lines(lines: List[str]) -> None:
    """Render up to 4 lines of text (legacy single-column). No-op if display not available."""
    if _renderer is not None:
        _renderer.show_lines(lines)


def show_areas(
    areas: List[List[dict]],
    font_size: str = "medium",
    font: str = "default",
) -> None:
    """Render header (areas[0]) full width + 2 columns (areas[1], areas[2])."""
    if _renderer is not None:
        _renderer.render(areas, font_size=font_size, font=font)


def is_available() -> bool:
    """Return True if display hardware was successfully initialized."""
    return _renderer is not None
