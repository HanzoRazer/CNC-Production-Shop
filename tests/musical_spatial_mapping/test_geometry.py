"""Tests for equal-temperament position geometry.

Dev Order: MSME-001

These vectors are behavioral spec: the equal-temperament formula
distance = L * (1 - 2 ** (-n / 12)) must hold for both fretted and fretless targets.
"""

import pytest

from musical_spatial_mapping.geometry import (
    distance_from_nut_mm,
    fret_distance_from_nut_mm,
    normalized_position_for_semitones,
)


class TestNormalizedPosition:
    def test_open_string_is_zero(self):
        assert normalized_position_for_semitones(0) == 0.0

    def test_octave_is_half(self):
        # Case G-002
        assert normalized_position_for_semitones(12) == pytest.approx(0.5)

    def test_two_octaves_is_three_quarters(self):
        # Case G-003
        assert normalized_position_for_semitones(24) == pytest.approx(0.75)

    def test_fractional_offset_is_continuous(self):
        # Case G-004: fretless target between semitones 3 and 4.
        value = normalized_position_for_semitones(3.5)
        assert 0.0 < value < 1.0
        lower = normalized_position_for_semitones(3.0)
        upper = normalized_position_for_semitones(4.0)
        assert lower < value < upper

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError):
            normalized_position_for_semitones(-1.0)


class TestDistanceFromNut:
    def test_open_string(self):
        # Case G-001
        assert distance_from_nut_mm(648.0, 0) == 0.0

    def test_octave(self):
        assert distance_from_nut_mm(648.0, 12) == pytest.approx(324.0)

    def test_two_octaves(self):
        assert distance_from_nut_mm(648.0, 24) == pytest.approx(486.0)

    def test_fret_distance_matches_semitone_distance(self):
        assert fret_distance_from_nut_mm(648.0, 12) == pytest.approx(
            distance_from_nut_mm(648.0, 12.0)
        )

    def test_nonpositive_scale_length_rejected(self):
        with pytest.raises(ValueError):
            distance_from_nut_mm(0.0, 12)
        with pytest.raises(ValueError):
            distance_from_nut_mm(-648.0, 12)

    def test_negative_fret_rejected(self):
        with pytest.raises(ValueError):
            fret_distance_from_nut_mm(648.0, -1)
