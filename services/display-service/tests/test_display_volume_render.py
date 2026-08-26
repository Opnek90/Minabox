"""Pixel-level checks on the volume HUD.

The renderer touches no hardware, so these run anywhere. They assert on what
the panel would actually show rather than on the calls made to get there.
"""

from display_service.render.primitives import HEIGHT, WIDTH
from display_service.render.volume import VolumeView, render

BLOCK_BAND_Y = 50  # inside the block row, clear of its top and bottom edges


def lit_runs(img, y):
    """Number of separate lit stretches along row *y*.

    A filled block is one stretch; an empty block is two, its left and right
    border. So a row of *n* blocks with *f* filled gives f + 2*(n-f).
    """
    pixels = img.load()
    runs, previous = 0, 0
    for x in range(img.width):
        value = pixels[x, y]
        if value and not previous:
            runs += 1
        previous = value
    return runs


def lit_count(img, box=None):
    x0, y0, x1, y1 = box or (0, 0, img.width, img.height)
    pixels = img.load()
    return sum(1 for x in range(x0, x1) for y in range(y0, y1) if pixels[x, y])


def view(volume, **kw):
    """The box as configured today: 20-40 at step 5, so five positions."""
    return VolumeView(volume=volume, min_volume=20, max_volume=40, step=5, **kw)


class TestFrame:
    def test_frame_matches_the_panel(self):
        img = render(view(20))
        assert img.size == (WIDTH, HEIGHT)
        assert img.mode == "1"

    def test_nothing_touches_the_edges(self):
        """PIL crops silently, so an overflowing layout only shows up as a
        clipped glyph on the real panel. The margins have to stay empty."""
        frames = [render(view(v)) for v in (20, 25, 30, 40)]
        frames.append(render(view(20, muted=True)))
        for img in frames:
            assert lit_count(img, (0, 0, 2, HEIGHT)) == 0, "left margin"
            assert lit_count(img, (WIDTH - 2, 0, WIDTH, HEIGHT)) == 0, "right margin"
            assert lit_count(img, (0, HEIGHT - 2, WIDTH, HEIGHT)) == 0, "bottom margin"


class TestBlocks:
    def test_one_block_per_position(self):
        # runs = filled + 2*(5 - filled), and filled counts from 1 at the floor.
        expected = {20: 9, 25: 8, 30: 7, 35: 6, 40: 5}
        for volume, runs in expected.items():
            assert lit_runs(render(view(volume)), BLOCK_BAND_Y) == runs, volume

    def test_the_quietest_setting_is_not_an_empty_row(self):
        """The one thing this screen must never say: "off". The parent set a
        floor so the box keeps playing; a blank row would contradict that."""
        floor = render(view(20))
        # Five positions, one lit: 1 + 2*4 = 9. An empty row would be 10.
        assert lit_runs(floor, BLOCK_BAND_Y) == 9

    def test_every_click_changes_the_picture(self):
        frames = [render(view(v)).tobytes() for v in range(20, 41, 5)]
        assert len(set(frames)) == len(frames)

    def test_a_hundred_positions_render_as_a_bar(self):
        img = render(VolumeView(volume=63, min_volume=0, max_volume=100, step=1))
        assert lit_runs(img, BLOCK_BAND_Y) <= 3

    def test_the_bar_fallback_is_never_empty_either(self):
        img = render(VolumeView(volume=0, min_volume=0, max_volume=100, step=1))
        assert lit_count(img, (4, 40, 20, 55)) > 0


class TestLabels:
    HEADER_RIGHT = (100, 10, WIDTH, 30)

    def test_the_bottom_of_the_range_is_labelled(self):
        """"Leise" is the difference between the quietest setting and off."""
        assert lit_count(render(view(20)), self.HEADER_RIGHT) > 0

    def test_the_ordinary_case_is_not_labelled(self):
        assert lit_count(render(view(30)), self.HEADER_RIGHT) == 0

    def test_the_stop_says_so(self):
        """Otherwise one keeps turning and wonders."""
        at_max = render(view(40))
        assert lit_count(at_max, self.HEADER_RIGHT) > 0
        # All five blocks solid, no borders left over.
        assert lit_runs(at_max, BLOCK_BAND_Y) == 5

    def test_no_percentage_anywhere(self):
        """A third number for one quantity is what made this confusing: the
        WebUI prints the raw volume beside a slider spanning the range, and
        any two of the three disagree."""
        percent_sign = render(view(30))
        # Right of the speaker glyph (which reaches x=40) the upper band is
        # empty unless one of the two end labels is showing.
        assert lit_count(percent_sign, (44, 0, WIDTH, 30)) == 0


class TestMuted:
    def test_muted_is_its_own_screen(self):
        assert render(view(20, muted=True)).tobytes() != render(view(20)).tobytes()

    def test_muted_does_not_depend_on_the_level_underneath(self):
        assert (
            render(view(0, muted=True)).tobytes()
            == render(view(40, muted=True)).tobytes()
        )

    def test_the_floor_and_muted_look_different(self):
        """The one distinction a parent has to be able to make at a glance -
        and the one the child cannot cause by turning, only by pressing."""
        assert render(view(20)).tobytes() != render(view(20, muted=True)).tobytes()
