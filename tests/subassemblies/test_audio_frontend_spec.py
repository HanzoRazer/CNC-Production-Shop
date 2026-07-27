"""Tests for the Smart Guitar audio front-end subassembly spec.

This record is a brief handed to a PCB designer, so the things worth guarding
are the ones a designer would build wrong if they drifted: the envelope that
the cavity is derived from, the requirements that are behavioural rather than
mechanical, and the boundary between what the instrument dictates and what the
designer chooses.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "subassemblies" / "audio_frontend_spec_v1.schema.json"
SPEC = ROOT / "fixtures" / "subassemblies" / "sg_audio_frontend_v1.json"
REGISTER = ROOT / "fixtures" / "geometry" / "smart_guitar_component_register_v1.json"
GEOMETRY = ROOT / "fixtures" / "geometry" / "smart_guitar_cavity_geometry_v1.json"
VALIDATE = ROOT / "scripts" / "validate_smart_guitar_geometry.py"


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def spec() -> dict:
    return load(SPEC)


def test_spec_matches_schema(spec):
    jsonschema.validate(spec, load(SCHEMA))


def test_envelope_drives_the_cavity(spec):
    """The board's dimensions and the pocket's must be the same numbers.

    This is the whole point of writing the brief into the repo rather than a
    document: revise the board and the pocket follows, or the validator fails.
    """
    board = next(
        c
        for c in load(REGISTER)["components"]
        if c["component_id"] == spec["component_id"]
    )
    env = spec["envelope"]
    assert board["length_mm"] == env["board_length_mm"]
    assert board["width_mm"] == env["board_width_mm"]
    assert board["height_mm"] == env["assembly_height_target_mm"]

    pod = next(
        c for c in load(GEOMETRY)["cavities"] if c["cavity_id"] == "POD_HAT"
    )
    assert spec["component_id"] in pod["component_ids"]
    # depth = standoff + assembly height + lid clearance
    expected = board["standoff_mm"] + env["assembly_height_target_mm"] + board["lid_clearance_mm"]
    assert pod["derived_depth_mm"] == expected


def test_height_target_sits_below_its_own_ceiling(spec):
    """The target leaves deliberate margin before the blank must grow."""
    env = spec["envelope"]
    assert env["assembly_height_target_mm"] < env["assembly_height_max_mm"]
    assert env["assembly_height_max_mm"] - env["assembly_height_target_mm"] == 6.0
    # And the ceiling is derived, not chosen.
    assert "47.0" in env["derivation"] and "8.0" in env["derivation"]


def test_bypass_is_a_shippable_blocker(spec):
    """An instrument silent while Linux boots is not a product.

    Recorded as a behavioural requirement with a criticality, so it cannot be
    quietly traded away as an implementation detail.
    """
    req = next(r for r in spec["requirements"] if r["requirement_id"] == "REQ-BYPASS")
    assert req["criticality"] == "shippable_blocker"
    assert "default to bypass on loss of power" in req["requirement"]


def test_blockers_are_the_ones_that_define_the_product(spec):
    blockers = {
        r["requirement_id"]
        for r in spec["requirements"]
        if r["criticality"] == "shippable_blocker"
    }
    assert blockers == {"REQ-BYPASS", "REQ-HIZ", "REQ-HEADPHONE-DRIVE"}


def test_mcu_absorption_records_why_it_is_required(spec):
    """It is not tidiness — it is what makes the solid body close."""
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-MCU-ONBOARD"
    )
    assert "37 cm2 short" in req["rationale"]


def test_spec_defers_circuit_design_to_the_designer(spec):
    """The brief must not pretend to be a design.

    It carries envelope, interfaces and behaviour. Topology, part numbers and
    component values are the designer's, and saying so prevents this record
    from being read as more settled than it is.
    """
    notes = " ".join(spec["notes"])
    assert "does NOT specify circuit topology" in notes
    assert spec["status"] == "concept"
    assert "No schematic exists" in notes


def test_i2s_versus_usb_is_open_and_not_blamed_on_latency(spec):
    """Latency does not decide it, and the record must not say it did.

    The existing USB path already meets the budget at 3.1 ms against 5 ms, so
    an all-I2S path buys headroom rather than meeting a requirement.
    """
    questions = " ".join(spec["open_questions"])
    assert "I2S versus USB has NOT been settled" in questions
    assert "Latency does not decide it" in questions
    assert "3.1 ms" in questions


def test_certification_is_scoped_to_the_finished_assembly(spec):
    """The Pi's own certification does not transfer to a product containing it."""
    cert = " ".join(spec["certification"])
    assert "FINISHED ASSEMBLY" in cert
    assert "does not transfer" in cert
    assert "ground-loop" in cert


def test_interfaces_are_wire_to_board_not_panel_jacks(spec):
    """In a guitar the jacks are body-mounted; the board takes flying leads."""
    audio = [
        i
        for i in spec["interfaces"]
        if i["interface_id"] in ("INSTRUMENT_IN", "AMP_OUT", "HEADPHONE_OUT")
    ]
    assert len(audio) == 3
    assert all(i["connection"] == "wire_to_board" for i in audio)


def test_spec_records_that_the_instrument_constrains_the_board(spec):
    """Adjacency and pack size stopped being preferences; say so."""
    notes = " ".join(spec["notes"])
    assert "must be ADJACENT" in notes
    assert "2x 18650" in notes
    assert "critical path for BOTH product lines" in notes


def test_validator_enforces_the_envelope_link():
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sg_audio_frontend_v1.json" in result.stdout
    assert "frontend envelope" in result.stdout
