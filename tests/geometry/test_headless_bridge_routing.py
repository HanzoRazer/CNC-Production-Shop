"""Tests for the headless bridge routing envelope.

The bridge is the one piece of this instrument that cannot be traded against
anything else. A headless terminates ALL string tension there — no headstock
shares the load — so the block under it is structural, and the figures that
size it come from two hand-measured vendor sheets rather than vendor CAD.

What is worth guarding: that the block is derived and not typed, that leaving
the unit unselected sizes it for the worst case rather than the convenient one,
and that the reason it cannot sit over a hollow survives in the record.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "geometry" / "bridge_routing_v1.schema.json"
FIXTURE = ROOT / "fixtures" / "geometry" / "headless_bridge_routing_v1.json"


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def doc() -> dict:
    return load(FIXTURE)


def test_matches_schema(doc):
    jsonschema.validate(doc, load(SCHEMA))


def test_block_is_derived_from_the_candidates(doc):
    """Every block figure recomputed from the envelopes and the margins."""
    block = doc["derived_block"]
    margin = doc["screw_margin_mm"]
    floor = doc["min_floor_mm"]
    pool = doc["candidates"]

    assert block["rout_width_mm"] == max(c["rout_width_mm"] for c in pool)
    assert block["rout_length_mm"] == max(c["rout_length_mm"] for c in pool)
    assert block["max_depth_mm"] == max(c["max_depth_mm"] for c in pool)
    assert block["block_width_mm"] == pytest.approx(block["rout_width_mm"] + 2 * margin)
    assert block["block_length_mm"] == pytest.approx(block["rout_length_mm"] + 2 * margin)
    assert block["required_solid_depth_mm"] == pytest.approx(block["max_depth_mm"] + floor)
    assert block["remaining_below_mm"] == pytest.approx(
        block["blank_thickness_mm"] - block["required_solid_depth_mm"]
    )
    assert block["verdict"] == (
        "sufficient" if block["remaining_below_mm"] >= 0 else "insufficient"
    )


def test_unselected_unit_sizes_the_block_for_the_worst_case(doc):
    """An unmade decision must not shrink the block.

    Both candidates are hand-measured off different production guitars and they
    disagree in both axes — the R-Trem is deeper, the TransTrem wider. Until one
    is chosen the block has to swallow both, or choosing later becomes a
    surprise instead of a confirmation.
    """
    assert doc["selected_candidate"] is None
    block = doc["derived_block"]
    for c in doc["candidates"]:
        assert block["rout_width_mm"] >= c["rout_width_mm"]
        assert block["rout_length_mm"] >= c["rout_length_mm"]
        assert block["max_depth_mm"] >= c["max_depth_mm"]
    # And the two really do disagree, so this is not a vacuous check.
    widths = {c["rout_width_mm"] for c in doc["candidates"]}
    depths = {c["max_depth_mm"] for c in doc["candidates"]}
    assert len(widths) > 1 and len(depths) > 1


def test_levels_are_consistent_with_the_stated_depth(doc):
    for c in doc["candidates"]:
        assert c["levels"] == sorted(c["levels"]), f"{c['unit_id']} levels unordered"
        assert max(c["levels"]) == c["max_depth_mm"]


def test_the_rout_cannot_sit_over_a_hollow(doc):
    """The whole reason this record exists; it must not become a footnote."""
    notes = " ".join(doc["notes"])
    assert "CANNOT LAND IN THE HOLLOW" in notes
    assert "no headstock sharing the load" in notes or "no headstock" in notes
    # The block competes with the electronics for the tail, and wins.
    assert "first call" in notes


def test_measurement_provenance_is_not_dressed_up_as_vendor_cad(doc):
    """Both sheets are measurements of production guitars by one author.

    Recording them as if they were toleranced vendor drawings would invite
    someone to cut to them.
    """
    assert doc["provenance"]["confidence"] == "draft"
    note = doc["provenance"]["note"]
    assert "MEASUREMENTS OF PRODUCTION GUITARS" in note
    assert "not vendor CAD" in note
    for c in doc["candidates"]:
        assert c["measured_from"].strip()
    # The screw margin is ours, not theirs, and must say so.
    assert "engineering estimate" in note


def test_string_spacing_is_recorded_as_unmodelled(doc):
    """The rout must clear the strings as well as the casting."""
    notes = " ".join(doc["notes"])
    assert "String spacing is not modelled" in notes
