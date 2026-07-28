"""Tests for SMART-GUITAR-CAVITY-GEOMETRY-1.

Covers the derivation rules, the fit verdicts, the body-thickness derivation,
conflict propagation, and the governance boundary that keeps cost and time out
of a physical record.

The central regression these tests protect is the one that motivated the Dev
Order: a cavity dimension must never be readable as an input, so a stale note
in a source spec cannot propagate into anything downstream.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import jsonschema
import pytest

from business.geometry.cavity_derivation import (
    VERDICT_INSUFFICIENT,
    VERDICT_SUFFICIENT,
    as_mm,
    derive_cavity,
    derive_cavity_depth,
    derive_cavity_footprint,
    derive_cavity_geometry,
    derive_required_body_thickness,
    mm_equal,
)
from business.geometry.loading import load_component_register
from business.geometry.models import (
    CavityPlanV1,
    ComponentV1,
    GeometryProvenanceV1,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas" / "geometry"
REGISTER_SCHEMA = SCHEMAS / "smart_guitar_component_register_v1.schema.json"
GEOMETRY_SCHEMA = SCHEMAS / "smart_guitar_cavity_geometry_v1.schema.json"
FIXTURES = ROOT / "fixtures" / "geometry"
REGISTER = FIXTURES / "smart_guitar_component_register_v1.json"
GEOMETRY = FIXTURES / "smart_guitar_cavity_geometry_v1.json"
VALIDATE = ROOT / "scripts" / "validate_smart_guitar_geometry.py"
DOC = ROOT / "docs" / "geometry" / "SMART_GUITAR_CAVITY_GEOMETRY_V1.md"

BODY_THICKNESS_MM = 47.0


def load_module_by_path(path: Path):
    """Import a script that lives outside any package."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _prov() -> GeometryProvenanceV1:
    return GeometryProvenanceV1(
        source="engineering_estimate",
        source_ref="test",
        snapshot_date="2026-07-26",
        confidence="draft",
    )


def _component(
    component_id: str,
    length: float,
    width: float,
    height: float,
    *,
    mounting: str = "floor",
    standoff: float = 0.0,
    margin_l: float = 0.0,
    margin_w: float = 0.0,
    lid_clearance: float = 0.0,
    consumes: bool = True,
    required: bool = True,
) -> ComponentV1:
    return ComponentV1(
        component_id=component_id,
        display_name=component_id,
        role="test",
        length_mm=length,
        width_mm=width,
        height_mm=height,
        mounting=mounting,
        standoff_mm=standoff,
        margin_length_mm=margin_l,
        margin_width_mm=margin_w,
        lid_clearance_mm=lid_clearance,
        consumes_cavity_depth=consumes,
        required=required,
        provenance=_prov(),
    )


def _plan(
    cavity_id: str,
    component_ids: tuple[str, ...],
    layout: str,
    *,
    inter_margin: float = 0.0,
    min_floor: float = 8.0,
    **stated: float | None,
) -> CavityPlanV1:
    return CavityPlanV1(
        cavity_id=cavity_id,
        description="test",
        surface="back",
        layout=layout,
        component_ids=component_ids,
        inter_component_margin_mm=inter_margin,
        min_floor_mm=min_floor,
        provenance=_prov(),
        **stated,
    )


def _register():
    return load_component_register(REGISTER)


def _recompute():
    stored = load_json(GEOMETRY)
    return stored, derive_cavity_geometry(
        _register(),
        geometry_id=stored["geometry_id"],
        register_ref=stored["register_ref"],
        effective_date=stored["calculation"]["effective_date"],
    )


# --------------------------------------------------------------------------
# Depth rules: the arithmetic that made stacking impossible
# --------------------------------------------------------------------------


def test_side_by_side_depth_is_the_tallest_not_the_sum():
    parts = [
        _component("A", 85, 56, 18, standoff=6, lid_clearance=3),
        _component("B", 65, 56, 24, standoff=6, lid_clearance=3),
    ]
    assert derive_cavity_depth(parts, "side_by_side") == 33.0


def test_stacked_depth_sums_and_exceeds_the_smart_guitar_blank():
    """The finding that forced the ruling: stacked is 58 mm, over any blank."""
    parts = [
        _component("PI5", 85, 56, 18, standoff=6),
        _component("HAT", 65, 56, 24, standoff=10),
    ]
    stacked = derive_cavity_depth(parts, "stacked")
    assert stacked == 58.0
    assert stacked > BODY_THICKNESS_MM


def test_lid_mounted_part_adds_depth_only_when_it_consumes_it():
    boards = [_component("PI5", 85, 56, 18, standoff=6, lid_clearance=3)]
    venting_fan = _component("FAN", 40, 40, 10, mounting="lid", consumes=False)
    internal_fan = _component("FAN", 40, 40, 10, mounting="lid", consumes=True)

    assert derive_cavity_depth([*boards, venting_fan], "side_by_side") == 27.0
    assert derive_cavity_depth([*boards, internal_fan], "side_by_side") == 37.0


def test_footprint_sums_lengths_only_for_side_by_side():
    parts = [
        _component("A", 85, 56, 18, margin_l=4, margin_w=4),
        _component("B", 65, 56, 24, margin_l=4, margin_w=4),
    ]
    length, width = derive_cavity_footprint(parts, "side_by_side", 4.0)
    assert (length, width) == (162.0, 64.0)

    # Stacked overlaps in plan, so the largest single footprint governs.
    length, width = derive_cavity_footprint(parts, "stacked", 4.0)
    assert (length, width) == (93.0, 64.0)


def test_lid_mounted_part_does_not_consume_plan_length():
    """A fan sits above the boards, not beside them."""
    parts = [
        _component("A", 85, 56, 18, margin_l=4, margin_w=4),
        _component("B", 65, 56, 24, margin_l=4, margin_w=4),
        _component("FAN", 40, 40, 10, mounting="lid", margin_l=2, margin_w=2),
    ]
    length, _ = derive_cavity_footprint(parts, "side_by_side", 4.0)
    assert length == 162.0


def test_lid_part_widens_cavity_when_larger_than_the_boards():
    parts = [
        _component("SMALL", 20, 20, 5),
        _component("BIGLID", 90, 70, 5, mounting="lid", margin_l=3, margin_w=3),
    ]
    length, width = derive_cavity_footprint(parts, "single", 0.0)
    assert (length, width) == (96.0, 76.0)


def test_empty_component_set_rejected():
    with pytest.raises(ValueError, match="at least one component"):
        derive_cavity_footprint([], "single", 0.0)


# --------------------------------------------------------------------------
# Fit verdicts and the stated-versus-derived comparison
# --------------------------------------------------------------------------


def test_stated_smaller_than_derived_produces_a_finding():
    """sg-spec's 30.48 mm pod against its own 33 mm of contents."""
    registry = {
        "A": _component("A", 85, 56, 18, standoff=6, lid_clearance=3, margin_l=4, margin_w=4),
        "B": _component("B", 65, 56, 24, standoff=6, lid_clearance=3, margin_l=4, margin_w=4),
    }
    plan = _plan("POD", ("A", "B"), "side_by_side", inter_margin=4.0, stated_depth_mm=30.48)
    result = derive_cavity(plan, registry, BODY_THICKNESS_MM)

    assert result.derived_depth_mm == 33.0
    assert result.depth_delta_mm == -2.52
    assert any("cannot hold its own contents" in f for f in result.findings)
    assert result.fit_ok is True


def test_slack_is_reported_but_is_not_a_failure():
    registry = {"A": _component("A", 61, 18, 3, standoff=4, lid_clearance=4.5)}
    plan = _plan("POCKET", ("A",), "single", stated_depth_mm=20.0)
    result = derive_cavity(plan, registry, BODY_THICKNESS_MM)

    assert result.derived_depth_mm == 11.5
    assert result.depth_delta_mm == 8.5
    assert any("slack" in f for f in result.findings)
    assert result.fit_ok is True


def test_cavity_that_breaches_min_floor_fails_fit():
    registry = {"BIG": _component("BIG", 50, 50, 45, standoff=0)}
    plan = _plan("DEEP", ("BIG",), "single", min_floor=8.0)
    result = derive_cavity(plan, registry, BODY_THICKNESS_MM)

    assert result.floor_remaining_mm == 2.0
    assert result.fit_ok is False
    assert any("does not fit" in f for f in result.findings)


def test_required_thickness_is_governed_by_deepest_plus_floor():
    registry = {
        "SHALLOW": _component("SHALLOW", 10, 10, 5),
        "DEEP": _component("DEEP", 10, 10, 30),
    }
    plans = [
        _plan("A", ("SHALLOW",), "single", min_floor=8.0),
        _plan("B", ("DEEP",), "single", min_floor=8.0),
    ]
    derivations = [derive_cavity(p, registry, BODY_THICKNESS_MM) for p in plans]
    body = derive_required_body_thickness(derivations, BODY_THICKNESS_MM)

    assert body.governing_cavity_id == "B"
    assert body.required_thickness_mm == 38.0
    assert body.margin_mm == 9.0
    assert body.verdict == VERDICT_SUFFICIENT


def test_insufficient_blank_is_reported_with_negative_margin():
    registry = {"DEEP": _component("DEEP", 10, 10, 50)}
    derivations = [derive_cavity(_plan("B", ("DEEP",), "single"), registry, BODY_THICKNESS_MM)]
    body = derive_required_body_thickness(derivations, BODY_THICKNESS_MM)

    assert body.required_thickness_mm == 58.0
    assert body.margin_mm == -11.0
    assert body.verdict == VERDICT_INSUFFICIENT


def test_body_derivation_requires_at_least_one_cavity():
    with pytest.raises(ValueError, match="at least one cavity"):
        derive_required_body_thickness([], BODY_THICKNESS_MM)


# --------------------------------------------------------------------------
# Structural validation of the register
# --------------------------------------------------------------------------


def test_unknown_component_reference_rejected():
    register = _register()
    plans = list(register.cavity_plans)
    plans[0] = replace(plans[0], component_ids=("GHOST",))
    with pytest.raises(ValueError, match="unknown component_id"):
        derive_cavity_geometry(
            replace(register, cavity_plans=tuple(plans)),
            register_ref="x",
            effective_date="2026-07-26",
        )


def test_component_placed_in_two_cavities_rejected():
    register = _register()
    plans = list(register.cavity_plans)
    plans[1] = replace(plans[1], component_ids=("PI5",))
    with pytest.raises(ValueError, match="more than one cavity"):
        derive_cavity_geometry(
            replace(register, cavity_plans=tuple(plans)),
            register_ref="x",
            effective_date="2026-07-26",
        )


def test_unplaced_required_component_rejected():
    register = _register()
    plans = [p for p in register.cavity_plans if p.cavity_id != "BATTERY_CHAMBER"]
    with pytest.raises(ValueError, match="required components are not placed"):
        derive_cavity_geometry(
            replace(register, cavity_plans=tuple(plans)),
            register_ref="x",
            effective_date="2026-07-26",
        )


def test_unplaced_optional_component_is_allowed():
    """The NVMe is registered but deliberately not placed."""
    register = _register()
    placed = {cid for p in register.cavity_plans for cid in p.component_ids}
    assert "NVME_SSD" not in placed
    nvme = next(c for c in register.components if c.component_id == "NVME_SSD")
    assert nvme.required is False


def test_duplicate_cavity_id_rejected():
    register = _register()
    plans = list(register.cavity_plans)
    plans[1] = replace(plans[1], cavity_id=plans[0].cavity_id, component_ids=("TEENSY_4_1",))
    with pytest.raises(ValueError, match="duplicate cavity_id"):
        derive_cavity_geometry(
            replace(register, cavity_plans=tuple(plans)),
            register_ref="x",
            effective_date="2026-07-26",
        )


def test_negative_component_dimension_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _component("BAD", 10, 10, -1)


def test_unsupported_mounting_rejected():
    with pytest.raises(ValueError, match="unsupported mounting"):
        _component("BAD", 10, 10, 5, mounting="ceiling")


def test_unsupported_layout_rejected():
    with pytest.raises(ValueError, match="unsupported layout"):
        _plan("X", ("A",), "interleaved")


def test_single_layout_requires_exactly_one_component():
    with pytest.raises(ValueError, match="exactly one component"):
        _plan("X", ("A", "B"), "single")


def test_draft_provenance_cannot_produce_approved_register():
    register = _register()
    with pytest.raises(ValueError, match="draft provenance"):
        derive_cavity_geometry(
            replace(register, status="reviewed"),
            register_ref="x",
            effective_date="2026-07-26",
        )


# --------------------------------------------------------------------------
# The committed fixtures
# --------------------------------------------------------------------------


def test_fixtures_match_schemas():
    jsonschema.validate(load_json(REGISTER), load_json(REGISTER_SCHEMA))
    jsonschema.validate(load_json(GEOMETRY), load_json(GEOMETRY_SCHEMA))


def test_stored_geometry_matches_recomputation():
    stored, recomputed = _recompute()
    expected = asdict(recomputed)

    for key, value in expected["body"].items():
        actual = stored["body"][key]
        assert mm_equal(actual, value) if isinstance(value, float) else actual == value, key

    stored_cavities = {c["cavity_id"]: c for c in stored["cavities"]}
    assert set(stored_cavities) == {c["cavity_id"] for c in expected["cavities"]}
    for cavity in expected["cavities"]:
        actual = stored_cavities[cavity["cavity_id"]]
        for key, value in cavity.items():
            if isinstance(value, float):
                assert mm_equal(actual[key], value), f"{cavity['cavity_id']}.{key}"
            elif isinstance(value, (list, tuple)):
                assert list(actual[key]) == list(value), f"{cavity['cavity_id']}.{key}"
            else:
                assert actual[key] == value, f"{cavity['cavity_id']}.{key}"


def test_pod_is_split_into_two_pockets_that_both_fit():
    """The one-piece pod had no valid position anywhere in the outline.

    Splitting is not a preference: a 162 x 64 slab could not be placed inside
    the body with rim inset and void clearance at any position, and growing
    the body to accept it needed 1.381x — a 556 x 647 mm instrument.
    """
    stored = load_json(GEOMETRY)
    by_id = {c["cavity_id"]: c for c in stored["cavities"]}

    assert "ELECTRONICS_POD" not in by_id
    pi, hat = by_id["POD_PI"], by_id["POD_HAT"]

    assert (pi["derived_length_mm"], pi["derived_depth_mm"]) == (93.0, 27.0)
    assert (hat["derived_length_mm"], hat["derived_depth_mm"]) == (73.0, 33.0)
    # The front-end board is 0.5 mm wider than the HAT it replaces.
    assert hat["derived_width_mm"] == 64.5
    assert pi["fit_ok"] and hat["fit_ok"]
    assert stored["body"]["governing_cavity_id"] == "POD_HAT"


def test_wire_channel_is_too_narrow_in_the_spec_for_a_ribbon():
    """Modelling the ribbon as a part exposed a channel that cannot hold it.

    sg-spec sizes its wiring channel at 10 mm, adequate for discrete leads.
    A 40-way GPIO ribbon needs 30. This surfaced only because the ribbon was
    registered as a component rather than described in a note.
    """
    channel = next(
        c for c in load_json(GEOMETRY)["cavities"]
        if c["cavity_id"] == "WIRE_CHANNEL_PI_HAT"
    )
    assert channel["stated_width_mm"] == 10.0
    assert channel["derived_width_mm"] == 30.0
    assert channel["width_delta_mm"] == -20.0
    assert any("cannot hold its own contents" in f for f in channel["findings"])


def test_ribbon_length_constrains_pocket_separation():
    """The channel's derived length IS the maximum pocket separation.

    Set to 100 mm. It was briefly 60 mm, chosen on an area argument about the
    channel's own cost — which was geometrically impossible: the pockets need
    72.25 mm centre-to-centre stacked before their walls clear, so a 60 mm
    ribbon forbade the layout outright at any body size. A constraint has to be
    physically achievable to be worth expressing.
    """
    stored = load_json(GEOMETRY)
    channel = next(
        c for c in stored["cavities"] if c["cavity_id"] == "WIRE_CHANNEL_PI_HAT"
    )
    assert channel["derived_length_mm"] == 100.0
    # 60 mm was geometrically impossible: the pockets need 72.25 mm stacked.
    assert channel["derived_length_mm"] > 72.25
    assert "GPIO_RIBBON" in channel["component_ids"]

    register = _register()
    ribbon = next(c for c in register.components if c.component_id == "GPIO_RIBBON")
    assert ribbon.required is True
    assert "stock GPIO extension ribbon" in ribbon.provenance.note
    assert "geometrically IMPOSSIBLE" in ribbon.provenance.note
    assert "72.25 mm" in ribbon.provenance.note


def test_frontend_board_replaces_both_the_hat_and_the_teensy():
    """Absorbing the MCU is what makes the electronics fit the solid body.

    With a separate Teensy module the solid line is 37 cm2 short; with its
    functions on the front-end board it has 35 cm2 spare.
    """
    register = _register()
    ids = {c.component_id for c in register.components}
    assert "SG_AUDIO_FRONTEND" in ids
    assert "HIFIBERRY_DAC_ADC" not in ids
    assert "TEENSY_4_1" not in ids

    cavities = {c["cavity_id"] for c in load_json(GEOMETRY)["cavities"]}
    assert "TEENSY_IO_POCKET" not in cavities

    board = next(c for c in register.components if c.component_id == "SG_AUDIO_FRONTEND")
    assert board.required is True
    assert "ENVELOPE" in board.provenance.note
    assert "no schematic exists" in board.provenance.note


def test_fan_venting_is_ruled_not_assumed():
    """The last blocker on this record. Ruled, and it confirms the model.

    Nothing derived changes, but the body-thickness verdict stops being
    provisional: the 3.45 mm margin is now real rather than contingent on an
    unstated mounting choice.
    """
    fan = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-FAN-INTRUSION"
    )
    assert fan["status"] == "ruled"
    assert "vents OUTWARD" in fan["ruling"]
    assert "owner ruling" in fan["ruled_by"]

    register = _register()
    fan_part = next(c for c in register.components if c.component_id == "FAN_40MM")
    assert fan_part.mounting == "lid"
    assert fan_part.consumes_cavity_depth is False
    assert fan_part.depth_demand_mm == 0.0

    stored = load_json(GEOMETRY)
    assert stored["body"]["verdict"] == VERDICT_SUFFICIENT
    assert stored["body"]["margin_mm"] == 6.0


def test_internal_fan_would_break_the_blank():
    """Counterfactual: an internally mounted fan does not fit the 47.0 blank.

    The fan lives in POD_PI since the split, so this now tests that pocket.
    """
    register = _register()
    components = [
        replace(c, consumes_cavity_depth=True) if c.component_id == "FAN_40MM" else c
        for c in register.components
    ]
    result = derive_cavity_geometry(
        replace(register, components=tuple(components)),
        register_ref="x",
        effective_date="2026-07-26",
    )
    pod_pi = next(c for c in result.cavities if c.cavity_id == "POD_PI")
    assert pod_pi.derived_depth_mm == 37.0
    assert pod_pi.floor_remaining_mm == 10.0
    # POD_HAT still governs at 33 + 8, so the blank survives — but the Pi
    # pocket loses 10 mm of floor, which is the cost worth seeing.
    assert result.body.verdict == VERDICT_SUFFICIENT


def test_every_cavity_fits_the_stated_blank():
    stored = load_json(GEOMETRY)
    assert all(c["fit_ok"] for c in stored["cavities"])


def test_conflicts_propagate_verbatim_into_the_derived_record():
    stored = load_json(GEOMETRY)
    register_raw = load_json(REGISTER)
    assert stored["conflicts"] == register_raw["conflicts"]


def test_unresolved_conflicts_are_recorded_not_hidden():
    stored = load_json(GEOMETRY)
    unresolved = {c["conflict_id"] for c in stored["conflicts"] if c["status"] == "unresolved"}
    assert {
        "CONF-PICKUP-TYPE",
        "CONF-PICKUP-ROUTE-DIMS",
        "CONF-SINGLE-PICKUP-EMC",
    } <= unresolved


def test_pickup_emc_conflict_awaits_measurement_not_derivation():
    """The one question the register cannot answer by calculating.

    Everything else here is derived from dimensions. This one needs a shielded
    mock-up on a bench, so it must stay unresolved however tempting the
    engineering judgement is, and it must point at the procedure that settles
    it rather than at a number nobody measured.
    """
    conflict = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-SINGLE-PICKUP-EMC"
    )
    assert conflict["status"] == "unresolved"
    assert "CANNOT BE SETTLED BY DERIVATION" in conflict["ruling"]
    assert "SG_PICKUP_EMC_MOCKUP_PROCEDURE.md" in conflict["ruling"]
    assert "no measurement has been taken" in conflict["ruling"]
    # Failing it re-opens the packing that put compute back in the Khaya.
    assert "CONF-SINGLE-PICKUP-SPACE" in conflict["ruling"]
    # The field no longer quotes a separation: every one was withdrawn.
    assert "71.6" not in conflict["field"]
    assert "one cavity set with a Raspberry Pi 5" in conflict["field"]
    # Moving the pockets improved the geometry; it did not answer the question.
    assert "GEOMETRY IMPROVED but the question stands" in conflict["ruling"]
    assert any("THEN WITHDRAWN" in x for x in conflict["sources"])


def test_pocket_relocation_improved_both_coupling_axes():
    """The relocation had to beat the old layout on the analog board too.

    Maximising POD_PI's distance from the pickup alone lands it 8.5 mm from
    POD_HAT, which swaps the pickup coil for the more sensitive analog front
    end. The ruled placement maximises distance to the nearest victim, so it
    dominates the old layout rather than trading against it.
    """
    conflict = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-POD-EMC-CLEARANCE"
    )
    # Invalidated by CONF-VOID-SET-SOURCE: the REASONING stands and should be
    # re-applied once the void set is ruled, but the coordinates must not be
    # readable as good.
    assert conflict["status"] == "unresolved"
    assert conflict["ruling"].startswith("PLACEMENT INVALIDATED")
    assert "DO NOT CUT FROM THEM" in conflict["ruling"]
    assert "STRICTLY BETTER" in conflict["ruling"]
    assert "10.75 mm to 35.75 mm" in conflict["ruling"]
    assert "NEAREST victim" in conflict["ruling"]
    # The ceiling is set by the ergonomic void, not by the pickup: without this
    # the next reader will assume there is more room to buy.
    assert any("bass-side ergonomic void" in s for s in conflict["sources"])
    assert "does NOT resolve CONF-SINGLE-PICKUP-EMC" in conflict["ruling"]


def test_relocated_pockets_still_pack_against_every_keepout():
    """Re-derive the ruled placement rather than trusting the prose.

    The placement lives in a conflict ruling, which no validator recomputes, so
    this is the only thing standing between a typo and a body that cannot be
    cut.
    """
    # Loaded by path, not imported: scripts/ is not a package, and an
    # importorskip here would turn a broken solver into a silent skip.
    solver = load_module_by_path(ROOT / "scripts" / "solve_khaya_pocket_layout.py")
    outline, voids, features = solver.load_body()
    usable = outline.buffer(-solver.RIM_MIN)
    route = solver.rect(0.0, 294.6, 80.0, 22.0)
    placement = {
        "POD_PI": (11.910, 180.0),
        "POD_HAT": (94.410, 280.0),
        "BATTERY_CHAMBER": (2.910, 247.5),
    }
    boxes = {
        name: solver.rect(x, y, *solver.POCKETS[name]) for name, (x, y) in placement.items()
    }
    for name, box in boxes.items():
        assert usable.contains(box), f"{name} breaks the rim minimum"
        assert box.distance(route) >= solver.MIN_WEB, f"{name} crowds the pickup route"
        for index, void in enumerate(voids):
            assert box.distance(void) >= solver.MIN_WEB, f"{name} crowds void {index}"
        for layer, feature in features:
            assert box.distance(feature) >= solver.MIN_WEB, f"{name} crowds {layer}"
    for name, other in ((a, b) for a in boxes for b in boxes if a < b):
        assert boxes[name].distance(boxes[other]) >= solver.MIN_WEB

    assert boxes["POD_PI"].distance(route) == pytest.approx(71.6, abs=0.1)
    assert boxes["POD_PI"].distance(boxes["POD_HAT"]) == pytest.approx(35.75, abs=0.1)

    # The constraint that matters is how far the RIBBON travels, not how far
    # apart the pockets are. Ruling the first relocation on edge clearance
    # produced a layout needing 118.8 mm of a 100 mm part.
    span = solver._header_span(boxes["POD_PI"], boxes["POD_HAT"])
    assert span == pytest.approx(89.9, abs=0.1)
    assert span <= solver.RIBBON_LENGTH * 0.9, "less than 10% ribbon slack"


def test_length_datum_is_resolved_and_preserves_cavity_positions():
    """The extra 24 mm sits at the tail, so every y_from_top survives.

    This was the binding constraint on plan-level work: growth at the neck end
    would have shifted every cavity by 24 mm, roughly twice the rim minimum.
    """
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-LENGTH-DATUM"
    )
    assert conflict["status"] == "ruled"
    assert "TAIL" in conflict["ruling"]
    assert "preserved" in conflict["ruling"]
    assert "owner ruling" in conflict["ruled_by"]


def test_body_width_is_independently_corroborated():
    """402.85 mm is confirmed by a second, separate derivation.

    The CAD declares no width, so a figure resting only on the traced aspect
    would be thin evidence. An independent calculation reaching the same
    number is what makes it governed rather than provisional.
    """
    width = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-BODY-WIDTH"
    )
    assert width["status"] == "ruled"
    assert "468.5" in width["ruling"]
    assert "402.85" in width["ruling"]
    assert "CORROBORATED INDEPENDENTLY" in width["ruled_by"]


def test_registration_is_diagnosed_as_a_constant_datum_offset():
    """The outline and the spec positions are compatible after all.

    Six of eight cavity layers in front_v5 imply one body-top datum; the file's
    own outline sits 109 mm away. That is a generator bug, not incompatible
    data, and it means (body_top_y - y_from_top) is the correct registration.
    """
    conflicts = {c["conflict_id"]: c for c in load_json(GEOMETRY)["conflicts"]}
    reg = conflicts["CONF-TRACE-REGISTRATION"]

    assert reg["status"] == "ruled"
    assert "CONSTANT DATUM OFFSET" in reg["ruling"]
    assert "109.0 mm" in reg["ruling"]
    assert "(body_top_y - y_from_top)" in reg["ruling"]
    # It must not be read as impugning the silhouette, which the width rests on.
    assert conflicts["CONF-BODY-WIDTH"]["status"] == "ruled"


def test_registration_records_the_two_positions_still_suspect():
    """Removing the offset does not rescue neck pocket or control plate."""
    reg = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-TRACE-REGISTRATION"
    )
    assert "NECK_POCKET and CONTROL_PLATE remain outliers" in reg["ruling"]
    assert "two cavity positions remain suspect" in reg["ruled_by"]


def test_body_width_is_corroborated_by_three_artifacts():
    """One derivation is a guess; three agreeing artifacts is a measurement."""
    width = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-BODY-WIDTH"
    )
    assert "back_v5" in " ".join(width["sources"])
    assert "0.8599" in " ".join(width["sources"])
    assert "Three artifacts now agree" in width["ruled_by"]


def test_body_dimensions_are_not_consumed_by_any_derivation():
    """Only thickness feeds the derivation, so the width dispute is inert here.

    This is why CONF-BODY-WIDTH and CONF-LENGTH-DATUM can sit unresolved
    without invalidating a single derived cavity dimension.
    """
    register = _register()
    assert register.body.stated_thickness_mm == BODY_THICKNESS_MM

    stored = load_json(GEOMETRY)
    # No length or width of the BODY appears anywhere in the derived record.
    assert set(stored["body"]) == {
        "stated_thickness_mm",
        "required_thickness_mm",
        "governing_cavity_id",
        "margin_mm",
        "verdict",
    }
    # Changing the blank thickness must move the verdict; nothing else can.
    thinner = derive_cavity_geometry(
        replace(register, body=replace(register.body, stated_thickness_mm=38.0)),
        register_ref="x",
        effective_date="2026-07-26",
    )
    assert thinner.body.verdict == VERDICT_INSUFFICIENT


def test_pickups_are_recorded_as_conflicts_but_not_modelled():
    """Pickups are out of scope here; the record must not imply otherwise.

    The register covers embedded-electronics cavities only. Both pickup
    disagreements are logged, and no pickup dimension is derived or fit-checked
    anywhere, so nothing downstream can mistake silence for agreement.
    """
    stored = load_json(GEOMETRY)
    conflicts = {c["conflict_id"]: c for c in stored["conflicts"]}

    assert conflicts["CONF-PICKUP-TYPE"]["status"] == "unresolved"
    assert conflicts["CONF-PICKUP-ROUTE-DIMS"]["status"] == "unresolved"

    # No pickup is modelled as a component or a cavity.
    placed = {cid for c in stored["cavities"] for cid in c["component_ids"]}
    assert not any("PICKUP" in cid for cid in placed)
    assert not any("PICKUP" in c["cavity_id"] for c in stored["cavities"])

    notes = " ".join(stored["notes"]).lower()
    assert "pickup routes" in notes and "not modelled" in notes


def test_pickup_type_conflict_is_intra_file_not_cross_repo():
    """P90 appears only in luthiers-toolbox; sg-spec has no P90 reference.

    Guards a real misattribution: the conflict was first filed as sg-spec
    versus luthiers-toolbox, which would send a reader to the wrong repo.
    """
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-PICKUP-TYPE"
    )
    assert all("luthiers-toolbox" in s for s in conflict["sources"])
    assert not any("sg-spec" in s for s in conflict["sources"])
    assert "INTRA-FILE" in conflict["ruling"]
    # P-90 and humbucker are different pickup CLASSES, not two models.
    assert "a P-90 is a SINGLE COIL" in conflict["ruling"]


def test_pod_relocation_removes_the_opposed_face_constraint():
    """Plan separation does not satisfy the web check — it removes it.

    The pod sits in the tail below the bridge, clear of every top-face route,
    so there is no opposing pair to measure. Guarded because a future edit
    that nudges the pod back under a pickup would silently reintroduce a
    -5.0 mm intersection that no derived field in this record would show.
    """
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-OPPOSED-FACE-WEB"
    )
    assert conflict["status"] == "ruled"
    assert "centre x 74.0, y_from_top 387.0" in conflict["ruling"]
    assert "clears every top-face route" in conflict["ruling"]
    assert "owner instruction" in conflict["ruled_by"]


def test_pod_split_is_recorded_with_why_it_was_forced():
    """A ruling without its reason is a note, and notes rot."""
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"] if c["conflict_id"] == "CONF-POD-SPLIT"
    )
    assert conflict["status"] == "ruled"
    assert "NO valid position" in " ".join(conflict["sources"])
    assert "1.381x" in " ".join(conflict["sources"])
    assert "GPIO_RIBBON" in conflict["ruling"]


def test_cavity_datum_offset_is_recorded_as_a_fit_not_a_measurement():
    """dx -15, dy -50 takes four non-negotiable features from failing to passing.

    It must stay flagged as derived: it shifts every cavity in the instrument,
    so it needs confirming against the drawing rather than inheriting trust
    from having worked once.
    """
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-CAVITY-DATUM"
    )
    assert conflict["status"] == "ruled"
    assert "dx -15.0 dy -50.0" in conflict["ruling"]
    assert "ENGINEERING FIT, not a measured datum" in conflict["ruling"]
    assert "confirm against the CAD drawing" in conflict["ruled_by"]


def test_x_sign_convention_is_ruled_treble_positive():
    """+X is treble; the spec's 'bass side' annotation is wrong.

    This decided which half of the instrument the pod is cut into, so the
    ruling and its corroboration are pinned rather than left to memory.
    """
    conflict = next(
        c for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-X-SIGN-CONVENTION"
    )
    assert conflict["status"] == "ruled"
    assert "+X IS TREBLE" in conflict["ruling"]
    assert "spec annotation is wrong" in conflict["ruling"]
    # Corroboration matters more than the ruling: bass voids sit at negative x.
    assert "V1 (upper_bass) and V5 (bass_lower)" in conflict["ruling"]
    assert "no asymmetric feature needs mirroring" in conflict["ruling"]
    assert "owner ruling" in conflict["ruled_by"]


def test_ruled_conflicts_name_who_ruled_them():
    stored = load_json(GEOMETRY)
    for conflict in stored["conflicts"]:
        if conflict["status"] == "ruled":
            assert conflict["ruled_by"] != "", conflict["conflict_id"]
            assert "unresolved" not in conflict["ruled_by"]


def test_no_cost_or_time_fields_in_a_physical_record():
    forbidden = {
        "cost", "unit_cost", "price", "margin", "markup",
        "labor_minutes", "machine_minutes", "runtime_minutes", "hourly_rate",
    }

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in forbidden, key
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(load_json(REGISTER))
    scan(load_json(GEOMETRY))


def test_register_stays_draft():
    register_raw = load_json(REGISTER)
    assert register_raw["status"] == "draft"
    assert register_raw["provenance"]["confidence"] == "draft"


def test_register_records_that_the_source_scan_was_bounded():
    """The scan cannot be exhaustive, and the record must say so."""
    notes = " ".join(load_json(REGISTER)["notes"]).lower()
    assert "bounded" in notes
    assert "not exhaustive" in notes


def test_validator_script_passes():
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_doc_records_the_ruling_and_the_open_items():
    text = DOC.read_text(encoding="utf-8")
    for marker in ("side-by-side", "CONF-FAN-INTRUSION", "162", "33.0", "not exhaustive"):
        assert marker in text, marker


def test_as_mm_rounds_to_two_places():
    assert as_mm(30.4799999) == 30.48
    assert mm_equal(30.4799999, 30.48)


def test_cad_dimension_sheet_is_not_stale():
    """The sheet says it is generated. It has to actually be.

    The version this replaced carried that claim in its header while being
    hand-written, and by the time anyone checked it held a 162 mm one-piece pod
    from before the split, a Teensy pocket for a part no longer in the design,
    and a superseded position. Regenerating and comparing is the only thing
    that keeps the claim honest.
    """
    exporter = load_module_by_path(ROOT / "scripts" / "export_cad_dimensions.py")
    written = (ROOT / "docs" / "geometry" / "SMART_GUITAR_CAD_DIMENSIONS.md").read_text(
        encoding="utf-8"
    )
    assert written == exporter.render(), (
        "SMART_GUITAR_CAD_DIMENSIONS.md is stale — "
        "run scripts/export_cad_dimensions.py"
    )


def test_battery_placement_is_forced_not_chosen():
    """The pack sits 8.60 mm from the coil because nowhere else is legal.

    Read cold, that number looks like carelessness — the pack was fitted last,
    wherever it fit. It is worth pinning that with the Pi and board where they
    are ruled, the search has exactly one battery site, so the figure is
    forced. If a future change opens a second site, this fails and the ruling
    in CONF-BATTERY-AGGRESSOR has to be revisited rather than assumed.
    """
    solver = load_module_by_path(ROOT / "scripts" / "solve_khaya_pocket_layout.py")
    outline, voids, features = solver.load_body()
    usable = outline.buffer(-solver.RIM_MIN)
    keepout = [v.buffer(solver.MIN_WEB) for v in voids]
    keepout += [p.buffer(solver.MIN_WEB) for _, p in features]
    route = solver.rect(0.0, 294.6, 80.0, 22.0)
    route_keepout = route.buffer(solver.MIN_WEB)
    pi = solver.rect(11.910, 180.0, *solver.POCKETS["POD_PI"])
    hat = solver.rect(94.410, 280.0, *solver.POCKETS["POD_HAT"])

    width, height = solver.POCKETS["BATTERY_CHAMBER"]
    minx, _, maxx, _ = usable.bounds
    legal = []
    x = minx + width / 2
    while x <= maxx - width / 2:
        y = solver.Y_MIN
        while y <= solver.Y_MAX:
            box = solver.rect(x, y, width, height)
            if (
                usable.contains(box)
                and not any(box.intersects(k) for k in keepout)
                and not box.intersects(route_keepout)
                and box.distance(pi) >= solver.MIN_WEB
                and box.distance(hat) >= solver.MIN_WEB
            ):
                legal.append((x, y, box.distance(route)))
            y += 2.5
        x += 2.5

    assert len(legal) == 1, f"battery now has {len(legal)} legal sites, not 1"
    x, y, coil_gap = legal[0]
    assert (round(x, 3), y) == (2.910, 247.5)
    assert coil_gap == pytest.approx(8.60, abs=0.01)


def test_battery_aggressor_ruling_records_the_binary_choice():
    """Not a continuum: one pocket gets the space the neck pickup vacated."""
    conflict = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-BATTERY-AGGRESSOR"
    )
    assert conflict["status"] == "ruled"
    assert "NO CHANGE TO THE LAYOUT" in conflict["ruling"]
    assert "BINARY, NOT A CONTINUUM" in conflict["ruling"]
    # The mitigation is local, not geometric — that is the whole point.
    assert "MITIGATED LOCALLY" in conflict["ruling"]
    assert any("EXACTLY ONE legal site" in s for s in conflict["sources"])
    # The ruling asserts the pack is weak without having measured it, and must
    # say so plus point at the configurations that could falsify it.
    assert "ENGINEERING JUDGEMENT STANDING IN FOR A MEASUREMENT" in conflict["ruling"]
    assert "configurations G to I" in conflict["ruling"]


def test_emc_procedure_covers_the_charging_configurations():
    """The pack is 8.6 mm from the coil; charging is when it misbehaves."""
    procedure = (
        ROOT / "docs" / "geometry" / "SG_PICKUP_EMC_MOCKUP_PROCEDURE.md"
    ).read_text(encoding="utf-8")
    for marker in ("| **G** |", "| **H** |", "| **I** |"):
        assert marker in procedure, f"configuration {marker} missing"
    assert "8.60 mm" in procedure
    # Near-full taper is the counterintuitive case and must not be dropped.
    assert "Do not skip H for G" in procedure
    assert "pulse-skipping or burst mode" in procedure
    # Charging failures are a product decision, not an audio-board defect.
    assert "REQ-NOISE-BOUNDARY" in procedure


def test_void_set_is_ruled_from_the_renders_not_the_trace():
    """The trace is stale, and believing it produced a false blocking finding.

    It plots four through-body voids. The design has three, and what the trace
    shows as a fourth on the lower treble side is the electronics cavity —
    visible in the owner's back render as a screwed cover plate. Treating that
    as a hole is what produced "no pocket fits anywhere".
    """
    conflict = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-VOID-SET-SOURCE"
    )
    assert conflict["status"] == "ruled"
    assert "The traced outline is STALE" in conflict["ruling"]
    assert "ELECTRONICS CAVITY" in conflict["ruling"]
    # The reversal must be explicit, not implied by a status flip.
    assert "THE EARLIER FINDING IS WITHDRAWN" in conflict["ruling"]
    assert "ALSO WITHDRAWN" in conflict["ruling"]


def test_body_cannot_host_conflict_is_withdrawn_not_quietly_flipped():
    """It asserted the body and the electronics could not both exist.

    The premise was false three ways: a stale void set, a per-pocket wall
    requirement that does not apply inside a hollow box, and the control cavity
    treated as a keep-out rather than part of the same hollow. Correcting the
    last of those alone took POD_PI from 0 placements to 224. A withdrawn
    finding has to say it was withdrawn, or the next reader inherits it.
    """
    conflict = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-BODY-CANNOT-HOST-ELECTRONICS"
    )
    assert conflict["status"] == "ruled"
    assert conflict["ruling"].startswith("WITHDRAWN - THE PREMISE WAS FALSE")
    assert "0 valid placements to 224" in conflict["ruling"]
    # What replaces it is a different KIND of question.
    assert "STRUCTURAL, NOT SPATIAL" in conflict["ruling"]


def test_dimension_sheet_separates_what_can_be_cut_from_what_cannot():
    """The sheet is read by someone starting CAD on an unfinished design.

    Grouping by confidence is the whole contract: a figure that is ruled and a
    figure that was solved against a stale outline must not sit in the same
    table looking alike.
    """
    sheet = (ROOT / "docs" / "geometry" / "SMART_GUITAR_CAD_DIMENSIONS.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "## 1. Fixed — cut geometry from these",
        "## 2. Parametric — right today, derived from a part",
        "## 3. Not established — cannot be drawn yet",
    ):
        assert heading in sheet, f"missing {heading!r}"

    fixed = sheet.split("## 2.")[0]
    for value in ("468.5", "402.85", "47.0", "628.65"):
        assert value in fixed, f"{value} missing from the fixed section"

    # Withdrawn placements must not reappear anywhere, in any section.
    for coord in ("11.910", "94.410", "2.910", "71.6", "35.75", "89.9"):
        assert coord not in sheet, f"withdrawn figure {coord} is back in the sheet"

    # The outline itself is not established, and that has to be stated plainly
    # rather than left for the reader to infer from a missing table.
    open_section = sheet.split("## 3.")[1]
    assert "Body outline curve" in open_section
    assert "Every cavity position" in open_section
    assert "tremolo" in open_section, "the fixed-vs-trem contradiction must be flagged"


def test_dimension_sheet_gives_an_order_that_stops_where_the_data_stops():
    """Telling someone where to STOP is the useful part."""
    sheet = (ROOT / "docs" / "geometry" / "SMART_GUITAR_CAD_DIMENSIONS.md").read_text(
        encoding="utf-8"
    )
    assert "## 4. Suggested modelling order" in sheet
    assert "Stop." in sheet
    # The bridge block is the only positionable feature, because the scale
    # length is settled and everything else depends on the outline.
    assert "positioned from the scale length" in sheet

