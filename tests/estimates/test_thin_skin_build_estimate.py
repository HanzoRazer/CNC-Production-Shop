"""Tests for THIN-SKIN-GUITAR-BUILD-ESTIMATE-1.

Covers the V2 time model, the eighteen-category rollup, equipment occupancy
costing, the two non-compounding risk mechanisms, WBS coverage, variant
comparability, provenance boundaries, and non-regression of the V1 solid-body
records that this sprint deliberately leaves intact.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import jsonschema
import pytest

from business.calculators.equipment_cost_basis import (
    assemble_equipment_hour_rate,
    derive_equipment_electricity_cost_per_hour,
    derive_equipment_occupancy_cost,
)
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.equipment_costing import build_equipment_occupancy_costing
from business.estimates.guitar_v2 import (
    calculate_category_cost,
    calculate_labor_cost,
    calculate_material_scrap_allowance,
    calculate_thin_skin_build_estimate,
    operation_machine_minutes,
    operation_occupancy_minutes,
)
from business.estimates.loading_v2 import load_thin_skin_estimate_input
from business.estimates.models_v2 import (
    EstimateProvenanceV2,
    MaterialInputV2,
    OperationTimeModelV2,
    PurchasedComponentInputV2,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
PRODUCT_SCHEMA = SCHEMAS / "products" / "thin_skin_guitar_product_definition_v1.schema.json"
INPUT_SCHEMA = SCHEMAS / "estimates" / "thin_skin_estimate_input_v2.schema.json"
ESTIMATE_SCHEMA = SCHEMAS / "estimates" / "thin_skin_build_estimate_v2.schema.json"
EQUIPMENT_PROFILE_SCHEMA = SCHEMAS / "equipment" / "equipment_profile_v1.schema.json"
EQUIPMENT_BASIS_SCHEMA = SCHEMAS / "equipment" / "equipment_cost_basis_v1.schema.json"

PRODUCT = ROOT / "fixtures" / "products" / "thin_skin_electric_guitar_baseline_v1.json"
ESTIMATES_DIR = ROOT / "fixtures" / "estimates" / "guitar"
EQUIPMENT_DIR = ROOT / "fixtures" / "equipment"
EQUIPMENT_BASIS_DIR = EQUIPMENT_DIR / "cost_basis"
VALIDATE = ROOT / "scripts" / "validate_thin_skin_estimates.py"
V1_VALIDATE = ROOT / "scripts" / "validate_guitar_estimates.py"
DOC = ROOT / "docs" / "estimates" / "THIN_SKIN_GUITAR_BUILD_ESTIMATE_V1.md"

VARIANTS = [
    ("thin_skin_variant_a_input_v1.json", "thin_skin_variant_a_estimate_v1.json"),
    ("thin_skin_variant_b_input_v1.json", "thin_skin_variant_b_estimate_v1.json"),
]

# The governed work breakdown. Every leaf must carry exactly one operation.
EXPECTED_WBS = [
    "1100", "1200", "1300",
    "2100", "2200", "2300", "2400", "2500",
    "3100", "3200", "3300", "3400", "3500", "3600",
    "4100", "4200", "4300", "4400",
    "5100", "5200", "5300", "5400", "5500", "5600",
    "6100", "6200", "6300", "6400",
    "7100", "7200", "7300",
    "8100", "8200", "8300", "8400", "8500",
    "9100", "9200", "9300",
]

GOVERNED_MACHINE_HOUR_RATE = 28.97
GOVERNED_LOADED_LABOR_RATE = 28.75
# Rates that belong to later commercial layers and must never appear here.
FORBIDDEN_RATES = {72.0, 45.0, 75.0}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _domain(input_name: str):
    return load_thin_skin_estimate_input(ESTIMATES_DIR / input_name)


def _recompute(input_name: str, estimate_name: str):
    estimate = load_json(ESTIMATES_DIR / estimate_name)
    return estimate, calculate_thin_skin_build_estimate(
        _domain(input_name),
        estimate_id=estimate["estimate_id"],
        estimate_input_ref=estimate["estimate_input_ref"],
        effective_date=estimate["calculation"]["effective_date"],
        repo_root=ROOT,
    )


def _prov(confidence: str = "draft") -> EstimateProvenanceV2:
    return EstimateProvenanceV2(source="engineering_estimate", confidence=confidence)


# --------------------------------------------------------------------------
# Time model: the separation that motivates V2
# --------------------------------------------------------------------------


def test_labor_minutes_exclude_occupancy_and_wait():
    """Press occupancy, CNC runtime, and cure time are never labor."""
    tm = OperationTimeModelV2(
        setup_minutes=4,
        operator_touch_minutes=16,
        machine_runtime_minutes=120,
        equipment_occupancy_minutes=90,
        elapsed_wait_minutes=2880,
        rework_minutes=5,
    )
    assert tm.labor_minutes == 25


def test_cure_operation_has_occupancy_but_zero_labor():
    """The 2400 cure leaf is the canonical occupancy-without-labor case."""
    ops = {o.wbs_code: o for o in _domain(VARIANTS[0][0]).operations}
    cure = ops["2400"]
    assert cure.time_model.labor_minutes == 0
    assert cure.time_model.equipment_occupancy_minutes == 90
    assert cure.attendance == "queue_or_cure"
    assert cure.equipment_id == "EQUIPMENT-VACUUM-PRESS-V1"


def test_cnc_runtime_exceeds_attended_labor_on_machining_leaves():
    """Partially-attended CNC leaves must not book runtime as touch labor."""
    ops = {o.wbs_code: o for o in _domain(VARIANTS[0][0]).operations}
    for code in ("3200", "3300", "4100"):
        op = ops[code]
        assert op.attendance == "partially_attended"
        assert op.time_model.machine_runtime_minutes > op.time_model.labor_minutes


def test_negative_time_fields_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        OperationTimeModelV2(operator_touch_minutes=-1)


def test_machine_and_occupancy_minutes_scale_with_quantity():
    ops = {o.wbs_code: o for o in _domain(VARIANTS[0][0]).operations}
    assert operation_machine_minutes(ops["3200"], 3) == 27
    assert operation_occupancy_minutes(ops["2400"], 3) == 270
    # A non-machine leaf contributes no machine minutes regardless of quantity.
    assert operation_machine_minutes(ops["4200"], 5) == 0
    assert operation_occupancy_minutes(ops["4200"], 5) == 0


# --------------------------------------------------------------------------
# Category rollup
# --------------------------------------------------------------------------


def test_category_cost_spans_both_input_lists():
    """A category draws from materials and components alike."""
    materials = (
        MaterialInputV2("MAT-A", "blank", "neck_fretboard", 1, "each", 26.0, _prov()),
    )
    components = (
        PurchasedComponentInputV2("CMP-A", "rod", "neck_fretboard", 1, "each", 12.5, _prov()),
        PurchasedComponentInputV2("CMP-B", "bridge", "hardware", 1, "each", 22.0, _prov()),
    )
    assert calculate_category_cost(materials, components, "neck_fretboard") == 38.5
    assert calculate_category_cost(materials, components, "hardware") == 22.0


def test_unknown_category_rejected():
    with pytest.raises(ValueError, match="unsupported input category"):
        calculate_category_cost((), (), "body_wood")


def test_labor_cost_conversion():
    assert calculate_labor_cost(60, GOVERNED_LOADED_LABOR_RATE) == 28.75
    assert calculate_labor_cost(0, GOVERNED_LOADED_LABOR_RATE) == 0.0


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_total_equals_sum_of_seventeen_categories(input_name, estimate_name):
    estimate, _ = _recompute(input_name, estimate_name)
    summary = estimate["cost_summary"]
    parts = sum(
        v for k, v in summary.items() if k != "total_direct_manufacturing_cost"
    )
    assert money_equal(summary["total_direct_manufacturing_cost"], as_money(parts))


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_lamination_and_finishing_are_not_buried_in_generic_labor(
    input_name, estimate_name
):
    """The categories the revision exists to expose must be non-zero and distinct."""
    estimate, _ = _recompute(input_name, estimate_name)
    summary = estimate["cost_summary"]
    assert summary["lamination_labor_cost"] > 0
    assert summary["finishing_labor_cost"] > 0
    assert summary["equipment_occupancy_cost"] > 0
    assert summary["adhesive_and_lamination_consumables"] > 0
    assert summary["skin_material_cost"] > 0
    # Machine time is CNC only and must not absorb equipment occupancy.
    assert money_equal(
        summary["machine_time_cost"],
        estimate["machine_costing"]["derived_machine_time_cost"],
    )


# --------------------------------------------------------------------------
# Equipment occupancy costing
# --------------------------------------------------------------------------


def test_equipment_hour_rate_assembly():
    rate = assemble_equipment_hour_rate(0.75, 0.03, 0.60)
    assert rate.equipment_hour_rate == 1.38


def test_equipment_electricity_derivation():
    assert derive_equipment_electricity_cost_per_hour(2.2, 0.85, 0.12) == 0.22


@pytest.mark.parametrize("load_factor", [0.0, 1.5, -0.2])
def test_equipment_load_factor_range_enforced(load_factor):
    with pytest.raises(ValueError, match="load_factor"):
        derive_equipment_electricity_cost_per_hour(2.2, load_factor, 0.12)


def test_equipment_occupancy_cost_derivation():
    assert derive_equipment_occupancy_cost(4.22, 52) == 3.66
    assert derive_equipment_occupancy_cost(0.12, 2880) == 5.76


def test_equipment_electricity_rejects_negative_inputs():
    with pytest.raises(ValueError, match="connected_load_kw"):
        derive_equipment_electricity_cost_per_hour(-1.0, 0.5, 0.12)
    with pytest.raises(ValueError, match="price_per_kwh"):
        derive_equipment_electricity_cost_per_hour(2.2, 0.5, -0.12)


@pytest.mark.parametrize(
    "burden,electricity,consumables,expected",
    [
        (-1.0, 0.03, 0.60, "equipment_burden_rate_per_hour"),
        (0.75, -0.03, 0.60, "electricity_cost_per_hour"),
        (0.75, 0.03, -0.60, "consumables_cost_per_hour"),
    ],
)
def test_equipment_rate_assembly_rejects_negative_components(
    burden, electricity, consumables, expected
):
    with pytest.raises(ValueError, match=expected):
        assemble_equipment_hour_rate(burden, electricity, consumables)


@pytest.mark.parametrize(
    "rate,minutes,expected",
    [
        (-1.0, 10, "equipment_hour_rate"),
        (1.38, -10, "occupancy_minutes"),
        (True, 10, "equipment_hour_rate"),
        (1.38, True, "occupancy_minutes"),
    ],
)
def test_occupancy_cost_rejects_bad_inputs(rate, minutes, expected):
    with pytest.raises(ValueError, match=expected):
        derive_equipment_occupancy_cost(rate, minutes)


def test_equipment_costing_rejects_bad_equipment_id_and_minutes():
    profile = EQUIPMENT_DIR / "vacuum_press_v1.json"
    basis = EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json"
    with pytest.raises(ValueError, match="invalid equipment_id"):
        build_equipment_occupancy_costing(
            equipment_id="PRESS-1",
            occupancy_minutes=10,
            equipment_profile_path=profile,
            cost_basis_path=basis,
            repo_root=ROOT,
        )
    with pytest.raises(ValueError, match="occupancy_minutes"):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
            occupancy_minutes=-5,
            equipment_profile_path=profile,
            cost_basis_path=basis,
            repo_root=ROOT,
        )


def test_equipment_costing_rejects_missing_artifact():
    with pytest.raises(FileNotFoundError, match="not found"):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
            occupancy_minutes=10,
            equipment_profile_path=EQUIPMENT_DIR / "does_not_exist.json",
            cost_basis_path=EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json",
            repo_root=ROOT,
        )


def _write_basis(tmp_repo: Path, **overrides) -> tuple[Path, Path]:
    """Materialise a profile/basis pair inside a throwaway repo root."""
    profile = json.loads((EQUIPMENT_DIR / "vacuum_press_v1.json").read_text("utf-8"))
    basis = json.loads(
        (EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json").read_text("utf-8")
    )
    basis.update(overrides)
    profile_path = tmp_repo / "profile.json"
    basis_path = tmp_repo / "basis.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    basis_path.write_text(json.dumps(basis), encoding="utf-8")
    return profile_path, basis_path


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"cost_basis_id": "COST-BASIS-PRESS"}, "invalid cost_basis_id"),
        ({"equipment_hour_rate": None}, "missing equipment_hour_rate"),
        ({"equipment_hour_rate": -1.0}, "must be non-negative"),
        ({"status": "provisional"}, "invalid status"),
        ({"equipment_id": "EQUIPMENT-OTHER-V1"}, "cost basis equipment_id"),
    ],
)
def test_equipment_cost_basis_contract_violations(tmp_path, overrides, message):
    profile_path, basis_path = _write_basis(tmp_path, **overrides)
    with pytest.raises(ValueError, match=message):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
            occupancy_minutes=10,
            equipment_profile_path=profile_path,
            cost_basis_path=basis_path,
            repo_root=tmp_path,
        )


def test_equipment_costing_rejects_non_object_artifact(tmp_path):
    stray = tmp_path / "list.json"
    stray.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected JSON object"):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
            occupancy_minutes=10,
            equipment_profile_path=stray,
            cost_basis_path=stray,
            repo_root=tmp_path,
        )


def test_equipment_ref_cost_basis_id_mismatch_rejected():
    domain = _domain(VARIANTS[0][0])
    refs = list(domain.equipment_refs)
    refs[0] = replace(refs[0], cost_basis_id="EQUIPMENT-COST-BASIS-WRONG-V1")
    with pytest.raises(ValueError, match="equipment cost_basis_id mismatch"):
        calculate_thin_skin_build_estimate(
            replace(domain, equipment_refs=tuple(refs)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_equipment_cost_basis_rates_recompute_from_components():
    for path in sorted(EQUIPMENT_BASIS_DIR.glob("*.json")):
        basis = load_json(path)
        electricity = basis["electricity"]
        assert money_equal(
            electricity["electricity_cost_per_hour"],
            derive_equipment_electricity_cost_per_hour(
                electricity["connected_load_kw"],
                electricity["load_factor"],
                electricity["price_per_kwh"],
            ),
        )
        assembled = assemble_equipment_hour_rate(
            basis["equipment_burden_rate_per_hour"],
            electricity["electricity_cost_per_hour"],
            basis["consumables_cost_per_hour"],
        )
        assert money_equal(basis["equipment_hour_rate"], assembled.equipment_hour_rate)


def test_equipment_costing_rejects_mismatched_equipment_id():
    with pytest.raises(ValueError, match="does not match requested equipment_id"):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-SPRAY-BOOTH-V1",
            occupancy_minutes=10,
            equipment_profile_path=EQUIPMENT_DIR / "vacuum_press_v1.json",
            cost_basis_path=EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json",
            repo_root=ROOT,
        )


def test_equipment_costing_rejects_paths_outside_repo(tmp_path):
    stray = tmp_path / "stray.json"
    stray.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must be inside repository root"):
        build_equipment_occupancy_costing(
            equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
            occupancy_minutes=10,
            equipment_profile_path=stray,
            cost_basis_path=EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json",
            repo_root=ROOT,
        )


def test_equipment_costing_refs_are_repo_relative():
    record = build_equipment_occupancy_costing(
        equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
        occupancy_minutes=118,
        equipment_profile_path=EQUIPMENT_DIR / "vacuum_press_v1.json",
        cost_basis_path=EQUIPMENT_BASIS_DIR / "vacuum_press_cost_basis_v1.json",
        repo_root=ROOT,
    )
    assert record.equipment_profile_ref == "fixtures/equipment/vacuum_press_v1.json"
    assert not Path(record.cost_basis_ref).is_absolute()
    assert record.cost_basis_role == "internal_technical_cost"
    assert record.derived_occupancy_cost == 2.71


def test_zero_occupancy_yields_zero_cost_record():
    record = build_equipment_occupancy_costing(
        equipment_id="EQUIPMENT-CURE-RACK-V1",
        occupancy_minutes=0,
        equipment_profile_path=EQUIPMENT_DIR / "cure_rack_v1.json",
        cost_basis_path=EQUIPMENT_BASIS_DIR / "cure_rack_cost_basis_v1.json",
        repo_root=ROOT,
    )
    assert record.derived_occupancy_cost == 0.0


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_equipment_occupancy_totals_trace_to_records(input_name, estimate_name):
    estimate, _ = _recompute(input_name, estimate_name)
    total = as_money(
        sum(e["derived_occupancy_cost"] for e in estimate["equipment_costing"])
    )
    assert money_equal(estimate["cost_summary"]["equipment_occupancy_cost"], total)
    assert {e["equipment_id"] for e in estimate["equipment_costing"]} == {
        "EQUIPMENT-VACUUM-PRESS-V1",
        "EQUIPMENT-SPRAY-BOOTH-V1",
        "EQUIPMENT-CURE-RACK-V1",
    }


# --------------------------------------------------------------------------
# Risk mechanisms
# --------------------------------------------------------------------------


def test_scrap_applies_only_to_eligible_ids():
    materials = (
        MaterialInputV2("MAT-CORE", "core", "core_material", 1, "ea", 100.0, _prov()),
    )
    components = (
        PurchasedComponentInputV2("CMP-PU", "pickups", "electronics", 1, "set", 200.0, _prov()),
    )
    base, allowance = calculate_material_scrap_allowance(
        material_inputs=materials,
        purchased_component_inputs=components,
        eligible_input_ids=("MAT-CORE",),
        scrap_rate=0.05,
    )
    assert base == 100.0
    assert allowance == 5.0


def test_scrap_rejects_unknown_eligible_id():
    with pytest.raises(ValueError, match="not found"):
        calculate_material_scrap_allowance(
            material_inputs=(),
            purchased_component_inputs=(),
            eligible_input_ids=("MAT-GHOST",),
            scrap_rate=0.05,
        )


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_risk_mechanisms_do_not_compound(input_name, estimate_name):
    """The scrap allowance is never part of the reserve base."""
    estimate, _ = _recompute(input_name, estimate_name)
    risk = estimate["risk_basis"]
    summary = estimate["cost_summary"]

    assembled = as_money(
        risk["process_reserve_material_base"]
        + risk["process_reserve_machine_base"]
        + risk["process_reserve_equipment_base"]
        + risk["process_reserve_labor_base"]
    )
    assert money_equal(risk["process_reserve_base"], assembled)
    assert money_equal(
        summary["process_rework_and_yield_reserve"],
        as_money(risk["process_reserve_base"] * risk["process_reserve_rate"]),
    )
    # Removing the scrap allowance from the base changes nothing, which is only
    # true if it was never in the base.
    without_scrap = as_money(
        risk["process_reserve_base"] - summary["material_scrap_allowance"]
    )
    assert not money_equal(risk["process_reserve_base"], without_scrap)
    assert risk["compounding"].startswith("material_scrap_allowance is excluded")


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_high_value_components_excluded_from_both_risk_bases(input_name, estimate_name):
    """Pickups, bridge, tuners, and strings carry no scrap or reserve."""
    raw = load_json(ESTIMATES_DIR / input_name)
    excluded = {
        "CMP-PICKUP-SET",
        "CMP-BRIDGE",
        "CMP-TUNERS",
        "CMP-HARNESS",
        "CMP-STRINGS",
    }
    assert not excluded & set(raw["material_scrap_policy"]["eligible_input_ids"])
    assert not excluded & set(
        raw["process_yield_reserve_policy"]["eligible_input_ids"]
    )


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_reserve_labor_base_covers_only_body_process_labor(input_name, estimate_name):
    """Assembly and inspection labor are outside the reserve base."""
    raw = load_json(ESTIMATES_DIR / input_name)
    estimate, _ = _recompute(input_name, estimate_name)
    body_process = {"lamination_labor", "direct_build_labor", "finishing_labor"}
    for op in raw["operations"]:
        assert op["reserve_eligible"] is (op["labor_category"] in body_process)

    expected = as_money(
        sum(
            r["labor_cost"]
            for r in estimate["operation_results"]
            if r["labor_category"] in body_process
        )
    )
    assert money_equal(estimate["risk_basis"]["process_reserve_labor_base"], expected)


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_rework_minutes_are_zero_while_reserve_carries_the_risk(
    input_name, estimate_name
):
    """Guards the documented double-count rule."""
    estimate, _ = _recompute(input_name, estimate_name)
    raw = load_json(ESTIMATES_DIR / input_name)
    assert estimate["time_summary"]["total_rework_minutes"] == 0
    assert raw["process_yield_reserve_policy"]["reserve_rate"] == 0.10


def test_reserve_rate_out_of_range_rejected():
    domain = _domain(VARIANTS[0][0])
    bad = replace(
        domain,
        process_yield_reserve_policy=replace(
            domain.process_yield_reserve_policy, reserve_rate=1.4
        ),
    )
    with pytest.raises(ValueError, match="reserve_rate"):
        calculate_thin_skin_build_estimate(
            bad,
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


# --------------------------------------------------------------------------
# Structural validation
# --------------------------------------------------------------------------


def test_occupancy_without_equipment_id_rejected():
    domain = _domain(VARIANTS[0][0])
    ops = list(domain.operations)
    target = next(i for i, o in enumerate(ops) if o.wbs_code == "4200")
    ops[target] = replace(
        ops[target],
        time_model=replace(ops[target].time_model, equipment_occupancy_minutes=30),
    )
    with pytest.raises(ValueError, match="books equipment occupancy without"):
        calculate_thin_skin_build_estimate(
            replace(domain, operations=tuple(ops)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_machine_runtime_without_uses_machine_rejected():
    domain = _domain(VARIANTS[0][0])
    ops = list(domain.operations)
    target = next(i for i, o in enumerate(ops) if o.wbs_code == "4200")
    ops[target] = replace(
        ops[target],
        time_model=replace(ops[target].time_model, machine_runtime_minutes=12),
    )
    with pytest.raises(ValueError, match="books machine runtime without"):
        calculate_thin_skin_build_estimate(
            replace(domain, operations=tuple(ops)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_undeclared_equipment_reference_rejected():
    domain = _domain(VARIANTS[0][0])
    ops = list(domain.operations)
    target = next(i for i, o in enumerate(ops) if o.wbs_code == "2400")
    ops[target] = replace(ops[target], equipment_id="EQUIPMENT-GHOST-V1")
    with pytest.raises(ValueError, match="undeclared equipment_id"):
        calculate_thin_skin_build_estimate(
            replace(domain, operations=tuple(ops)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_duplicate_wbs_code_rejected():
    domain = _domain(VARIANTS[0][0])
    ops = list(domain.operations)
    ops[1] = replace(ops[1], wbs_code=ops[0].wbs_code)
    with pytest.raises(ValueError, match="duplicate wbs_code"):
        calculate_thin_skin_build_estimate(
            replace(domain, operations=tuple(ops)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_unsupported_labor_category_rejected():
    domain = _domain(VARIANTS[0][0])
    ops = list(domain.operations)
    ops[0] = replace(ops[0], labor_category="generic_labor")
    with pytest.raises(ValueError, match="unsupported labor_category"):
        calculate_thin_skin_build_estimate(
            replace(domain, operations=tuple(ops)),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


def test_cost_basis_id_mismatch_rejected():
    domain = _domain(VARIANTS[0][0])
    bad = replace(domain, cost_basis_id="MACHINE-COST-BASIS-WRONG-V1")
    with pytest.raises(ValueError, match="cost_basis_id mismatch"):
        calculate_thin_skin_build_estimate(
            bad,
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


@pytest.mark.parametrize(
    "status,message",
    [
        ("approved", "approved estimate status requires approved provenance"),
        ("reviewed", "draft provenance"),
    ],
)
def test_draft_provenance_cannot_overstate_estimate_status(status, message):
    domain = _domain(VARIANTS[0][0])
    with pytest.raises(ValueError, match=message):
        calculate_thin_skin_build_estimate(
            replace(domain, status=status),
            estimate_input_ref="x",
            effective_date="2026-07-26",
            repo_root=ROOT,
        )


# --------------------------------------------------------------------------
# WBS coverage and variant comparability
# --------------------------------------------------------------------------


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_every_wbs_leaf_carries_exactly_one_operation(input_name, estimate_name):
    raw = load_json(ESTIMATES_DIR / input_name)
    codes = [o["wbs_code"] for o in raw["operations"]]
    assert codes == EXPECTED_WBS


def test_variants_differ_only_in_core_material_and_core_prep():
    a = load_json(ESTIMATES_DIR / VARIANTS[0][0])
    b = load_json(ESTIMATES_DIR / VARIANTS[1][0])

    a_times = {o["wbs_code"]: o["time_model"] for o in a["operations"]}
    b_times = {o["wbs_code"]: o["time_model"] for o in b["operations"]}
    assert sorted(c for c in a_times if a_times[c] != b_times[c]) == ["1100"]

    a_core = [m for m in a["material_inputs"] if m["category"] == "core_material"]
    b_core = [m for m in b["material_inputs"] if m["category"] == "core_material"]
    assert len(a_core) == len(b_core) == 1
    assert a_core[0]["input_id"] != b_core[0]["input_id"]
    assert [m for m in a["material_inputs"] if m["category"] != "core_material"] == [
        m for m in b["material_inputs"] if m["category"] != "core_material"
    ]
    assert a["purchased_component_inputs"] == b["purchased_component_inputs"]


def test_poplar_core_labor_penalty_exceeds_its_material_penalty():
    """The comparison metric is total cost, not raw core material cost.

    Variant B's dearer core is the obvious difference; the glue-up labor it
    forces is the larger one. This asserts the finding the sprint exists to
    surface, so a future edit cannot erase it silently.
    """
    a = load_json(ESTIMATES_DIR / VARIANTS[0][1])["cost_summary"]
    b = load_json(ESTIMATES_DIR / VARIANTS[1][1])["cost_summary"]
    material_delta = b["core_material_cost"] - a["core_material_cost"]
    labor_delta = b["direct_build_labor_cost"] - a["direct_build_labor_cost"]
    assert material_delta > 0
    assert labor_delta > material_delta


# --------------------------------------------------------------------------
# Fixtures, schemas, and governance boundaries
# --------------------------------------------------------------------------


def test_product_fixture_matches_schema():
    jsonschema.validate(load_json(PRODUCT), load_json(PRODUCT_SCHEMA))


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_fixtures_match_schemas(input_name, estimate_name):
    jsonschema.validate(load_json(ESTIMATES_DIR / input_name), load_json(INPUT_SCHEMA))
    jsonschema.validate(
        load_json(ESTIMATES_DIR / estimate_name), load_json(ESTIMATE_SCHEMA)
    )


def test_equipment_fixtures_match_schemas():
    profiles = sorted(EQUIPMENT_DIR.glob("*.json"))
    bases = sorted(EQUIPMENT_BASIS_DIR.glob("*.json"))
    assert len(profiles) == len(bases) == 3
    for path in profiles:
        jsonschema.validate(load_json(path), load_json(EQUIPMENT_PROFILE_SCHEMA))
    for path in bases:
        jsonschema.validate(load_json(path), load_json(EQUIPMENT_BASIS_SCHEMA))


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_stored_estimate_matches_recomputation(input_name, estimate_name):
    estimate, recomputed = _recompute(input_name, estimate_name)
    expected = asdict(recomputed)
    for key, value in expected["cost_summary"].items():
        assert money_equal(estimate["cost_summary"][key], value), key
    for key, value in expected["time_summary"].items():
        assert estimate["time_summary"][key] == value, key
    assert len(estimate["operation_results"]) == len(EXPECTED_WBS)


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_governed_rates_are_used_and_commercial_rates_are_not(input_name, estimate_name):
    estimate = load_json(ESTIMATES_DIR / estimate_name)
    raw = load_json(ESTIMATES_DIR / input_name)
    assert estimate["machine_costing"]["machine_hour_rate"] == GOVERNED_MACHINE_HOUR_RATE
    assert [r["loaded_rate_per_hour"] for r in raw["labor_rate_inputs"]] == [
        GOVERNED_LOADED_LABOR_RATE
    ]

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and any(h in key for h in ("rate", "per_hour", "hourly"))
                ):
                    assert float(value) not in FORBIDDEN_RATES, f"{key}={value}"
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(estimate)
    scan(raw)


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_no_commercial_fields_present(input_name, estimate_name):
    forbidden = {
        "customer_price", "quote_price", "margin", "markup", "msrp",
        "dtc_price", "wholesale_price", "dealer_price", "overhead_allocation",
        "warranty_reserve", "billing_rate", "commercial_rate",
    }

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in forbidden, key
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(load_json(ESTIMATES_DIR / input_name))
    scan(load_json(ESTIMATES_DIR / estimate_name))


def test_nothing_claims_owner_confirmed_without_an_artifact():
    """No cost input in this sprint has an owner-confirmation artifact."""
    paths = (
        [PRODUCT]
        + sorted(EQUIPMENT_DIR.glob("*.json"))
        + sorted(EQUIPMENT_BASIS_DIR.glob("*.json"))
        + [ESTIMATES_DIR / n for pair in VARIANTS for n in pair]
    )

    def scan(node):
        if isinstance(node, dict):
            if node.get("source") == "owner_confirmed":
                assert node.get("references"), "owner_confirmed without references"
            for value in node.values():
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    for path in paths:
        scan(load_json(path))


@pytest.mark.parametrize("input_name,estimate_name", VARIANTS)
def test_estimate_stays_draft(input_name, estimate_name):
    estimate = load_json(ESTIMATES_DIR / estimate_name)
    assert estimate["status"] == "draft"
    assert estimate["provenance"]["confidence"] == "draft"


def test_validator_script_passes():
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------
# V1 non-regression: the solid-body baseline is retained, not replaced
# --------------------------------------------------------------------------


def test_v1_solid_body_records_remain_intact():
    """V1 stays recomputable so it can serve as comparison variant C."""
    v1_product = ROOT / "fixtures" / "products" / "cnc_electric_guitar_baseline_v1.json"
    assert v1_product.is_file()
    assert (
        load_json(v1_product)["product_id"] == "PRODUCT-CNC-ELECTRIC-GUITAR-BASELINE-V1"
    )
    result = subprocess.run(
        [sys.executable, str(V1_VALIDATE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_doc_records_the_evidence_gap():
    """The doc must keep saying this is an estimate, not evidence."""
    text = DOC.read_text(encoding="utf-8")
    for marker in (
        "THIN-SKIN-PILOT-CAPTURE-1",
        "28.97",
        "28.75",
        "counted twice",
    ):
        assert marker in text, marker
