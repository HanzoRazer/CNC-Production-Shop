"""Tests for the bundled example profiles: schema conformance, semantic
validation, and serialization round-trip.

Dev Order: MSME-001

jsonschema is used here (a boundary/tooling concern) but never by the engine core.
"""

import json
from importlib.resources import files

import jsonschema
import pytest

from musical_spatial_mapping import (
    FingerboardMode,
    instrument_profile_from_dict,
    instrument_profile_to_dict,
)
from musical_spatial_mapping.fixtures import all_example_profiles

_PKG = "musical_spatial_mapping"
_EXAMPLES = ("guitar-standard-6.json", "bass-fretless-4.json", "mandolin-standard.json")


def _load_schema() -> dict:
    text = (
        files(_PKG)
        .joinpath("resources", "instruments", "schema", "instrument-profile-v1.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _load_raw(filename: str) -> dict:
    text = (
        files(_PKG)
        .joinpath("resources", "instruments", "examples", filename)
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


@pytest.mark.parametrize("filename", _EXAMPLES)
def test_example_conforms_to_schema(filename):
    jsonschema.validate(instance=_load_raw(filename), schema=_load_schema())


@pytest.mark.parametrize("filename", _EXAMPLES)
def test_example_loads_and_validates(filename):
    profile = instrument_profile_from_dict(_load_raw(filename))
    assert profile.strings  # semantic validation ran inside from_dict


@pytest.mark.parametrize("filename", _EXAMPLES)
def test_round_trip_is_stable(filename):
    profile = instrument_profile_from_dict(_load_raw(filename))
    again = instrument_profile_from_dict(instrument_profile_to_dict(profile))
    assert again == profile


def test_all_three_structurally_different_profiles_valid():
    profiles = all_example_profiles()
    assert len(profiles) == 3
    by_id = {p.instrument_id: p for p in profiles}

    guitar = by_id["guitar.standard.6"]
    assert guitar.fingerboard_mode == FingerboardMode.FRETTED
    assert guitar.fret_count == 22
    assert len(guitar.strings) == 6

    bass = by_id["bass.fretless.4"]
    assert bass.fingerboard_mode == FingerboardMode.FRETLESS
    assert bass.fret_count is None
    assert len(bass.strings) == 4

    mandolin = by_id["mandolin.standard.8"]
    assert len(mandolin.strings) == 8
    # course-aware: eight strings collapse to four courses
    courses = {s.course_id for s in mandolin.strings}
    assert courses == {"course-e", "course-a", "course-d", "course-g"}
