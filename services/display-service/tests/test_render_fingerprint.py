"""Tests for the display render fingerprint.

The OLED shares /dev/i2c-1 with the PN532 RFID reader, so the render loop only
pushes a frame when the content actually changed. The fingerprint is what that
decision rests on: it must be stable for identical content and must notice
every field that ends up on the panel.
"""

from __future__ import annotations

from display_service.main import DisplayService

fp = DisplayService._render_fingerprint


def _areas(clock="14:05", volume=35):
    return [
        [{"type": "text", "value": clock}, {"type": "icon", "value": "play"}],
        [{"type": "volume", "value": volume}],
        [],
    ]


def test_identical_content_gives_identical_fingerprint():
    assert fp(_areas(), "medium", "default") == fp(_areas(), "medium", "default")


def test_stable_across_key_order():
    a = [[{"type": "text", "value": "x"}], [], []]
    b = [[{"value": "x", "type": "text"}], [], []]
    assert fp(a, "medium", "default") == fp(b, "medium", "default")


def test_clock_change_is_noticed():
    assert fp(_areas(clock="14:05"), "medium", "default") != fp(
        _areas(clock="14:06"), "medium", "default"
    )


def test_volume_change_is_noticed():
    assert fp(_areas(volume=35), "medium", "default") != fp(
        _areas(volume=40), "medium", "default"
    )


def test_font_size_change_is_noticed():
    assert fp(_areas(), "medium", "default") != fp(_areas(), "large", "default")


def test_font_change_is_noticed():
    assert fp(_areas(), "medium", "default") != fp(_areas(), "medium", "mono")


def test_element_order_is_noticed():
    a = [[{"type": "icon", "value": "play"}, {"type": "icon", "value": "mute"}], [], []]
    b = [[{"type": "icon", "value": "mute"}, {"type": "icon", "value": "play"}], [], []]
    assert fp(a, "medium", "default") != fp(b, "medium", "default")


def test_element_moving_between_areas_is_noticed():
    a = [[{"type": "icon", "value": "play"}], [], []]
    b = [[], [{"type": "icon", "value": "play"}], []]
    assert fp(a, "medium", "default") != fp(b, "medium", "default")


def test_unserialisable_values_do_not_raise():
    class Weird:
        def __str__(self) -> str:
            return "weird"

    assert fp([[{"type": "x", "value": Weird()}], [], []], "medium", "default")
