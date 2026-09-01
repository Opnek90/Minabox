"""The screen for "something is playing": what it says and what it draws."""

from __future__ import annotations

from display_service.render.playing import (
    PAUSED_BAR_BOX,
    PAUSED_SLEEPER_SIZE,
    PAUSED_SLEEPER_TOP,
    PAUSED_Z_GAP,
    TIME_BASELINE,
    TITLE_BAND_HEIGHT,
    UNKNOWN_TIME,
    WALK_LINE_Y,
    PlayingView,
    render,
)
from display_service.render.primitives import (
    HEIGHT,
    SLEEP_ZS_PHASES,
    SLEEP_ZS_WIDTH,
    WIDTH,
)


def left_margin() -> int:
    """Left edge of the centred sleeper group - empty on the paused screen."""
    group = PAUSED_SLEEPER_SIZE + PAUSED_Z_GAP + SLEEP_ZS_WIDTH
    return max(2, (WIDTH - group) // 2)

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

    def test_paused_keeps_the_time_even_though_it_is_not_drawn(self):
        """The paused screen shows Knuffel asleep where the time would be. The
        value still has to be right: it is what comes back the moment play is
        pressed, and a view that lied while paused would flash the wrong number
        for a tick."""
        assert PlayingView(LONG, 5 * M, 10 * M, paused=True).time_text == "noch 5 Min."

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

    def test_a_short_title_does_not_grow_past_its_band(self):
        """The long title lands on the smallest size whatever the rule, so it
        proves nothing. A short one is offered 20 px by width alone - two lines
        of which would spill below the band into Knuffel's headroom."""
        # Fraction 0 keeps Knuffel far left, so the strip under the band on the
        # right is title-only: empty unless a second line has grown into it.
        img = render(PlayingView(SHORT, 10 * M, 10 * M))
        assert lit_count(img, (40, TITLE_BAND_HEIGHT + 1, 124, WALK_LINE_Y)) == 0

    def test_the_progress_advances_with_the_track(self):
        """Knuffel and the stretch of line behind him both move to the right."""
        early = render(PlayingView(LONG, 9 * M, 10 * M))
        late = render(PlayingView(LONG, 1 * M, 10 * M))
        band = (0, WALK_LINE_Y - 2, WIDTH, WALK_LINE_Y + 2)
        assert lit_count(late, band) > lit_count(early, band)


class TestWalk:
    """The progress bar is Knuffel walking the track to the end of the song."""

    HEAD_BAND = (0, WALK_LINE_Y - 16, WIDTH, WALK_LINE_Y - 2)

    def _knuffel_centre_x(self, img) -> float:
        """Mean x of the lit pixels in the band between the title and the line -
        which is Knuffel and nothing else."""
        x0, y0, x1, y1 = self.HEAD_BAND
        pixels = img.load()
        xs = [x for x in range(x0, x1) for y in range(y0, y1) if pixels[x, y]]
        assert xs, "Knuffel is not on the screen"
        return sum(xs) / len(xs)

    def test_he_is_on_the_track_while_playing(self):
        assert lit_count(render(PlayingView(LONG, 5 * M, 10 * M)), self.HEAD_BAND) > 60

    def test_he_walks_from_left_to_right_as_the_track_plays(self):
        xs = [
            self._knuffel_centre_x(render(PlayingView(LONG, r, 10 * M)))
            for r in (10 * M, 7 * M, 4 * M, 1 * M)
        ]
        assert xs == sorted(xs)
        assert xs[-1] - xs[0] > 40

    def test_he_waves_in_the_home_stretch(self):
        """Near the end he turns round - a different pose, not just a new
        position."""
        mid = render(PlayingView(SHORT, 5 * M, 10 * M))
        end = render(PlayingView(SHORT, 5_000, 10 * M))
        assert mid.tobytes() != end.tobytes()
        # The wave reaches up and out: the top-right of the sprite band is lit
        # near the end and was not mid-track.
        arm = (WIDTH - 30, WALK_LINE_Y - 22, WIDTH - 2, WALK_LINE_Y - 12)
        assert lit_count(end, arm) > lit_count(mid, arm)

    def test_a_stream_leaves_him_at_the_start(self):
        """No length means no end to walk to; he waits at the left."""
        img = render(PlayingView("Radio Teddy", None, None))
        assert self._knuffel_centre_x(img) < WIDTH / 3


class TestArriving:
    def test_true_only_in_the_last_seconds(self):
        assert not PlayingView(LONG, 60_000, 10 * M).arriving
        assert PlayingView(LONG, 10_000, 10 * M).arriving
        assert PlayingView(LONG, 0, 10 * M).arriving

    def test_a_stream_never_arrives(self):
        assert not PlayingView("Radio Teddy", None, None).arriving

    def test_pause_keeps_the_bar_rather_than_hiding_it(self):
        """Paused has its own layout, but "how far in" is still true and still
        what the parent looks for. Only its position moves."""
        early = render(PlayingView(LONG, 9 * M, 10 * M, paused=True))
        late = render(PlayingView(LONG, 1 * M, 10 * M, paused=True))
        band = (0, PAUSED_BAR_BOX[1], WIDTH, PAUSED_BAR_BOX[3] + 1)
        assert lit_count(early, band) > 0
        assert lit_count(late, band) > lit_count(early, band)


class TestPausedSleeper:
    """Paused draws Knuffel asleep instead of the word "Pause".

    The person most often standing in front of this panel cannot read yet, and
    a creature with its eyes shut needs no reading at all.
    """

    def test_paused_looks_nothing_like_playing(self):
        playing = render(PlayingView(LONG, 5 * M, 10 * M))
        paused = render(PlayingView(LONG, 5 * M, 10 * M, paused=True))
        assert paused.tobytes() != playing.tobytes()

    def test_the_sleeper_is_there(self):
        """A filled creature 27 px across, not a line of text.

        Deliberately not compared against the same band of the playing screen:
        the progress bar sits there and is lit far more brightly than anything
        Knuffel is, so that comparison passes and fails for the wrong reason.
        """
        paused = render(PlayingView(LONG, 5 * M, 10 * M, paused=True))
        left = left_margin()
        body = (left, PAUSED_SLEEPER_TOP, left + PAUSED_SLEEPER_SIZE, HEIGHT)
        assert lit_count(paused, body) > 200

    def test_the_word_pause_is_gone(self):
        """It was there for whoever can read. The creature is for everyone
        else, and both at once would only crowd the panel."""
        paused = render(PlayingView(LONG, 5 * M, 10 * M, paused=True))
        # Centred text reaches the outer thirds of the panel; the centred
        # sleeper group does not.
        assert lit_count(paused, (2, TIME_BASELINE - 11, left_margin(), HEIGHT)) == 0

    def test_each_phase_adds_a_z(self):
        """One Z, then two, then three. On a panel that cannot fade anything
        out, appearing one after another is what reads as breathing."""
        counts = [
            lit_count(
                render(PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=p)),
                (0, PAUSED_SLEEPER_TOP, WIDTH, HEIGHT),
            )
            for p in range(SLEEP_ZS_PHASES)
        ]
        assert counts == sorted(counts)
        assert counts[0] < counts[-1]

    def test_the_phase_wraps_instead_of_running_off(self):
        """The caller derives it from the clock, so it grows forever."""
        first = render(PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=0))
        wrapped = render(
            PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=SLEEP_ZS_PHASES)
        )
        assert wrapped.tobytes() == first.tobytes()

    def test_the_zs_stay_clear_of_the_progress_bar(self):
        """A Z growing out of the bar is just a broken bar."""
        last = SLEEP_ZS_PHASES - 1
        full = render(PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=last))
        empty = render(PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=0))
        band = (0, PAUSED_BAR_BOX[1], WIDTH, PAUSED_BAR_BOX[3] + 1)
        assert lit_count(full, band) == lit_count(empty, band)

    def test_he_does_not_move_while_the_zs_grow(self):
        """Only the Zs change between phases - that is what keeps the partial
        update to a few pages of a bus the RFID reader shares."""
        band = (0, PAUSED_SLEEPER_TOP, 40, HEIGHT)
        counts = {
            lit_count(
                render(PlayingView(LONG, 5 * M, 10 * M, paused=True, sleep_phase=p)),
                band,
            )
            for p in range(SLEEP_ZS_PHASES)
        }
        assert len(counts) == 1

    def test_nothing_touches_the_edges(self):
        """PIL crops silently: a creature 27 px tall starting at 36 has two
        pixels to spare, and the Zs reach right."""
        for title in (LONG, SHORT, "Bibi", ""):
            for phase in range(SLEEP_ZS_PHASES):
                img = render(
                    PlayingView(title, 5 * M, 10 * M, paused=True, sleep_phase=phase)
                )
                where = f"{title!r} phase {phase}"
                assert lit_count(img, (0, 0, 2, HEIGHT)) == 0, f"left: {where}"
                right = (WIDTH - 2, 0, WIDTH, HEIGHT)
                assert lit_count(img, right) == 0, f"right: {where}"
                low = (0, HEIGHT - 1, WIDTH, HEIGHT)
                assert lit_count(img, low) == 0, f"low: {where}"

    def test_an_unknown_title_still_renders_the_rest(self):
        img = render(PlayingView("", 5 * M, 10 * M))
        assert lit_count(img, (0, 32, WIDTH, HEIGHT)) > 0
