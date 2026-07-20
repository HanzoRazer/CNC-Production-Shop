"""Tests for pitch utilities.

Dev Order: MSME-001
"""

import pytest

from musical_spatial_mapping.pitch import (
    format_pitch_name,
    midi_note_to_octave,
    midi_note_to_pitch_class,
    pitch_distance_semitones,
)


class TestPitchClassAndOctave:
    def test_pitch_class(self):
        assert midi_note_to_pitch_class(60) == 0
        assert midi_note_to_pitch_class(64) == 4
        assert midi_note_to_pitch_class(61) == 1

    def test_octave_boundaries(self):
        assert midi_note_to_octave(60) == 4
        assert midi_note_to_octave(72) == 5
        assert midi_note_to_octave(48) == 3
        assert midi_note_to_octave(0) == -1

    def test_invalid_midi_note_rejected(self):
        with pytest.raises(ValueError):
            midi_note_to_pitch_class(128)
        with pytest.raises(ValueError):
            midi_note_to_octave(-1)

    def test_bool_is_not_a_valid_midi_note(self):
        with pytest.raises(ValueError):
            midi_note_to_pitch_class(True)


class TestPitchNames:
    def test_sharp_names(self):
        assert format_pitch_name(64) == "E4"
        assert format_pitch_name(60) == "C4"
        assert format_pitch_name(61) == "C#4"
        assert format_pitch_name(40) == "E2"

    def test_flat_names(self):
        assert format_pitch_name(61, prefer_flats=True) == "Db4"
        assert format_pitch_name(63, prefer_flats=True) == "Eb4"

    def test_spelling_never_changes_pitch_class(self):
        assert midi_note_to_pitch_class(61) == 1  # C#/Db both pitch class 1


class TestPitchDistance:
    def test_ascending(self):
        assert pitch_distance_semitones(60, 64) == 4.0

    def test_descending(self):
        assert pitch_distance_semitones(64, 60) == -4.0

    def test_cents_offset_folds_in(self):
        assert pitch_distance_semitones(60, 64, cents_offset=50.0) == pytest.approx(4.5)

    def test_non_finite_cents_rejected(self):
        with pytest.raises(ValueError):
            pitch_distance_semitones(60, 64, cents_offset=float("inf"))
