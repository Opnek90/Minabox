"""Arithmetic of the volume HUD - the part that must not lie to the user.

The premise of every case here: the audio service clamps the running volume
into [min_volume, max_volume], so the raw number is a position in that range
and not a percentage.
"""

import pytest

from display_service.render.volume import LEVELS, VolumeView


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


class TestLevel:
    """The knob's own resolution stops at the panel: every box shows five
    singing levels, whatever its configured step."""

    def test_the_floor_is_level_one_never_zero(self):
        """min_volume is a setting, not silence; level 0 would say otherwise."""
        assert VolumeView(volume=20, min_volume=20, max_volume=40).level == 1

    def test_the_stop_is_the_top_level(self):
        assert VolumeView(volume=40, min_volume=20, max_volume=40).level == LEVELS

    def test_the_levels_climb_evenly_across_the_range(self):
        levels = [
            VolumeView(volume=v, min_volume=20, max_volume=40).level
            for v in range(20, 41, 5)
        ]
        assert levels == [1, 2, 3, 4, 5]

    def test_a_wide_fine_range_still_only_has_five(self):
        seen = {
            VolumeView(volume=v, min_volume=0, max_volume=100).level
            for v in range(0, 101)
        }
        assert seen == {1, 2, 3, 4, 5}

    def test_a_retained_out_of_range_value_is_clamped_to_a_level(self):
        assert VolumeView(volume=999, min_volume=0, max_volume=40).level == LEVELS
        assert VolumeView(volume=-5, min_volume=10, max_volume=40).level == 1


class TestEnds:
    def test_at_max_is_the_stop(self):
        assert VolumeView(volume=40, min_volume=0, max_volume=40).at_max
        assert not VolumeView(volume=39, min_volume=0, max_volume=40).at_max

    def test_at_min_is_the_floor(self):
        assert VolumeView(volume=20, min_volume=20, max_volume=40).at_min
        assert not VolumeView(volume=25, min_volume=20, max_volume=40).at_min

    def test_the_floor_is_not_muted(self):
        view = VolumeView(volume=20, min_volume=20, max_volume=40)
        assert not view.muted
        assert view.at_min
