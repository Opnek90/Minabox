"""Arithmetic of the volume HUD - the part that must not lie to the user.

The premise of every case here: the audio service clamps the running volume
into [min_volume, max_volume], so the raw number is a position in that range
and not a percentage.
"""

import pytest

from display_service.render.volume import LABEL_MAX, LABEL_MIN, VolumeView


class TestPercent:
    def test_max_volume_is_a_clamp_not_a_scale(self):
        """40 on a box configured 0-40 is full volume, not 40 percent."""
        assert VolumeView(volume=40, min_volume=0, max_volume=40).percent == 100

    def test_minimum_is_zero_percent(self):
        assert VolumeView(volume=15, min_volume=15, max_volume=40).percent == 0

    def test_midpoint(self):
        assert VolumeView(volume=20, min_volume=0, max_volume=40).percent == 50

    def test_offset_range(self):
        # 25 sits 10 into a span of 25.
        assert VolumeView(volume=25, min_volume=15, max_volume=40).percent == 40

    @pytest.mark.parametrize("raw", [-10, 0, 50, 999])
    def test_percent_stays_in_bounds_for_any_input(self, raw):
        view = VolumeView(volume=raw, min_volume=10, max_volume=40)
        assert 0 <= view.percent <= 100

    def test_retained_status_from_before_a_config_change(self):
        """A retained message can sit outside the range; it is clamped, not shown."""
        assert VolumeView(volume=80, min_volume=0, max_volume=40).percent == 100

    def test_degenerate_range_does_not_divide_by_zero(self):
        assert VolumeView(volume=5, min_volume=5, max_volume=5).percent == 0


class TestDetents:
    def test_this_box_has_eight_steps(self):
        """0-40 at step 5 is what the box is configured for today."""
        view = VolumeView(volume=0, min_volume=0, max_volume=40, step=5)
        assert view.steps == 8
        assert view.use_blocks

    def test_one_click_lights_one_block(self):
        filled = [
            VolumeView(volume=v, min_volume=0, max_volume=40, step=5).filled
            for v in range(0, 41, 5)
        ]
        assert filled == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    def test_filled_never_exceeds_steps(self):
        view = VolumeView(volume=999, min_volume=0, max_volume=40, step=5)
        assert view.filled == view.steps

    def test_too_many_steps_falls_back_to_a_bar(self):
        view = VolumeView(volume=63, min_volume=0, max_volume=100, step=1)
        assert view.steps == 100
        assert not view.use_blocks

    def test_too_few_steps_falls_back_to_a_bar(self):
        view = VolumeView(volume=20, min_volume=0, max_volume=40, step=20)
        assert view.steps == 2
        assert not view.use_blocks

    def test_unknown_step_falls_back_to_a_bar(self):
        view = VolumeView(volume=20, min_volume=0, max_volume=40, step=0)
        assert view.steps == 0
        assert not view.use_blocks
        assert view.filled == 0


class TestLabel:
    def test_at_the_stop_it_says_so(self):
        assert VolumeView(volume=40, min_volume=0, max_volume=40).label == LABEL_MAX

    def test_at_the_bottom_it_says_quiet_not_muted(self):
        assert VolumeView(volume=0, min_volume=0, max_volume=40).label == LABEL_MIN

    def test_zero_is_not_muted(self):
        view = VolumeView(volume=0, min_volume=0, max_volume=40)
        assert not view.muted
        assert view.label != ""

    def test_no_label_in_the_ordinary_case(self):
        assert VolumeView(volume=20, min_volume=0, max_volume=40).label == ""
