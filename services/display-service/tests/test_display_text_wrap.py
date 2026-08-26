"""Breaking a title across lines, measured rather than counted.

Both bugs this pins down were found by rendering: the wrapper first dropped the
second line of every two-line title, then drew a single over-long word straight
off the edge of the panel. Both looked fine in the arithmetic and wrong on the
glass.
"""

from __future__ import annotations

import pytest

from display_service.render import fonts
from display_service.render.primitives import (
    block_height,
    fit_lines,
    new_frame,
    text_width,
    wrap,
)

WIDTH = 124
LONG = "Das Lied von der Raupe Nimmersatt"
SHORT = "Ein Lama in Yokohama"


@pytest.fixture
def draw():
    _, d = new_frame()
    return d


def widths(draw, lines, font):
    return [text_width(draw, line, font) for line in lines]


class TestWrap:
    def test_every_line_fits_the_width(self, draw):
        font = fonts.get(fonts.REGULAR, 12)
        lines = wrap(draw, LONG, font, WIDTH, 2)
        assert max(widths(draw, lines, font)) <= WIDTH

    def test_a_single_word_too_wide_is_trimmed_not_drawn_off_the_edge(self, draw):
        """The bug: one word, no break opportunity, returned unmarked."""
        font = fonts.get(fonts.REGULAR, 20)
        lines = wrap(draw, "Sandmaennchen", font, WIDTH, 2)
        assert max(widths(draw, lines, font)) <= WIDTH
        assert lines[-1].endswith("…")

    def test_text_that_fits_is_left_alone(self, draw):
        font = fonts.get(fonts.REGULAR, 12)
        assert wrap(draw, "Kurz", font, WIDTH, 2) == ["Kurz"]

    def test_it_breaks_on_words(self, draw):
        font = fonts.get(fonts.REGULAR, 12)
        lines = wrap(draw, LONG, font, WIDTH, 2)
        assert len(lines) == 2
        assert " ".join(lines) == LONG

    def test_more_than_fits_is_marked_as_cut(self, draw):
        font = fonts.get(fonts.REGULAR, 14)
        lines = wrap(draw, "Der Grueffelo und das Grueffelokind lesen ein Buch",
                     font, WIDTH, 2)
        assert len(lines) == 2
        assert lines[-1].endswith("…")

    def test_the_ellipsis_is_not_doubled(self, draw):
        font = fonts.get(fonts.REGULAR, 20)
        lines = wrap(draw, "Sandmaennchenlied und mehr davon", font, WIDTH, 2)
        assert not lines[-1].endswith("……")

    def test_empty_text_is_one_empty_line(self, draw):
        font = fonts.get(fonts.REGULAR, 12)
        assert wrap(draw, "", font, WIDTH, 2) == [""]

    def test_it_terminates_on_a_wall_of_long_words(self, draw):
        """A loop that cannot place a word must still advance."""
        font = fonts.get(fonts.REGULAR, 20)
        lines = wrap(draw, "Donaudampfschiff " * 5, font, WIDTH, 2)
        assert len(lines) == 2


class TestFitLines:
    def test_a_short_title_gets_a_bigger_size(self, draw):
        _, _, small = fit_lines(draw, LONG, WIDTH, 2, (20, 16, 12, 9),
                                fonts.REGULAR, max_height=27)
        _, _, large = fit_lines(draw, "Bibi", WIDTH, 2, (20, 16, 12, 9),
                                fonts.REGULAR, max_height=27)
        assert large > small

    def test_the_band_height_is_respected(self, draw):
        """Checking only the width picks a size whose second line then does not
        fit the band - which is how that line went missing."""
        _, lines, size = fit_lines(draw, SHORT, WIDTH, 2, (20, 18, 16, 14, 12, 9),
                                   fonts.REGULAR, max_height=27)
        assert block_height(size, len(lines)) <= 27

    def test_a_title_that_cannot_fit_comes_back_cut(self, draw):
        _, lines, _ = fit_lines(draw, "Der Grueffelo und das Grueffelokind lesen",
                                WIDTH, 1, (12, 9), fonts.REGULAR, max_height=27)
        assert lines[-1].endswith("…")

    def test_the_result_always_fits_the_measured_width(self, draw):
        for title in (LONG, SHORT, "Sandmaennchen", "A", "", "x " * 40):
            font, lines, _ = fit_lines(draw, title, WIDTH, 2, (20, 16, 12, 9),
                                       fonts.REGULAR, max_height=27)
            assert max(widths(draw, lines, font)) <= WIDTH, title
