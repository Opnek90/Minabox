"""Sending only what changed.

A whole frame is 1024 bytes and holds the I2C bus for 92 ms at the 100 kHz it
runs at - time the RFID reader spends unable to speak. A rectangle costs its
own area instead: a 32x16 sprite is 64 bytes, or 5.8 ms. That difference is
what makes a moving idle screen possible at all.

The risk is that this reaches past luma's public API. These tests hold the two
together: the packing is checked against luma's own offset and mask formulas,
and the fallback is checked by taking the internals away.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from display_service.infrastructure.display_controller import (
    MAX_PARTIAL_BYTES,
    DisplayRenderer,
)

W, H = 128, 64
COLUMNADDR, PAGEADDR = 0x21, 0x22


class FakeDevice:
    """Records what a real SSD1306 would have been told."""

    def __init__(self, *, partial: bool = True) -> None:
        self.commands: list[tuple] = []
        self.data_blocks: list[list[int]] = []
        self.full_frames = 0
        self.size = (W, H)
        self.mode = "1"
        self.rotate = 0
        self.bounding_box = (0, 0, W - 1, H - 1)
        if partial:
            self._const = SimpleNamespace(COLUMNADDR=COLUMNADDR, PAGEADDR=PAGEADDR)
            self._colstart = 0
            self._pages = H // 8

    @staticmethod
    def preprocess(image):
        return image

    def command(self, *args) -> None:
        self.commands.append(args)

    def data(self, values) -> None:
        self.data_blocks.append(list(values))

    def display(self, image) -> None:
        self.full_frames += 1

    def cleanup(self) -> None:
        pass


def frame(draw_fn=None):
    img = Image.new("1", (W, H), 0)
    if draw_fn:
        draw_fn(ImageDraw.Draw(img))
    return img


def luma_buffer(img):
    """luma's own packing, transcribed from ssd1306.__init__ and display().

    Kept as the specification: if a luma upgrade changes it, this test is
    where the two drift apart, not the panel.
    """
    mask = [1 << (i // W) % 8 for i in range(W * H)]
    offsets = [(W * (i // (W * 8))) + (i % W) for i in range(W * H)]
    buf = bytearray(W * (H // 8))
    # luma walks image.getdata(); reading the same pixels through load()
    # keeps the two offset formulas above - the part that matters - identical
    # without inheriting a Pillow deprecation warning.
    pixels = img.load()
    for y in range(H):
        for x in range(W):
            if pixels[x, y]:
                index = y * W + x
                buf[offsets[index]] |= mask[index]
    return buf


class TestPacking:
    def test_a_whole_frame_matches_luma_byte_for_byte(self):
        img = frame(lambda d: (
            d.ellipse([10, 5, 60, 40], fill=1),
            d.rectangle([70, 20, 120, 55], outline=1, width=2),
            d.text((5, 48), "Minabox", fill=1),
        ))
        packed = DisplayRenderer._pack(img, 0, W - 1, 0, H // 8 - 1)
        assert bytes(packed) == bytes(luma_buffer(img))

    @pytest.mark.parametrize(
        "x0,x1,p0,p1", [(32, 63, 2, 3), (0, 7, 0, 0), (100, 127, 5, 7), (64, 64, 4, 4)]
    )
    def test_a_rectangle_matches_the_same_slice_of_luma(self, x0, x1, p0, p1):
        img = frame(lambda d: (
            d.ellipse([5, 5, 120, 58], outline=1, width=3),
            d.text((20, 20), "Knuffel", fill=1),
        ))
        buf = luma_buffer(img)
        expected = bytearray()
        for page in range(p0, p1 + 1):
            expected += buf[page * W + x0 : page * W + x1 + 1]
        assert bytes(DisplayRenderer._pack(img, x0, x1, p0, p1)) == bytes(expected)


class TestWhatGoesOverTheWire:
    def test_the_first_frame_is_a_whole_one(self):
        """Nothing is known about the glass yet, so nothing can be diffed."""
        device = FakeDevice()
        DisplayRenderer(device).show_image(frame())
        assert device.full_frames == 1
        assert device.data_blocks == []

    def test_a_small_change_sends_a_rectangle(self):
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))

        assert device.full_frames == 1, "the second push should not be a whole frame"
        assert len(device.data_blocks) == 1
        # 32 columns across two pages.
        assert len(device.data_blocks[0]) == 64

    def test_the_window_matches_the_change(self):
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))

        assert device.commands[-1] == (COLUMNADDR, 40, 71, PAGEADDR, 2, 3)

    def test_a_change_inside_one_page_still_takes_the_whole_page(self):
        """The controller addresses eight rows at a time; there is no finer cut."""
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.show_image(frame(lambda d: d.line([(10, 3), (20, 3)], fill=1)))

        _, x0, x1, _, p0, p1 = device.commands[-1]
        assert (p0, p1) == (0, 0)
        assert x0 <= 10 and x1 >= 20

    def test_an_identical_frame_sends_nothing_at_all(self):
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        same = frame(lambda d: d.text((5, 5), "gleich", fill=1))
        renderer.show_image(same)
        before = len(device.commands)
        renderer.show_image(same.copy())

        assert device.full_frames == 1
        assert device.data_blocks == []
        assert len(device.commands) == before

    def test_a_big_change_goes_back_to_a_whole_frame(self):
        """Past a point the saving no longer pays for the diffing, and luma's
        own path is both faster and better tested."""
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.show_image(frame(lambda d: d.rectangle([0, 0, W - 1, H - 1], fill=1)))

        assert device.full_frames == 2
        assert device.data_blocks == []

    def test_the_threshold_is_where_it_says_it_is(self):
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        # Six pages of 127 columns is 762 bytes, just inside the limit.
        renderer.show_image(frame(lambda d: d.rectangle([0, 0, 126, 47], fill=1)))

        assert 127 * 6 <= MAX_PARTIAL_BYTES
        assert device.full_frames == 1
        assert len(device.data_blocks[0]) == 127 * 6


class TestFallback:
    def test_a_device_without_the_internals_gets_whole_frames(self):
        """A luma upgrade that renames them must slow the panel down, not
        break it."""
        device = FakeDevice(partial=False)
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))

        assert device.full_frames == 2
        assert device.data_blocks == []

    def test_clearing_forces_the_next_frame_to_be_whole(self):
        """clear() writes to the panel behind show_image()'s back."""
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())
        renderer.clear()
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))

        assert device.full_frames == 2

    def test_a_failed_push_forgets_what_was_on_the_glass(self):
        device = FakeDevice()
        renderer = DisplayRenderer(device)
        renderer.show_image(frame())

        def boom(*_args, **_kwargs):
            raise OSError("i2c gone")

        device.command = boom
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))

        device.command = FakeDevice.command.__get__(device)
        renderer.show_image(frame(lambda d: d.rectangle([40, 16, 71, 31], fill=1)))
        assert device.full_frames == 2, "the diff was taken against a lost frame"


class TestWaveFitsThePanel:
    """PIL clips silently, so an arm drawn past the edge is simply not there."""

    @staticmethod
    def _lit(mood, x):
        from display_service.core.idle_animation import SIZE
        from display_service.render import knuffel

        img = frame(lambda d: knuffel.draw(d, x, 12, SIZE, mood))
        pixels = img.load()
        return sum(
            1
            for px in range(img.width)
            for py in range(img.height)
            if pixels[px, py]
        )

    def test_a_waving_knuffel_at_the_far_edge_is_not_cut_off(self):
        from display_service.core.idle_animation import BOUNDS
        from display_service.render import knuffel

        _, _, right, _ = BOUNDS
        for mood in knuffel.WAVING:
            assert self._lit(mood, right) == self._lit(mood, 2), mood

    def test_the_overhang_scales_with_him(self):
        from display_service.render import knuffel

        assert knuffel.wave_overhang(80) > knuffel.wave_overhang(38) > 0
