"""The panel itself: opening it, and getting a finished frame onto it.

What to draw lives in ``display_service.render``; this module knows only
how to put a whole 128x64 image on the glass and how to send as little of
it as possible.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Partial updates
# ---------------------------------------------------------------------------

# A whole frame is 1024 bytes, and at the 100 kHz this bus runs at that is
# 92 ms during which the RFID reader cannot get a word in. The SSD1306 can be
# told to accept a rectangle instead, so a moving sprite costs its own area:
# 32x16 px is 64 bytes, or 5.8 ms.
#
# Reaching a rectangle needs these, and only the last two are public API. They
# are probed once at init and the renderer falls back to whole frames if a luma
# upgrade renames any of them - a slower panel rather than a broken one.
_PARTIAL_ATTRS = ("_const", "_colstart", "_pages", "command", "data")

# Above this the saving no longer pays for the diffing and the extra command
# bytes, and luma's own full-frame path is both faster and better tested.
MAX_PARTIAL_BYTES = 768


# ---------------------------------------------------------------------------
# DisplayRenderer
# ---------------------------------------------------------------------------

class DisplayRenderer:
    """One SSD1306 panel, and a record of what is currently on it.

    The record is what makes partial updates possible: show_image() diffs the
    frame it is handed against the last one it sent and pushes only the
    rectangle that changed.
    """

    def __init__(self, device: Any) -> None:
        self._device = device
        # The last frame actually on the glass, in physical orientation. None
        # means "unknown", which forces the next push to be a whole frame.
        self._last_frame: Any = None
        self._partial_ok = all(hasattr(device, name) for name in _PARTIAL_ATTRS)
        if not self._partial_ok:
            logger.info(
                "display_partial_updates_unavailable",
                hint="Whole frames only. Check luma for renamed internals.",
            )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self.forget_frame()
        try:
            from luma.core.render import canvas
            with canvas(self._device) as draw:
                draw.rectangle(self._device.bounding_box, outline="black", fill="black")
        except Exception as exc:
            logger.warning("display_clear_failed", error=str(exc))

    def close(self) -> None:
        """Blank the panel and close the underlying I2C handle."""
        self.forget_frame()
        self._device.cleanup()

    def show_image(self, img: Any) -> None:
        """Push a finished frame, sending only the part of it that changed.

        The screen renderers in ``display_service.render`` build whole frames;
        this is the way onto the device for them, bypassing the widget grid.
        What actually goes over the wire is worked out here rather than by the
        caller, so every screen benefits without knowing about it - a clock
        ticking over costs its own two lines, not the whole panel.
        """
        try:
            frame = self._device.preprocess(img)
            if not self._push_region(frame):
                self._device.display(img)
            self._last_frame = frame.copy()
        except Exception as exc:
            logger.warning("display_show_image_failed", error=str(exc))
            # What is on the glass is now anyone's guess.
            self._last_frame = None

    def _push_region(self, frame: Any) -> bool:
        """Send just the changed rectangle. False asks for a whole frame."""
        if not self._partial_ok or self._last_frame is None:
            return False
        if frame.size != self._last_frame.size or frame.mode != self._last_frame.mode:
            return False

        from PIL import ImageChops

        bbox = ImageChops.difference(frame, self._last_frame).getbbox()
        if bbox is None:
            # Identical to what is already showing. The render loop's
            # fingerprint normally catches this earlier; when it does not,
            # sending nothing is still the right answer.
            return True

        x0, y0, x1, y1 = bbox  # x1 and y1 are exclusive
        page_start, page_end = y0 // 8, (y1 - 1) // 8
        columns, pages = x1 - x0, page_end - page_start + 1
        if columns * pages > MAX_PARTIAL_BYTES:
            return False

        device = self._device
        device.command(
            device._const.COLUMNADDR,
            device._colstart + x0,
            device._colstart + x1 - 1,
            device._const.PAGEADDR,
            page_start,
            page_end,
        )
        device.data(self._pack(frame, x0, x1 - 1, page_start, page_end))
        return True

    @staticmethod
    def _pack(
        frame: Any, x0: int, x1: int, page_start: int, page_end: int
    ) -> list[int]:
        """Bytes for one rectangle, in the order the SSD1306 consumes them.

        One byte is eight vertically stacked pixels of a single column, the
        lowest row in the highest bit; the controller walks columns first and
        then wraps to the next page. Which is what luma's own offset table
        encodes, and tests/test_display_partial_update.py holds the two
        together.
        """
        pixels = frame.load()
        packed: list[int] = []
        for page in range(page_start, page_end + 1):
            top = page * 8
            for x in range(x0, x1 + 1):
                byte = 0
                for bit in range(8):
                    if pixels[x, top + bit]:
                        byte |= 1 << bit
                packed.append(byte)
        return packed

    def set_contrast(self, level: int) -> None:
        """Set the panel brightness. One command, two bytes on the bus."""
        try:
            self._device.contrast(max(0, min(255, level)))
        except Exception as exc:
            logger.warning("display_contrast_failed", level=level, error=str(exc))

    def set_visible(self, visible: bool) -> None:
        """Switch the panel on or off without closing it.

        Off is genuinely off - luma puts the device into low-power sleep - and
        the frame buffer survives, so switching back on shows what was there.
        Which is why the record of it is kept rather than forgotten.
        """
        try:
            if visible:
                self._device.show()
            else:
                self._device.hide()
        except Exception as exc:
            logger.warning("display_visibility_failed", visible=visible, error=str(exc))

    def forget_frame(self) -> None:
        """Drop the record of what is on the glass, forcing a whole frame next.

        Anything that writes to the panel behind show_image()'s back has to say
        so, or the next diff is taken against a frame that is no longer there.
        """
        self._last_frame = None

    def show_lines(self, lines: list[str]) -> None:
        """Legacy single-column text renderer (up to 4 lines)."""
        self.forget_frame()
        try:
            from luma.core.render import canvas
            display_lines = [s[:20] for s in lines[:4]]
            with canvas(self._device) as draw:
                for i, text in enumerate(display_lines):
                    if text:
                        draw.text((0, i * 14), text, fill="white")
        except Exception as exc:
            logger.warning("display_show_failed", error=str(exc))

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_renderer: DisplayRenderer | None = None


# ---------------------------------------------------------------------------
# Public API – identical to original free-function interface
# ---------------------------------------------------------------------------

def init(i2c_bus: int, i2c_address: int, *, log_failure: bool = True) -> bool:
    """Initialize SSD1306 device. Returns True if successful.

    ``log_failure`` is what lets the render loop retry every 30 seconds without
    filling the log: the first failure is reported at startup, every retry
    after that is a debug line.
    """
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
        log = logger.warning if log_failure else logger.debug
        log(
            "display_init_failed",
            bus=i2c_bus,
            address=i2c_address,
            error=str(exc),
            hint="Display disabled. Check the I2C bus and address in display.json.",
        )
        return False


def shutdown() -> None:
    """Release the device so a later init() can open a different address.

    Without this there is no way back out of init(): the module-level renderer
    was only ever assigned, so changing i2c_bus or i2c_address in the config
    kept talking to the old address until the container was restarted.

    luma's own ``cleanup()`` blanks the panel, puts it into low-power mode and
    closes the I2C handle. Failure here is not worth propagating - the renderer
    is dropped either way, and the caller's next init() is what matters.
    """
    global _renderer
    renderer, _renderer = _renderer, None
    if renderer is None:
        return
    try:
        renderer.close()
        logger.info("display_shutdown")
    except Exception as exc:
        logger.warning("display_shutdown_failed", error=str(exc))


def clear() -> None:
    if _renderer is not None:
        _renderer.clear()


def show_image(img: Any) -> None:
    """Push a pre-rendered frame. No-op if display unavailable."""
    if _renderer is not None:
        _renderer.show_image(img)


def set_contrast(level: int) -> None:
    """Set the panel brightness. No-op if display unavailable."""
    if _renderer is not None:
        _renderer.set_contrast(level)


def set_visible(visible: bool) -> None:
    """Switch the panel on or off. No-op if display unavailable."""
    if _renderer is not None:
        _renderer.set_visible(visible)


def show_lines(lines: list[str]) -> None:
    """Legacy single-column text renderer. No-op if display unavailable."""
    if _renderer is not None:
        _renderer.show_lines(lines)


def is_available() -> bool:
    """Return True if display hardware was successfully initialized."""
    return _renderer is not None
