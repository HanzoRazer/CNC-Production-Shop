"""Mapping-result serialization and golden-vector tests.

Dev Order: MSME-002 Phase G

Every vector is regenerated from its declared inputs and compared to the
committed record. A golden file that were merely re-read and pretty-printed
would prove nothing; these run the engine.
"""

from __future__ import annotations

import json

import pytest

from musical_spatial_mapping.enums import SelectionStatus
from musical_spatial_mapping.mapper import MusicalSpatialMapper, equal_best_of
from musical_spatial_mapping.models import MappingConstraints
from musical_spatial_mapping.serialization import (
    mapping_result_from_dict,
    mapping_result_from_json,
    mapping_result_to_dict,
    mapping_result_to_json,
)

from .msme_vectors import ALL_TIED, GOLDEN_PATH, build, vectors
from .test_candidates import event, fretless_bass, guitar, mandolin


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def mapped(profile=None, midi=64, **kw):
    return MusicalSpatialMapper(profile=profile or guitar(), **kw).map(event(midi))


# ------------------------------------------------------------------ round trip


def test_a_result_round_trips_exactly():
    result = mapped()
    assert mapping_result_from_dict(mapping_result_to_dict(result)) == result


def test_a_result_round_trips_through_json():
    result = mapped()
    assert mapping_result_from_json(mapping_result_to_json(result)) == result


@pytest.mark.parametrize(
    ("profile", "midi", "kw"),
    [
        (guitar(), 64, {}),
        (guitar(), 67, {"constraints": MappingConstraints(capo_fret=2)}),
        (guitar(), 30, {}),                                   # UNPLAYABLE
        (guitar(), 64, {"preferences": ALL_TIED}),            # AMBIGUOUS
        (fretless_bass(), 50, {}),
        (fretless_bass(scale_length_mm=None), 50, {}),
        (mandolin(), 74, {}),
    ],
)
def test_every_shape_round_trips(profile, midi, kw):
    result = MusicalSpatialMapper(profile=profile, **kw).map(event(midi))
    assert mapping_result_from_dict(mapping_result_to_dict(result)) == result


def test_an_unplayable_result_serializes_as_a_result_not_an_error():
    data = mapping_result_to_dict(mapped(midi=30))
    assert data["status"] == "unplayable"
    assert data["selected"] is None
    assert data["candidates"] == []
    assert data["diagnostics"], "rejection evidence must survive serialization"


# ------------------------------------------------------- coordinates not collapsed


def test_the_three_coordinates_stay_three_objects():
    position = mapping_result_to_dict(mapped())["selected"]["position"]
    assert set(position) == {"string_id", "course_id", "sounding", "physical", "playing"}
    assert "midi_note" in position["sounding"]
    assert "semitone_offset_from_nut" in position["physical"]
    assert "semitone_offset_from_open" in position["playing"]


def test_the_capo_split_survives_serialization():
    """The regression the coordinate model exists for, in the stored artifact."""
    data = mapping_result_to_dict(
        mapped(midi=67, constraints=MappingConstraints(capo_fret=2))
    )
    position = data["selected"]["position"]
    assert position["physical"]["fret_number"] == 3
    assert position["playing"]["fret_relative_to_capo"] == 1
    assert position["physical"]["fret_number"] != position["playing"]["fret_relative_to_capo"]


def test_fretless_serializes_a_null_fret_and_keeps_its_position():
    position = mapping_result_to_dict(
        mapped(fretless_bass(), 50)
    )["selected"]["position"]
    assert position["physical"]["fret_number"] is None
    assert position["playing"]["fret_relative_to_capo"] is None
    assert position["physical"]["normalized_position"] > 0


def test_score_components_are_named_in_the_serialized_form():
    candidate = mapping_result_to_dict(mapped())["candidates"][0]
    assert candidate["score"]["components"]
    assert candidate["score"]["total"] == pytest.approx(
        sum(candidate["score"]["components"].values())
    )


# --------------------------------------------------------------------- ambiguity


def _spanish_guitar():
    """A profile whose name is not ASCII. Entirely ordinary, and the case that
    separates "stable structure" from "stable bytes"."""
    from musical_spatial_mapping.models import InstrumentProfile

    base = guitar()
    return InstrumentProfile(**{
        **base.__dict__,
        "display_name": "Guitarra Española",
        "instrument_id": "guitarra.española.6",
    })


def test_result_json_is_ascii_even_for_a_non_ascii_profile():
    """Ordered keys give stable STRUCTURE; escaping gives stable BYTES.

    A non-ASCII instrument name parses identically either way, so a structural
    comparison would never notice — but the bytes differ, and golden vectors and
    CLI output are compared as bytes.
    """
    result = MusicalSpatialMapper(profile=_spanish_guitar()).map(event(64))
    assert mapping_result_to_json(result).isascii()


def test_library_and_cli_emit_identical_bytes():
    """One payload, one byte contract. The CLI serializes through this function
    rather than its own json.dumps, so the two cannot drift apart."""
    import subprocess
    import sys as _sys

    from musical_spatial_mapping.serialization import instrument_profile_to_dict

    profile = _spanish_guitar()
    result = MusicalSpatialMapper(profile=profile).map(event(64))
    library = mapping_result_to_json(result, indent=2)

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "profile.json"
        path.write_text(
            json.dumps(instrument_profile_to_dict(profile)), encoding="utf-8"
        )
        proc = subprocess.run(
            [_sys.executable, "-m", "musical_spatial_mapping.cli",
             "--profile", str(path), "--event", '{"midi_note": 64, "event_id": "e1"}'],
            capture_output=True, text=True,
        )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == library.strip()


def test_readable_output_is_opt_in_and_not_byte_stable():
    """ensure_ascii=False stays available as a display choice, clearly labelled."""
    result = MusicalSpatialMapper(profile=_spanish_guitar()).map(event(64))
    readable = mapping_result_to_json(result, ensure_ascii=False)
    assert not readable.isascii()
    # Same structure either way — which is exactly why bytes need their own rule.
    assert json.loads(readable) == json.loads(mapping_result_to_json(result))


def test_no_equal_best_field_is_stored():
    """A stored copy of a derived fact could drift from the scores it summarises."""
    data = mapping_result_to_dict(mapped(preferences=ALL_TIED))
    assert "equal_best" not in data


def test_the_tie_is_reconstructable_from_the_serialized_result():
    result = mapped(preferences=ALL_TIED)
    restored = mapping_result_from_dict(mapping_result_to_dict(result))
    assert restored.status is SelectionStatus.AMBIGUOUS
    assert len(equal_best_of(restored)) == len(equal_best_of(result)) > 1


# ------------------------------------------------------------------ golden file


def test_the_golden_file_exists_and_meets_its_minimum(golden):
    assert golden["vector_schema"] == "msme_v1"
    assert len(golden["vectors"]) >= 20, "tests/golden/README.md requires at least 20"


def test_golden_vector_ids_are_unique_and_ordered(golden):
    ids = [v["vector_id"] for v in golden["vectors"]]
    assert len(ids) == len(set(ids))
    assert ids == [v.vector_id for v in vectors()]


@pytest.mark.parametrize("vector", vectors(), ids=lambda v: v.vector_id)
def test_every_vector_reproduces_its_golden_record(vector, golden):
    """Regenerated from inputs, compared structurally to the committed record."""
    stored = next(v for v in golden["vectors"] if v["vector_id"] == vector.vector_id)
    assert vector.run() == stored["result"]


def test_the_whole_golden_document_regenerates_identically(golden):
    assert build() == golden


def test_every_golden_result_round_trips_as_objects(golden):
    """The file is a contract about objects, not a rendering of text."""
    for entry in golden["vectors"]:
        restored = mapping_result_from_dict(entry["result"])
        assert mapping_result_to_dict(restored) == entry["result"], entry["vector_id"]


def test_the_golden_file_is_environment_independent():
    raw = GOLDEN_PATH.read_text(encoding="utf-8")
    assert raw.isascii(), "non-ASCII risks differing between writer and checker"
    lowered = raw.lower()
    for banned in ("timestamp", "created_at", "c:\\", "/home/", "/users/", "python3."):
        assert banned not in lowered, banned


def test_the_golden_file_ends_with_a_single_newline():
    raw = GOLDEN_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")


def test_the_golden_set_covers_every_status(golden):
    seen = {v["result"]["status"] for v in golden["vectors"]}
    assert seen == {"selected", "ambiguous", "unplayable"}


def test_the_golden_set_distinguishes_every_rejection_category(golden):
    """UNPLAYABLE must be able to say WHICH kind of limit applied."""
    codes = {
        line.split(":")[0]
        for v in golden["vectors"]
        for line in v["result"]["diagnostics"]
        if ":" in line
    }
    for expected in (
        "below_open_pitch",          # instrument feasibility
        "above_position_range",      # instrument feasibility
        "pitch_not_realizable",      # discrete geometry
        "position_constraint",       # caller window
        "string_excluded",           # caller identity
        "string_disabled",           # instrument feasibility
        "string_jump_constraint",    # caller movement
        "open_string_excluded",      # caller policy
    ):
        assert expected in codes, f"no golden vector exercises {expected}"


def test_the_golden_set_covers_all_three_instrument_families(golden):
    ids = {v["result"]["instrument_id"] for v in golden["vectors"]}
    assert ids == {"guitar.standard.6", "bass.fretless.4", "mandolin.standard.8"}


def test_golden_course_vectors_stay_at_course_level(golden):
    for entry in golden["vectors"]:
        if entry["result"]["instrument_id"] != "mandolin.standard.8":
            continue
        courses = [c["position"]["course_id"] for c in entry["result"]["candidates"]]
        assert all(c is not None for c in courses)
        assert len(courses) == len(set(courses)), entry["vector_id"]
