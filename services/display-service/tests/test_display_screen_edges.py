"""Nothing any screen draws may touch the edge of the panel.

PIL crops silently, so a glyph or a word that overflows is not an error - it is
simply missing a piece on the glass, and only on the glass. That has now caught
three separate screens during this work, so it is checked in one place for all
of them rather than remembered per screen.
"""

from __future__ import annotations

import pytest

from display_service.core.idle_animation import BOUNDS, IdleAnimation
from display_service.render import idle, knuffel, quota_over, tag_blocked, unknown_tag
from display_service.render.idle import strip_width
from display_service.render.playing import PlayingView
from display_service.render.playing import render as render_playing
from display_service.render.primitives import HEIGHT, WIDTH
from display_service.render.volume import VolumeView
from display_service.render.volume import render as render_volume

M = 60_000
LONG_TITLE = "Der Grueffelo und das Grueffelokind lesen ein Buch"


def _idle_frame(mood: str, marks_showing: tuple[str, ...] = ()) -> object:
    """Knuffel in his far corner, in the pose that reaches furthest."""
    animation = IdleAnimation(now=0.0)
    animation.set_reserved(strip_width(marks_showing), 0.0)
    pose = animation.pose()
    far = type(pose)(x=BOUNDS[2] - strip_width(marks_showing), y=BOUNDS[1], mood=mood)
    return idle.render(far, marks_showing)


def _frames():
    yield "unknown_tag", unknown_tag.render()
    yield "quota_over", quota_over.render()
    yield "tag_blocked", tag_blocked.render()
    yield "tag_blocked+name", tag_blocked.render("Bibi Blocksberg und Kartoffelbrei")
    for volume in range(20, 41, 5):
        # Every singing level: the top note climbs into the corner, so this is
        # where an off-by-one runs a note off the panel.
        yield f"volume:{volume}", render_volume(VolumeView(volume, 20, 40))
    yield "volume_muted", render_volume(VolumeView(30, 20, 40, muted=True))
    yield "playing", render_playing(PlayingView(LONG_TITLE, 5 * M, 10 * M))
    yield "playing_muted", render_playing(
        PlayingView("Ein Lama in Yokohama", 5 * M, 10 * M, muted=True)
    )
    for mood in knuffel.MOODS:
        yield f"idle:{mood}", _idle_frame(mood)
    yield "idle+marks", _idle_frame(knuffel.WAVE_UP, ("error", "sleep_timer"))


def lit(img, box):
    x0, y0, x1, y1 = box
    pixels = img.load()
    return sum(1 for x in range(x0, x1) for y in range(y0, y1) if pixels[x, y])


_CASES = list(_frames())


@pytest.mark.parametrize("name,img", _CASES, ids=[c[0] for c in _CASES])
def test_nothing_touches_the_edges(name, img):
    assert img.size == (WIDTH, HEIGHT), name
    assert lit(img, (0, 0, 1, HEIGHT)) == 0, f"{name}: left"
    assert lit(img, (WIDTH - 1, 0, WIDTH, HEIGHT)) == 0, f"{name}: right"
    assert lit(img, (0, 0, WIDTH, 1)) == 0, f"{name}: top"
    assert lit(img, (0, HEIGHT - 1, WIDTH, HEIGHT)) == 0, f"{name}: bottom"
