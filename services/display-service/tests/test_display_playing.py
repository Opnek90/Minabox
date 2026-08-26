"""The screen for "something is playing": what it says and what it draws."""

from __future__ import annotations

from display_service.render.playing import (
    PAUSED_TEXT,
    UNKNOWN_TIME,
    PlayingView,
    render,
)
from display_service.render.primitives import HEIGHT, WIDTH

M = 60_000
LONG = "Das Lied von der Raupe Nimmersatt"
SHORT = "Ein Lama in Yokohama"


def lit_count(img, box):
    x0, y0, x1, y1 = box
    pixels = img.load()
    return sum(1 for x in range(x0, x1) for y in range(y0, y1) if pixels[x, y])


class TestTimeText:
    def test_minutes_round_up_so_it_never_says_zero(self):
        """"noch 0 Min." while a minute is still playing reads as an error."""
        assert PlayingView(LONG, 61_000, 10 * M).time_text == "noch 2 Min."
        assert PlayingView(LONG, 1_000, 10 * M).time_text == "noch 10 Sek."

    def test_under_a_minute_it_switches_to_seconds(self):
        assert PlayingView(LONG, 40_000, 10 * M).time_text == "noch 40 Sek."

    def test_seconds_are_rounded_to_ten(self):
        """A per-second countdown on this panel is noise, and a full frame on
        the shared I2C bus every second is worse than noise."""
        assert PlayingView(LONG, 37_000, 10 * M).time_text == "noch 40 Sek."

    def test_paused_says_so_instead_of_counting(self):
        assert PlayingView(LONG, 5 * M, 10 * M, paused=True).time_text == PAUSED_TEXT

    def test_a_stream_has_no_remaining_time(self):
        """Streams have no length, and VLC does not always know one at once."""
        assert PlayingView("Radio Teddy", None, None).time_text == UNKNOWN_TIME


class TestFraction:
    def test_it_measures_what_is_behind_us(self):
        assert PlayingView(LONG, 5 * M, 10 * M).fraction == 0.5

    def test_a_fresh_track_is_empty(self):
        assert PlayingView(LONG, 10 * M, 10 * M).fraction == 0.0

    def test_without_a_length_there_is_no_progress(self):
        assert PlayingView("Radio Teddy", None, None).fraction == 0.0

    def test_it_cannot_leave_the_rails(self):
        """A locally counted remainder can overshoot at the end of a track."""
        assert PlayingView(LONG, -5000, 10 * M).fraction == 1.0
        assert PlayingView(LONG, 99 * M, 10 * M).fraction == 0.0


class TestRender:
    def test_frame_matches_the_panel(self):
        img = render(PlayingView(LONG, 5 * M, 10 * M))
        assert img.size == (WIDTH, HEIGHT)
        assert img.mode == "1"

    def test_nothing_touches_the_edges(self):
        """PIL crops silently, so an overflowing title is only visible on the
        glass. "Sandmaennchen" at 20 px was drawn straight off the edge."""
        for title in (LONG, SHORT, "Sandmaennchen", "Radio Teddy", "", "x " * 40):
            img = render(PlayingView(title, 5 * M, 10 * M))
            assert lit_count(img, (0, 0, 2, HEIGHT)) == 0, f"left: {title}"
            assert lit_count(img, (WIDTH - 2, 0, WIDTH, HEIGHT)) == 0, f"right: {title}"
            assert lit_count(img, (0, HEIGHT - 2, WIDTH, HEIGHT)) == 0, f"low: {title}"

    def test_both_title_lines_are_drawn(self):
        """The band decides the font size; when only the width was checked the
        second line was chosen and then silently dropped."""
        two_lines = render(PlayingView(LONG, 5 * M, 10 * M))
        first_line = lit_count(two_lines, (0, 0, WIDTH, 14))
        second_line = lit_count(two_lines, (0, 14, WIDTH, 30))
        assert first_line > 0
        assert second_line > 0

    def test_a_short_title_does_not_grow_into_the_bar(self):
        """The long title lands on 12 px whatever the rule, so it proves
        nothing. A short one is offered 16 px by width alone - two lines of
        which reach into the progress bar underneath."""
        img = render(PlayingView(SHORT, 5 * M, 10 * M))
        # Right half of the bar interior: empty at half-played, unless the
        # second title line has grown down into it.
        assert lit_count(img, (66, 34, 124, 44)) == 0

    def test_the_bar_moves_with_the_track(self):
        early = render(PlayingView(LONG, 9 * M, 10 * M))
        late = render(PlayingView(LONG, 1 * M, 10 * M))
        band = (0, 32, WIDTH, 47)
        assert lit_count(late, band) > lit_count(early, band)

    def test_pause_freezes_the_bar_rather_than_hiding_it(self):
        playing = render(PlayingView(LONG, 5 * M, 10 * M))
        paused = render(PlayingView(LONG, 5 * M, 10 * M, paused=True))
        band = (0, 32, WIDTH, 47)
        assert lit_count(paused, band) == lit_count(playing, band)
        assert paused.tobytes() != playing.tobytes()

    def test_an_unknown_title_still_renders_the_rest(self):
        img = render(PlayingView("", 5 * M, 10 * M))
        assert lit_count(img, (0, 32, WIDTH, HEIGHT)) > 0
