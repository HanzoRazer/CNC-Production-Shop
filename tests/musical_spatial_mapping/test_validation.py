"""Tests for fail-closed validation.

Dev Order: MSME-001
"""

import pytest

from musical_spatial_mapping import (
    FingerboardMode,
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    MusicalEvent,
    StringProfile,
    validate_instrument_profile,
    validate_mapping_constraints,
    validate_mapping_preferences,
    validate_musical_event,
)
from musical_spatial_mapping.errors import (
    EventValidationError,
    MappingConstraintError,
    ProfileValidationError,
)
from musical_spatial_mapping.fixtures import guitar_standard_6


def _string(sid: str, order: int, note: int) -> StringProfile:
    return StringProfile(
        string_id=sid, display_label=str(order), display_order=order, open_midi_note=note
    )


def _fretted(**overrides) -> InstrumentProfile:
    base = dict(
        schema_version="1.0",
        instrument_id="test.fretted",
        display_name="Test",
        family="test",
        fingerboard_mode=FingerboardMode.FRETTED,
        strings=(_string("string-1", 1, 64), _string("string-2", 2, 59)),
        scale_length_mm=648.0,
        fret_count=22,
    )
    base.update(overrides)
    return InstrumentProfile(**base)


class TestEventValidation:
    def test_valid_event(self):
        event = MusicalEvent("n1", 64, 0, 480)
        assert validate_musical_event(event) is event

    def test_empty_id(self):
        with pytest.raises(EventValidationError):
            validate_musical_event(MusicalEvent("", 64, 0, 480))

    def test_bad_midi(self):
        with pytest.raises(EventValidationError):
            validate_musical_event(MusicalEvent("n1", 200, 0, 480))

    def test_nonpositive_duration(self):
        with pytest.raises(EventValidationError):
            validate_musical_event(MusicalEvent("n1", 64, 0, 0))

    def test_bad_velocity(self):
        with pytest.raises(EventValidationError):
            validate_musical_event(MusicalEvent("n1", 64, 0, 480, velocity=200))


class TestProfileValidation:
    def test_example_guitar_valid(self):
        profile = guitar_standard_6()
        assert validate_instrument_profile(profile) is profile

    def test_duplicate_string_id(self):
        # Construction never validates; the fail-closed check is validate_*.
        profile = _fretted(strings=(_string("dup", 1, 64), _string("dup", 2, 59)))
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)

    def test_duplicate_display_order(self):
        profile = _fretted(strings=(_string("a", 1, 64), _string("b", 1, 59)))
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)

    def test_open_pitch_out_of_range(self):
        profile = _fretted(strings=(_string("a", 1, 200), _string("b", 2, 59)))
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)

    def test_fretted_requires_fret_count(self):
        profile = _fretted(fret_count=None)
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)

    def test_fretless_forbids_fret_count(self):
        profile = _fretted(fingerboard_mode=FingerboardMode.FRETLESS, fret_count=22)
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)

    def test_negative_scale_length(self):
        profile = _fretted(scale_length_mm=-1.0)
        with pytest.raises(ProfileValidationError):
            validate_instrument_profile(profile)


class TestConstraintValidation:
    def test_capo_beyond_fret_count(self):
        profile = _fretted()
        with pytest.raises(MappingConstraintError):
            validate_mapping_constraints(profile, MappingConstraints(capo_fret=99))

    def test_min_exceeds_max(self):
        profile = _fretted()
        with pytest.raises(MappingConstraintError):
            validate_mapping_constraints(
                profile, MappingConstraints(minimum_position=10, maximum_position=2)
            )

    def test_allowed_and_excluded_overlap(self):
        profile = _fretted()
        with pytest.raises(MappingConstraintError):
            validate_mapping_constraints(
                profile,
                MappingConstraints(
                    allowed_string_ids=frozenset({"string-1"}),
                    excluded_string_ids=frozenset({"string-1"}),
                ),
            )

    def test_unknown_excluded_string(self):
        profile = _fretted()
        with pytest.raises(MappingConstraintError):
            validate_mapping_constraints(
                profile, MappingConstraints(excluded_string_ids=frozenset({"ghost"}))
            )

    def test_allowed_minus_excluded_empty(self):
        profile = _fretted()
        with pytest.raises(MappingConstraintError):
            validate_mapping_constraints(
                profile,
                MappingConstraints(
                    allowed_string_ids=frozenset({"string-1"}),
                    excluded_string_ids=frozenset({"string-1", "string-2"}),
                ),
            )

    def test_valid_constraints_pass(self):
        profile = _fretted()
        constraints = MappingConstraints(
            preferred_minimum_position=0, preferred_maximum_position=5, capo_fret=2
        )
        assert validate_mapping_constraints(profile, constraints) is constraints


class TestPreferenceValidation:
    def test_negative_weight_rejected(self):
        with pytest.raises(MappingConstraintError):
            validate_mapping_preferences(MappingPreferences(movement_weight=-1.0))

    def test_non_finite_weight_rejected(self):
        with pytest.raises(MappingConstraintError):
            validate_mapping_preferences(
                MappingPreferences(position_weight=float("nan"))
            )

    def test_signed_lower_position_bias_allowed(self):
        prefs = MappingPreferences(lower_position_bias=-2.0)
        assert validate_mapping_preferences(prefs) is prefs
