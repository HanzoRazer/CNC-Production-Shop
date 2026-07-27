"""Tests for SMART-GUITAR-CAVITY-GEOMETRY-1.

Covers the derivation rules, the fit verdicts, the body-thickness derivation,
conflict propagation, and the governance boundary that keeps cost and time out
of a physical record.

The central regression these tests protect is the one that motivated the Dev
Order: a cavity dimension must never be readable as an input, so a stale note
in a source spec cannot propagate into anything downstream.
"""

from __future__ import annotations

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

BODY_THICKNESS_MM = 51.0


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

    assert result.floor_remaining_mm == 6.0
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
    assert body.margin_mm == 13.0
    assert body.verdict == VERDICT_SUFFICIENT


def test_insufficient_blank_is_reported_with_negative_margin():
    registry = {"DEEP": _component("DEEP", 10, 10, 50)}
    derivations = [derive_cavity(_plan("B", ("DEEP",), "single"), registry, BODY_THICKNESS_MM)]
    body = derive_required_body_thickness(derivations, BODY_THICKNESS_MM)

    assert body.required_thickness_mm == 58.0
    assert body.margin_mm == -7.0
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
    plans = [p for p in register.cavity_plans if p.cavity_id != "TEENSY_IO_POCKET"]
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


def test_pod_is_side_by_side_and_fits_the_specified_blank():
    """The ruling, and the number that makes it work."""
    stored = load_json(GEOMETRY)
    pod = next(c for c in stored["cavities"] if c["cavity_id"] == "ELECTRONICS_POD")

    assert pod["layout"] == "side_by_side"
    assert pod["derived_depth_mm"] == 33.0
    assert pod["derived_length_mm"] == 162.0
    assert pod["derived_width_mm"] == 64.0
    assert pod["fit_ok"] is True
    assert stored["body"]["verdict"] == VERDICT_SUFFICIENT
    assert stored["body"]["governing_cavity_id"] == "ELECTRONICS_POD"
    assert stored["body"]["margin_mm"] == 10.0


def test_sg_spec_stated_pod_depth_is_too_shallow_for_its_own_contents():
    """Guards the finding: 30.48 mm stated against 33.0 mm derived."""
    stored = load_json(GEOMETRY)
    pod = next(c for c in stored["cavities"] if c["cavity_id"] == "ELECTRONICS_POD")
    assert pod["stated_depth_mm"] == 30.48
    assert pod["depth_delta_mm"] == -2.52
    assert any("cannot hold its own contents" in f for f in pod["findings"])


def test_teensy_pocket_footprint_reproduces_the_stated_pocket():
    """Back-derived anisotropic margins must reproduce 70 x 25 exactly."""
    stored = load_json(GEOMETRY)
    pocket = next(c for c in stored["cavities"] if c["cavity_id"] == "TEENSY_IO_POCKET")
    assert pocket["derived_length_mm"] == pocket["stated_length_mm"] == 70.0
    assert pocket["derived_width_mm"] == pocket["stated_width_mm"] == 25.0
    assert pocket["length_delta_mm"] == 0.0
    assert pocket["width_delta_mm"] == 0.0


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
    assert stored["body"]["margin_mm"] == 10.0


def test_internal_fan_is_exactly_viable_at_the_enlarged_blank():
    """The enlargement changed this counterfactual's answer.

    At the original 44.45 mm blank an internally mounted fan failed by
    6.55 mm. At the ruled 51.0 mm it lands exactly on the requirement with
    zero margin — viable, but with nothing in hand. Kept because a later edit
    flipping the mounting would otherwise pass silently, and because zero
    margin is worth seeing rather than discovering.
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
    assert result.body.required_thickness_mm == 51.0
    assert result.body.verdict == VERDICT_SUFFICIENT
    assert result.body.margin_mm == 0.0
    pod = next(c for c in result.cavities if c.cavity_id == "ELECTRONICS_POD")
    assert pod.fit_ok is True
    assert pod.derived_depth_mm == 43.0
    assert pod.floor_remaining_mm == 8.0


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
        "CONF-HIZ-SPLITTER-DIMS",
        "CONF-USB-INTERFACE-LOCATION",
        "CONF-PICKUP-TYPE",
        "CONF-PICKUP-ROUTE-DIMS",
        "CONF-OPPOSED-FACE-WEB",
        "CONF-TRACE-REGISTRATION",
    } <= unresolved


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


def test_registration_finding_is_scoped_to_void_positions_only():
    """The void-position failure must not be read as impugning the aspect.

    These are separable claims: a render can place voids decoratively while
    the silhouette it was traced from stays proportionally faithful. Conflating
    them would discard a corroborated width for no reason.
    """
    conflicts = {c["conflict_id"]: c for c in load_json(GEOMETRY)["conflicts"]}
    reg = conflicts["CONF-TRACE-REGISTRATION"]

    assert reg["status"] == "unresolved"
    assert "VOID POSITIONS only" in reg["ruling"]
    assert "does NOT impugn" in reg["ruling"]
    assert "0.5707" in reg["sources"][0]

    # The width ruling must survive it, and say so.
    assert conflicts["CONF-BODY-WIDTH"]["status"] == "ruled"
    assert "separable" in conflicts["CONF-BODY-WIDTH"]["ruled_by"]


def test_registration_finding_states_its_mitigation():
    """An unverifiable frame is a residual risk only if the trace is used narrowly."""
    reg = next(
        c
        for c in load_json(GEOMETRY)["conflicts"]
        if c["conflict_id"] == "CONF-TRACE-REGISTRATION"
    )
    assert "V1, V2, V3, V5 only" in reg["ruling"]
    assert "Never read a cavity position out of the trace" in reg["ruling"]
    assert "residual risk, not a blocker" in reg["ruled_by"]


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


def test_opposed_face_web_is_quantified_and_fails():
    """With min_web ruled at 8.0 mm the check can be evaluated, and it fails.

    Arithmetic guarded here because the register cannot compute it — this is a
    plan-level result — but the numbers must not drift from the cavity depths
    this record does derive. If the pod depth changes, this test is where the
    stale conclusion surfaces.
    """
    stored = load_json(GEOMETRY)
    pod = next(c for c in stored["cavities"] if c["cavity_id"] == "ELECTRONICS_POD")

    thickness = stored["body"]["stated_thickness_mm"]
    bridge_route_depth = 19.0
    min_web = 8.0
    web = thickness - bridge_route_depth - pod["derived_depth_mm"]

    assert web == pytest.approx(-1.0)
    assert web < min_web
    assert web < 0, "negative web means the cavities intersect, not merely crowd"
    assert min_web - web == pytest.approx(9.0)

    # The enlargement narrowed the gap but did not close it.
    assert bridge_route_depth + pod["derived_depth_mm"] + min_web == pytest.approx(60.0)
    assert thickness - bridge_route_depth - min_web == pytest.approx(24.0)

    conflict = next(
        c for c in stored["conflicts"] if c["conflict_id"] == "CONF-OPPOSED-FACE-WEB"
    )
    assert "still fails after the thickness enlargement" in conflict["ruling"]
    assert "-1.0" in conflict["ruling"]
    assert "ROBUST TO ORIENTATION" in conflict["ruling"]
    assert "min_web ruled 8.0" in conflict["ruled_by"]


def test_opposed_face_web_stays_open_as_a_placement_decision():
    """Quantified but not resolved: choosing a placement is design, not derivation.

    The failure is now arithmetic rather than suspicion, but this register
    still cannot close it — plan position is out of scope, and the fix is a
    design choice about where the pod sits.
    """
    stored = load_json(GEOMETRY)
    conflict = next(
        c for c in stored["conflicts"] if c["conflict_id"] == "CONF-OPPOSED-FACE-WEB"
    )
    assert conflict["status"] == "unresolved"
    assert "Plan separation is the only viable fix" in conflict["ruling"]
    assert "SMART-GUITAR-PLAN-COLLISION-1" in conflict["ruled_by"]

    # The viable direction must be recorded, not just the failure.
    assert "148.5 mm of tail" in conflict["ruling"]
    # And that the enlargement fixed the spec-native failures but not this one.
    assert "NOT POD-SPECIFIC" in conflict["ruling"]

    pod = next(c for c in stored["cavities"] if c["cavity_id"] == "ELECTRONICS_POD")
    assert pod["derived_depth_mm"] + 19.0 > stored["body"]["stated_thickness_mm"]

    notes = " ".join(stored["notes"]).lower()
    assert "lower bound" in notes


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
