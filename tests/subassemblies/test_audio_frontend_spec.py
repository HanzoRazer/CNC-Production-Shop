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
    """Four things, each of which makes the instrument not-a-product if missed.

    Sound when the Pi is down, a guitar-appropriate input, headphones loud
    enough to practise through, and a power architecture that is not guessed at.
    """
    blockers = {
        r["requirement_id"]
        for r in spec["requirements"]
        if r["criticality"] == "shippable_blocker"
    }
    assert blockers == {
        "REQ-BYPASS",
        "REQ-HIZ",
        "REQ-HEADPHONE-DRIVE",
        "REQ-POWER-ARCH",
        "REQ-INPUT-HEADROOM",
    }


def test_mcu_absorption_does_not_overclaim(spec):
    """It reduces the pocket count. It does NOT make the solid body close.

    An earlier rationale said it did, on the strength of an area budget that
    later failed a real packing test. The correction is kept in the record so
    the claim cannot quietly return.
    """
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-MCU-ONBOARD"
    )
    assert "CORRECTED 2026-07-27" in req["rationale"]
    assert "cannot coexist at all" in req["rationale"]
    assert "reduces the shortfall without closing it" in req["rationale"]


def test_board_serves_both_lines_and_amortises_across_them(spec):
    """Restoring Khaya compute halves the NRE burden per line.

    A costing consequence, not a design one, and it belongs on the record
    before the budget model reads it.
    """
    notes = " ".join(spec["notes"])
    assert "critical path for BOTH product lines again" in notes
    assert "amortise across two lines rather than one" in notes


def test_acceptance_should_be_measured_in_the_harder_instrument(spec):
    """The Khaya pairs a single coil with onboard compute — the worst case."""
    questions = " ".join(spec["open_questions"])
    assert "worst EMC combination this board will meet" in questions
    assert "taken in THAT instrument, not the hollow one" in questions


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
    assert "critical path for BOTH product lines again" in notes


def test_power_architecture_is_stated_not_left_ambiguous(spec):
    """The largest gap in the Rev A tender: which way does power flow.

    A contractor who assumed this board feeds the Pi would design a 25 W
    converter and quote for it. Stating the mode removes that guess.
    """
    pa = spec["electrical"]["power_architecture"]
    assert pa["mode"] == "independent_rails"
    assert "does NOT supply the Raspberry Pi" in pa["rationale"]
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-POWER-ARCH"
    )
    assert req["criticality"] == "shippable_blocker"


def test_electrical_envelope_is_complete_enough_to_tender(spec):
    """Each of these was missing from Rev A and blocks a real quote."""
    el = spec["electrical"]
    sup = el["supply"]
    assert sup["input_min_v"] < sup["input_nominal_v"] < sup["input_max_v"]
    assert sup["quiescent_max_ma"] < sup["peak_max_ma"]
    assert el["audio"]["sample_rate_primary_khz"] == 48.0
    assert el["audio"]["bit_depth"] == 24
    assert el["audio"]["input_full_scale_vpp"] > el["audio"]["input_typical_vpp"]
    assert el["performance"]["adc_snr_db_a_weighted"] > 0
    assert el["thermal"]["component_rating_min_c"] > el["thermal"]["cavity_ambient_max_c"]


def test_every_electrical_figure_is_flagged_as_unconfirmed(spec):
    """These were proposed, not measured or specified. Say so, loudly.

    A number that loses its provenance becomes a number someone builds to.
    """
    prov = spec["electrical"]["provenance"]
    assert prov["source"] == "engineering_estimate"
    assert prov["confidence"] == "draft"
    assert "EVERY VALUE IN THIS BLOCK IS PROPOSED, NOT CONFIRMED" in prov["note"]
    assert "CONF-PICKUP-TYPE" in prov["note"]


def test_performance_figures_carry_measurement_methods(spec):
    """A MUST without a method can be neither demonstrated nor rejected."""
    conditions = " ".join(spec["electrical"]["measurement_conditions"])
    assert "A-weighted" in conditions
    assert "32 ohm" in conditions
    assert "NOT on open bench" in conditions
    # And the requirements themselves must carry the numbers.
    noise = next(r for r in spec["requirements"] if r["requirement_id"] == "REQ-NOISE")
    assert "95 dB" in noise["requirement"]
    phones = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-HEADPHONE-DRIVE"
    )
    assert "100 mW" in phones["requirement"] and "1% THD" in phones["requirement"]


def test_mcu_link_is_on_the_gpio_header_not_usb(spec):
    """Rev A offered USB-serial while its own table put the link on GPIO.

    A second cable is not in the cavity budget, so the ambiguity had to close.
    """
    req = next(r for r in spec["requirements"] if r["requirement_id"] == "REQ-MCU-LINK")
    assert "shall not require a separate USB cable" in req["requirement"]
    assert "40-pin GPIO header" in req["requirement"]


def test_pickup_type_no_longer_blocks_this_board(spec):
    """Fluid pickups are recorded as answered HERE and still open upstream.

    The board is made indifferent to the decision; the pickup ROUTE dimensions
    are a separate question this board does not touch.
    """
    questions = " ".join(spec["open_questions"])
    assert "Pickup type is FLUID by owner decision" in questions
    assert "no longer a blocker on this board" in questions
    assert "remains open upstream as CONF-PICKUP-TYPE" in questions


def test_commercial_gaps_are_recorded_as_open(spec):
    """Deliverables, IP and firmware scope are not engineering, but a tender
    without them is incomplete and they were absent from Rev A."""
    questions = " ".join(spec["open_questions"])
    assert "IP ownership" in questions
    assert "firmware" in questions


def test_every_requirement_has_an_acceptance_row(spec):
    """Traceability is what makes the document self-enforcing.

    Requirement IDs and a request for a test procedure are not the same as
    tying one to the other. Without this pairing a contractor cannot prove
    compliance and the buyer has no ground to reject work.
    """
    reqs = {r["requirement_id"] for r in spec["requirements"]}
    acc = {a["requirement_id"] for a in spec["acceptance"]}
    assert reqs == acc, f"uncovered: {sorted(reqs - acc)}, orphaned: {sorted(acc - reqs)}"
    for row in spec["acceptance"]:
        assert row["method"].strip() and row["pass_criterion"].strip()


def test_noise_acceptance_forbids_a_bench_measurement(spec):
    """The noise environment IS the requirement, so the venue is part of it."""
    row = next(a for a in spec["acceptance"] if a["requirement_id"] == "REQ-NOISE")
    assert "ASSEMBLED INSTRUMENT" in row["method"]
    assert "bench figure" in row["pass_criterion"]
    assert row["stage"] == "first_article"


def test_input_is_a_range_because_pickups_are_fluid(spec):
    """Specifying one level would tie the board to an open pickup decision.

    Headroom plus gain range makes the board indifferent to it, which is
    cheaper than a respin when the pickups change.
    """
    audio = spec["electrical"]["audio"]
    assert audio["input_full_scale_vpp"] == 4.0
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-INPUT-HEADROOM"
    )
    assert "30 dB of gain range" in req["requirement"]
    assert "FLUID" in req["requirement"]
    assert req["criticality"] == "shippable_blocker"
    # And it must no longer be blocked on the pickup conflict.
    assert "NO LONGER blocked" in spec["electrical"]["provenance"]["note"]


def test_noise_responsibility_boundary_is_stated(spec):
    """A pickup is an antenna. No input stage removes what arrives pre-summed.

    Stating the boundary protects a contractor from being held to something
    they cannot fix, and stops the buyer assuming a board fix exists.
    """
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-NOISE-BOUNDARY"
    )
    assert "not responsible for interference the pickup itself receives" in req["requirement"]
    assert "terminated in 10 kilohm, not through a live pickup" in req["requirement"]
    assert "INSTRUMENT problem" in req["rationale"]


def test_single_coil_risk_is_recorded_as_instrument_level(spec):
    """A P-90 is a single coil — the pickup humbuckers replaced.

    Losing common-mode rejection next to an onboard computer is a materially
    harder EMC problem, and it may constrain pickup choice rather than the
    other way round.
    """
    env = " ".join(spec["environment"])
    assert "A true single coil has no common-mode rejection" in env
    questions = " ".join(spec["open_questions"])
    assert "SINGLE-COIL EXPOSURE IS AN INSTRUMENT-LEVEL RISK" in questions
    assert "shielded mock-up" in questions
    # How the tone is obtained decides the size of the exposure, so the record
    # must distinguish the three cases rather than treat them as one.
    assert "coil-split humbucker loses rejection only in the split position" in questions
    assert "stacked noiseless single coil hum-cancels by construction" in questions
    assert "WORST mode" in questions
    req = next(
        r for r in spec["requirements"] if r["requirement_id"] == "REQ-INPUT-HEADROOM"
    )
    assert "a P-90 is a single coil, not a humbucker" in req["rationale"]


def test_document_is_an_rfi_not_a_tender(spec):
    """Concept status cannot be tendered against.

    Codec unselected, quantity unstated, several values proposed. Those are the
    right conditions to shortlist and cost, and the wrong ones to buy a design
    — so commercial terms stay out of scope until they resolve.
    """
    dc = spec["document_control"]
    assert dc["document_class"] == "rfi"
    assert dc["commercial_terms_in_scope"] is False
    assert spec["status"] == "concept"
    notes = " ".join(spec["notes"])
    assert "NOT A TENDER" in notes
    assert "padded number or an argument" in notes


def test_document_control_is_complete(spec):
    dc = spec["document_control"]
    assert dc["revision"] == "B"
    assert len(dc["revision_history"]) >= 2
    assert dc["revision_history"][-1]["revision"] == dc["revision"]
    # The contact is not yet named, and must say so rather than be absent.
    assert "TO BE NAMED BEFORE ISSUE" in dc["change_contact"]


def test_quantity_and_schedule_are_recorded_as_missing(spec):
    """Asking for BOM tiers implies volumes the document never commits to."""
    questions = " ".join(spec["open_questions"])
    assert "QUANTITY AND SCHEDULE ARE NOT STATED" in questions
    assert "first-article date" in questions


def test_headphone_interface_row_is_quantified(spec):
    """'Practice level' survived in the interface table after Table 2 fixed it."""
    row = next(
        i for i in spec["interfaces"] if i["interface_id"] == "HEADPHONE_OUT"
    )
    assert "100 mW into 32 ohm" in row["description"]
    assert "REQ-HEADPHONE-DRIVE" in row["description"]


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
