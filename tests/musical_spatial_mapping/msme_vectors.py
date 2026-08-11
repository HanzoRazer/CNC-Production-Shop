"""Golden vector specification for the Musical Spatial Mapping Engine.

Dev Order: MSME-002 Phase G

This module declares the INPUTS only. Every expected output in
``tests/golden/msme_v1_vectors.json`` is produced by running the engine, so the
golden file is recorded behaviour rather than hand-written prose that could
quietly disagree with the code it claims to specify.

Profiles come from the bundled example resources via ``fixtures``, so vectors
exercise the instruments actually shipped rather than test-local approximations.

Regenerate with::

    python -m tests.musical_spatial_mapping.msme_vectors

Changing a vector changes the SPEC. Per ``tests/golden/README.md`` that is a
deliberate, reviewed decision — never a way to make a failing implementation
pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from musical_spatial_mapping import fixtures
from musical_spatial_mapping.enums import OpenStringPolicy
from musical_spatial_mapping.mapper import MusicalSpatialMapper
from musical_spatial_mapping.models import (
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    MusicalEvent,
    SpatialPosition,
    StringProfile,
)
from musical_spatial_mapping.serialization import mapping_result_to_dict

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "tests" / "golden" / "msme_v1_vectors.json"

# Every weight zeroed, so all totals are exactly 0.0 and the whole set ties.
ALL_TIED = MappingPreferences(
    movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
    preferred_region_weight=0.0, open_string_weight=0.0, lower_position_bias=0.0,
)


def _guitar() -> InstrumentProfile:
    return fixtures.guitar_standard_6()


def _bass() -> InstrumentProfile:
    return fixtures.bass_fretless_4()


def _mandolin() -> InstrumentProfile:
    return fixtures.mandolin_standard()


def _guitar_with_disabled(string_id: str) -> InstrumentProfile:
    base = _guitar()
    strings = tuple(
        StringProfile(**{**s.__dict__, "enabled": s.string_id != string_id})
        for s in base.strings
    )
    return InstrumentProfile(**{**base.__dict__, "strings": strings})


def _bass_without_scale_length() -> InstrumentProfile:
    base = _bass()
    return InstrumentProfile(**{**base.__dict__, "scale_length_mm": None})


def _event(midi: int, *, cents: float = 0.0, event_id: str = "vec") -> MusicalEvent:
    """Fixed tick values: nothing here may depend on a clock."""
    return MusicalEvent(
        event_id=event_id, midi_note=midi, start_tick=0, duration_ticks=480,
        velocity=64, cents_offset=cents,
    )


def _position_on(profile: InstrumentProfile, midi: int, string_id: str) -> SpatialPosition:
    """A prior position, produced by the engine rather than hand-built."""
    result = MusicalSpatialMapper(profile=profile).map(_event(midi))
    return next(c for c in result.candidates if c.position.string_id == string_id).position


@dataclass(frozen=True)
class Vector:
    """One golden case: a stable id, a description, and the exact inputs."""

    vector_id: str
    description: str
    profile: InstrumentProfile
    event: MusicalEvent
    constraints: MappingConstraints = field(default_factory=MappingConstraints)
    preferences: MappingPreferences = field(default_factory=MappingPreferences)
    previous_string_id: str | None = None
    previous_midi: int | None = None

    def run(self) -> dict[str, Any]:
        previous = None
        if self.previous_string_id is not None:
            previous = _position_on(
                self.profile,
                self.previous_midi if self.previous_midi is not None else self.event.midi_note,
                self.previous_string_id,
            )
        mapper = MusicalSpatialMapper(
            profile=self.profile, constraints=self.constraints, preferences=self.preferences
        )
        return mapping_result_to_dict(mapper.map(self.event, previous_position=previous))


def vectors() -> tuple[Vector, ...]:
    """The behavioural specification, in a fixed order."""
    return (
        Vector("guitar-fretted-basic", "Ordinary fretted selection, A4",
               _guitar(), _event(69)),
        Vector("guitar-multi-position", "One pitch playable on several strings, E4",
               _guitar(), _event(64)),
        Vector("guitar-open-string", "Low E as an open string",
               _guitar(), _event(40)),
        Vector("guitar-open-preferred", "Open-string policy PREFER charges fretted",
               _guitar(), _event(64),
               MappingConstraints(open_string_policy=OpenStringPolicy.PREFER)),
        Vector("guitar-open-avoided", "Open-string policy AVOID charges open",
               _guitar(), _event(64),
               MappingConstraints(open_string_policy=OpenStringPolicy.AVOID)),
        Vector("guitar-open-excluded", "Open-string policy EXCLUDE removes the candidate",
               _guitar(), _event(64),
               MappingConstraints(open_string_policy=OpenStringPolicy.EXCLUDE)),
        Vector("guitar-capo-2", "Capo 2: physical fret 3 from the nut, playing fret 1",
               _guitar(), _event(67), MappingConstraints(capo_fret=2)),
        Vector("guitar-capo-open", "Capo 2: the capoed pitch is the new open",
               _guitar(), _event(66), MappingConstraints(capo_fret=2)),
        Vector("guitar-ambiguous-tie", "Every weight zeroed, so all candidates tie exactly",
               _guitar(), _event(64), preferences=ALL_TIED),
        Vector("guitar-previous-position-movement", "Movement penalty from a prior position",
               _guitar(), _event(64),
               preferences=MappingPreferences(movement_weight=10.0),
               previous_string_id="string-1"),
        Vector("guitar-string-change", "String-change penalty from a prior position",
               _guitar(), _event(64),
               preferences=MappingPreferences(string_change_weight=10.0),
               previous_string_id="string-1"),
        Vector("guitar-string-jump-rejected", "maximum_string_jump rejects distant units",
               _guitar(), _event(64),
               MappingConstraints(maximum_string_jump=1), previous_string_id="string-1"),
        Vector("guitar-minimum-position", "Caller's minimum position excludes low candidates",
               _guitar(), _event(64), MappingConstraints(minimum_position=6.0)),
        Vector("guitar-maximum-position", "Caller's maximum position excludes high candidates",
               _guitar(), _event(64), MappingConstraints(maximum_position=6.0)),
        Vector("guitar-preferred-region", "Preferred region penalises without rejecting",
               _guitar(), _event(64),
               MappingConstraints(preferred_minimum_position=0.0,
                                  preferred_maximum_position=3.0),
               MappingPreferences(preferred_region_weight=5.0)),
        Vector("guitar-string-disabled", "Profile marks a string unavailable",
               _guitar_with_disabled("string-2"), _event(64)),
        Vector("guitar-string-excluded", "Request excludes a string by identity",
               _guitar(), _event(64),
               MappingConstraints(excluded_string_ids=frozenset({"string-2"}))),
        Vector("guitar-microtone-unrealizable", "Fixed frets cannot produce a quarter tone",
               _guitar(), _event(64, cents=50.0)),
        Vector("guitar-below-range", "Pitch below every open string is UNPLAYABLE",
               _guitar(), _event(30)),
        Vector("guitar-above-range", "Pitch beyond the neck is UNPLAYABLE",
               _guitar(), _event(100)),
        Vector("guitar-constraints-exclude-all", "Constraints leave no candidate at all",
               _guitar(), _event(64),
               MappingConstraints(allowed_string_ids=frozenset({"string-1"}),
                                  minimum_position=6.0)),
        Vector("bass-fretless-basic", "Fretless position carries fret_number = null",
               _bass(), _event(50)),
        Vector("bass-fretless-millimetres", "Fretless with a declared scale length",
               _bass(), _event(45)),
        Vector("bass-fretless-normalized-only", "Fretless with no scale length declared",
               _bass_without_scale_length(), _event(45)),
        Vector("bass-fretless-microtone", "A fretless instrument accepts a quarter tone",
               _bass(), _event(45, cents=50.0)),
        # C3 sits exactly 5 semitones above the open G string, where the bass
        # profile declares the "5" position marker.
        Vector("bass-fretless-marker", "A position landing on a reference marker",
               _bass(), _event(48)),
        Vector("mandolin-course-basic", "Course-level candidate, not per wire",
               _mandolin(), _event(74)),
        Vector("mandolin-course-tie", "Course-level exact tie",
               _mandolin(), _event(74), preferences=ALL_TIED),
        Vector("mandolin-course-open", "An open course",
               _mandolin(), _event(76)),
        Vector("mandolin-capo", "Course instrument under a capo",
               _mandolin(), _event(79), MappingConstraints(capo_fret=2)),
    )


def build() -> dict[str, Any]:
    """Run every vector and assemble the golden document."""
    return {
        "vector_schema": "msme_v1",
        "dev_order": "MSME-002",
        "vectors": [
            {"vector_id": v.vector_id, "description": v.description, "result": v.run()}
            for v in vectors()
        ],
    }


def main() -> int:
    GOLDEN_PATH.write_text(
        json.dumps(build(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {GOLDEN_PATH.name} with {len(vectors())} vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
