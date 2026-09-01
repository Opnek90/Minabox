"""Pixel-level checks on the volume HUD.

The renderer touches no hardware, so these run anywhere. They assert on what
the panel would actually show rather than on the calls made to get there.
"""

from display_service.render import knuffel
from display_service.render.primitives import HEIGHT, WIDTH
from display_service.render.volume import LEVELS, VolumeView, render

# Right of Knuffel's body, where the notes climb - clear of the sprite itself.
NOTES_BOX = (48, 0, WIDTH, HEIGHT)


def lit_count(img, box=None):
    x0, y0, x1, y1 = box or (0, 0, img.width, img.height)
    pixels = img.load()
    return sum(1 for x in range(x0, x1) for y in range(y0, y1) if pixels[x, y])


def note_blobs(img):
    """How many separate lit shapes sit in the notes area, by flood fill.

    Knuffel is excluded by the box; the notes are the only thing left there,
    and each is one connected blob (head plus its stem)."""
    pixels = img.load()
    x0, y0, x1, y1 = NOTES_BOX
    seen = set()
    blobs = 0
    stack = []
    for sx in range(x0, x1):
        for sy in range(y0, y1):
            if not pixels[sx, sy] or (sx, sy) in seen:
                continue
            blobs += 1
            stack.append((sx, sy))
            while stack:
                x, y = stack.pop()
                if (x, y) in seen:
                    continue
                seen.add((x, y))
                if not (x0 <= x < x1 and y0 <= y < y1) or not pixels[x, y]:
                    continue
                stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    return blobs


def view(volume, **kw):
    """The box as configured today: 20-40, so the five levels line up with the
    five detents the knob happens to have."""
    return VolumeView(volume=volume, min_volume=20, max_volume=40, **kw)


class TestFrame:
    def test_frame_matches_the_panel(self):
        img = render(view(20))
        assert img.size == (WIDTH, HEIGHT)
        assert img.mode == "1"

    def test_nothing_touches_the_edges(self):
        """PIL crops silently, so an overflowing layout only shows up as a
        clipped glyph on the real panel. The margins have to stay empty."""
        frames = [render(view(v)) for v in range(20, 41, 5)]
        frames.append(render(view(20, muted=True)))
        for img in frames:
            assert lit_count(img, (0, 0, 1, HEIGHT)) == 0, "left margin"
            assert lit_count(img, (WIDTH - 1, 0, WIDTH, HEIGHT)) == 0, "right margin"
            assert lit_count(img, (0, HEIGHT - 1, WIDTH, HEIGHT)) == 0, "bottom margin"
            assert lit_count(img, (0, 0, WIDTH, 1)) == 0, "top margin"


class TestSinging:
    def test_one_note_per_level(self):
        for volume, level in ((20, 1), (25, 2), (30, 3), (35, 4), (40, 5)):
            assert note_blobs(render(view(volume))) == level, volume

    def test_the_quietest_setting_still_shows_a_note(self):
        """The one thing this screen must never say is "off". The parent set a
        floor so the box keeps playing; nothing coming out of him would
        contradict that."""
        assert note_blobs(render(view(20))) == 1

    def test_every_level_change_changes_the_picture(self):
        frames = [render(view(v)).tobytes() for v in range(20, 41, 5)]
        assert len(set(frames)) == len(frames)

    def test_the_notes_grow_as_they_climb(self):
        """Level 5 puts far more lit pixels in the notes area than level 2 -
        more of them, and each one larger."""
        assert lit_count(render(view(40)), NOTES_BOX) > lit_count(
            render(view(25)), NOTES_BOX
        )

    def test_a_wide_fine_range_still_shows_five_levels(self):
        seen = {
            note_blobs(render(VolumeView(v, 0, 100)))
            for v in range(0, 101, 3)
        }
        assert seen == set(range(1, LEVELS + 1))

    def test_the_top_puts_knuffel_at_full_stretch(self):
        """The ceiling cue: at the stop he belts it out, eyes shut. Below it he
        just sings. The two faces have to differ."""
        assert render(view(40)).tobytes() != render(view(35)).tobytes()
        # And it is a face change, not only one more note: the sprite area
        # itself differs.
        sprite = (0, 0, 48, HEIGHT)
        assert lit_count(render(view(40)), sprite) != lit_count(
            render(view(35)), sprite
        )


class TestNoText:
    def test_no_words_and_no_percentage_anywhere(self):
        """A number here would be a third figure for one quantity - the WebUI
        already prints the raw volume beside a slider spanning the range, and
        any two of the three disagree. The screen is a picture, nothing else."""
        # Right of Knuffel, along the bottom: where "MAX" / "Leise" and any
        # digits used to sit. The notes only ever climb, never down here.
        for volume in range(20, 41, 5):
            img = render(view(volume))
            assert lit_count(img, (48, HEIGHT - 18, WIDTH, HEIGHT)) == 0


class TestMuted:
    def test_muted_is_its_own_screen(self):
        assert render(view(20, muted=True)).tobytes() != render(view(20)).tobytes()

    def test_muted_is_knuffel_with_his_lips_shut(self):
        """The same character as every other screen, not a crossed-out speaker.

        His filled body is a broad lit mass in the upper half, and "Stumm" sits
        underneath for whoever can read.
        """
        muted = render(view(20, muted=True))
        assert lit_count(muted, (44, 2, 84, 44)) > 600
        assert knuffel.HUSHED in knuffel.MOODS
        # Text in the bottom strip - the one screen of the HUD that carries a
        # word.
        assert lit_count(muted, (0, HEIGHT - 12, WIDTH, HEIGHT)) > 0

    def test_muted_does_not_depend_on_the_level_underneath(self):
        assert (
            render(view(20, muted=True)).tobytes()
            == render(view(40, muted=True)).tobytes()
        )

    def test_the_floor_and_muted_look_different(self):
        """The one distinction a parent has to be able to make at a glance -
        and the one the child cannot cause by turning, only by pressing."""
        assert render(view(20)).tobytes() != render(view(20, muted=True)).tobytes()
