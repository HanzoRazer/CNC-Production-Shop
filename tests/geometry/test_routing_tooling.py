"""Tests for the routing tooling record.

One decision — the cutter diameter — sets every internal corner radius in the
instrument. What is worth guarding is that the radii stay derived from it, that
the precision survives (3.175 is exactly 1/8 inch and must not be rounded to a
pocket-wall convention), and that reach is checked as well as radius: a corner
radius costs nothing, a cut deeper than the tool's flute length is a real
manufacturing constraint.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "geometry" / "routing_tooling_v1.schema.json"
FIXTURE = ROOT / "fixtures" / "geometry" / "routing_tooling_v1.json"
GEOMETRY = ROOT / "fixtures" / "geometry" / "smart_guitar_cavity_geometry_v1.json"


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def doc() -> dict:
    return load(FIXTURE)


def test_matches_schema(doc):
    jsonschema.validate(doc, load(SCHEMA))


def test_every_radius_is_the_cutter_halved(doc):
    radius = doc["cutter_diameter_mm"] / 2
    assert doc["derived"]["internal_corner_radius_mm"] == pytest.approx(radius, abs=1e-6)
    for row in doc["cavities"]:
        assert row["corner_radius_mm"] == pytest.approx(radius, abs=1e-6)


def test_radius_precision_is_not_rounded_to_the_pocket_convention(doc):
    """3.175 is exactly 1/8 inch. The geometry convention would make it 3.17.

    Two-decimal rounding is right for a pocket wall and wrong for a cutter
    radius — it is the difference between a tool that exists and one that does
    not.
    """
    assert doc["derived"]["internal_corner_radius_mm"] == 3.175
    assert doc["cutter_diameter_mm"] == 6.35


def test_square_corners_clear_the_radius(doc):
    """A square PCB corner cannot reach into a radiused pocket corner.

    The leftover material reaches r*(sqrt(2)-1) from the true corner along the
    diagonal. That has to be smaller than the clearance already carried around
    each board, or the pockets need corner relief — and they do not.
    """
    derived = doc["derived"]
    radius = derived["internal_corner_radius_mm"]
    diagonal = radius * (math.sqrt(2) - 1)
    assert derived["square_corner_intrusion_diagonal_mm"] == pytest.approx(diagonal, abs=0.005)
    assert derived["square_corner_intrusion_per_axis_mm"] == pytest.approx(
        diagonal / math.sqrt(2), abs=0.005
    )
    assert derived["square_corner_intrusion_per_axis_mm"] < doc["part_clearance_per_side_mm"]
    assert derived["clearance_verdict"] == "absorbed"
    # And the record must say no relief is needed, so nobody adds any.
    notes = " ".join(doc["notes"])
    assert "No corner relief is needed" in notes


def test_reach_is_classified_against_real_flute_lengths(doc):
    """Radius is free; depth is not. Two pockets exceed a stock cutter."""
    geometry = {c["cavity_id"]: c for c in load(GEOMETRY)["cavities"]}
    std = doc["standard_cut_length_mm"]
    long_series = doc["long_series_cut_length_mm"]
    assert std < long_series

    for row in doc["cavities"]:
        depth = geometry[row["cavity_id"]]["derived_depth_mm"]
        assert row["depth_mm"] == depth
        expected = (
            "standard"
            if depth <= std
            else ("long_series" if depth <= long_series else "beyond_long_series")
        )
        assert row["reach_class"] == expected
        if expected != "standard":
            assert row.get("note", "").strip(), f"{row['cavity_id']} needs a note"

    deep = {r["cavity_id"] for r in doc["cavities"] if r["reach_class"] != "standard"}
    assert deep == {"POD_PI", "POD_HAT"}


def test_the_cutter_actually_fits_every_pocket(doc):
    for row in doc["cavities"]:
        assert row["min_plan_dimension_mm"] > doc["cutter_diameter_mm"]
        assert row["tool_entry"] == "fits"


def test_tooling_covers_every_cavity_in_the_geometry(doc):
    """A cavity with no tooling entry is a cavity nobody has thought about."""
    assert {r["cavity_id"] for r in doc["cavities"]} == {
        c["cavity_id"] for c in load(GEOMETRY)["cavities"]
    }


def test_bridge_is_deliberately_excluded(doc):
    """Its radii come from the vendor drawing, not from the shop's cutter."""
    notes = " ".join(doc["notes"])
    assert "bridge rout is excluded" in notes
    assert "R6" in notes
