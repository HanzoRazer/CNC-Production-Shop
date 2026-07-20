"""Tests for domain contracts.

Dev Order: MSME-001

Confirms enum serialized values (a public contract) and the three-concept
coordinate model: a spatial position composes SoundingPitch, PhysicalPosition
(from the nut), and PlayingPosition (relative to a capo) without overloading one
integer. Models are frozen.
"""

import dataclasses

import pytest

from musical_spatial_mapping import (
    FingerboardMode,
    MusicalEvent,
    OpenStringPolicy,
    PhysicalPosition,
    PlayingPosition,
    SelectionStatus,
    SoundingPitch,
    SpatialPosition,
)


class TestEnumValues:
    def test_fingerboard_mode_values(self):
        assert FingerboardMode.FRETTED.value == "fretted"
        assert FingerboardMode.FRETLESS.value == "fretless"
        assert FingerboardMode.HYBRID.value == "hybrid"

    def test_selection_status_values(self):
        assert SelectionStatus.SELECTED.value == "selected"
        assert SelectionStatus.AMBIGUOUS.value == "ambiguous"
        assert SelectionStatus.UNPLAYABLE.value == "unplayable"

    def test_open_string_policy_values(self):
        assert {p.value for p in OpenStringPolicy} == {
            "allow",
            "prefer",
            "avoid",
            "exclude",
        }


class TestMusicalEvent:
    def test_defaults(self):
        event = MusicalEvent(
            event_id="note-001", midi_note=64, start_tick=0, duration_ticks=480
        )
        assert event.velocity == 64
        assert event.cents_offset == 0.0
        assert event.voice_id is None

    def test_frozen(self):
        event = MusicalEvent(
            event_id="note-001", midi_note=64, start_tick=0, duration_ticks=480
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.midi_note = 65  # type: ignore[misc]


class TestThreeConceptPosition:
    def test_composition_separates_physical_from_playing(self):
        # A note fretted 3 semitones above a capo at fret 2 -> physical fret 5,
        # playing fret 3 relative to the capo. The two integers are distinct.
        position = SpatialPosition(
            string_id="string-1",
            course_id=None,
            sounding=SoundingPitch(midi_note=67),
            physical=PhysicalPosition(
                semitone_offset_from_nut=5.0,
                fret_number=5,
                normalized_position=0.159104,
                distance_from_nut_mm=103.10,
            ),
            playing=PlayingPosition(
                semitone_offset_from_open=3.0,
                fret_relative_to_capo=3,
                is_open=False,
            ),
        )
        assert position.physical.fret_number == 5
        assert position.playing.fret_relative_to_capo == 3
        assert position.physical.fret_number != position.playing.fret_relative_to_capo

    def test_fretless_position_has_no_fret_but_has_location(self):
        position = SpatialPosition(
            string_id="string-1",
            course_id=None,
            sounding=SoundingPitch(midi_note=67),
            physical=PhysicalPosition(
                semitone_offset_from_nut=3.0,
                fret_number=None,
                normalized_position=0.159104,
                distance_from_nut_mm=103.10,
            ),
            playing=PlayingPosition(
                semitone_offset_from_open=3.0,
                fret_relative_to_capo=None,
                is_open=False,
            ),
        )
        # Absence of a fret must not imply absence of a position.
        assert position.physical.fret_number is None
        assert position.physical.normalized_position > 0.0

    def test_frozen(self):
        pitch = SoundingPitch(midi_note=67)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pitch.midi_note = 68  # type: ignore[misc]
