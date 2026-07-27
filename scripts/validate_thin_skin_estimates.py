#!/usr/bin/env python3
"""Validate thin-skin product, equipment, estimate-input, and estimate fixtures.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1

Usage:
    python scripts/validate_thin_skin_estimates.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.calculators.equipment_cost_basis import (  # noqa: E402
    assemble_equipment_hour_rate,
    derive_equipment_electricity_cost_per_hour,
)
from business.calculators.machine_cost_basis import as_money, money_equal  # noqa: E402
from business.estimates.guitar_v2 import (  # noqa: E402
    calculate_thin_skin_build_estimate,
)
from business.estimates.loading_v2 import load_thin_skin_estimate_input  # noqa: E402

SCHEMAS = ROOT / "schemas"
PRODUCT_SCHEMA = SCHEMAS / "products" / "thin_skin_guitar_product_definition_v1.schema.json"
INPUT_SCHEMA = SCHEMAS / "estimates" / "thin_skin_estimate_input_v2.schema.json"
ESTIMATE_SCHEMA = SCHEMAS / "estimates" / "thin_skin_build_estimate_v2.schema.json"
EQUIPMENT_PROFILE_SCHEMA = SCHEMAS / "equipment" / "equipment_profile_v1.schema.json"
EQUIPMENT_BASIS_SCHEMA = SCHEMAS / "equipment" / "equipment_cost_basis_v1.schema.json"

PRODUCT_FIXTURE = ROOT / "fixtures" / "products" / "thin_skin_electric_guitar_baseline_v1.json"
EQUIPMENT_DIR = ROOT / "fixtures" / "equipment"
EQUIPMENT_BASIS_DIR = EQUIPMENT_DIR / "cost_basis"
ESTIMATES_DIR = ROOT / "fixtures" / "estimates" / "guitar"

VARIANTS = [
    ("thin_skin_variant_a_input_v1.json", "thin_skin_variant_a_estimate_v1.json"),
    ("thin_skin_variant_b_input_v1.json", "thin_skin_variant_b_estimate_v1.json"),
]

# Commercial concepts that must not appear anywhere in a direct-cost layer.
FORBIDDEN_PRICE_KEYS = {
    "customer_price",
    "quote_price",
    "target_margin_pct",
    "margin",
    "markup",
    "dealer_discount",
    "dealer_price",
    "wholesale_price",
    "dtc_price",
    "msrp",
    "commercial_rate",
    "billing_rate",
    "overhead_allocation",
    "warranty_reserve",
}

# The commercial machine rate and the future burdened shop-rate range must not
# leak into this layer. Values are checked against every numeric leaf.
FORBIDDEN_RATE_VALUES = {72.0, 45.0, 75.0}
RATE_KEY_HINTS = ("rate", "per_hour", "hourly")


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _walk(obj: object, path: str = "$"):
    """Yield (path, key, value) for every dict entry in a JSON document."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from _walk(value, f"{path}[{idx}]")


def _contains_forbidden(data: dict, label: str) -> list[str]:
    errors: list[str] = []
    for path, key, value in _walk(data):
        if key in FORBIDDEN_PRICE_KEYS:
            errors.append(f"FAIL {label}: forbidden field {path}")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and any(hint in key for hint in RATE_KEY_HINTS)
            and float(value) in FORBIDDEN_RATE_VALUES
        ):
            errors.append(
                f"FAIL {label}: {path} = {value} is a commercial/burdened rate and "
                f"must not appear in an internal direct-cost record"
            )
    return errors


def _check_owner_confirmed(data: dict, label: str) -> list[str]:
    """owner_confirmed provenance requires a supporting artifact reference."""
    errors: list[str] = []
    for path, key, value in _walk(data):
        if key == "source" and value == "owner_confirmed":
            parent_path = path.rsplit(".", 1)[0]
            node = _resolve_pointer(data, parent_path)
            refs = node.get("references") if isinstance(node, dict) else None
            if not refs:
                errors.append(
                    f"FAIL {label}: {parent_path} claims owner_confirmed with no "
                    f"supporting references artifact"
                )
    return errors


def _resolve_pointer(data: dict, path: str) -> object:
    node: object = data
    for part in path.split(".")[1:]:
        if "[" in part:
            name, _, rest = part.partition("[")
            if name and isinstance(node, dict):
                node = node.get(name)
            for chunk in rest.rstrip("]").split("]["):
                if isinstance(node, list) and chunk.isdigit():
                    node = node[int(chunk)]
        elif isinstance(node, dict):
            node = node.get(part)
    return node


def validate_schema(fixture_path: Path, schema_path: Path) -> list[str]:
    errors: list[str] = []
    data = load_json(fixture_path)
    schema = load_json(schema_path)
    label = fixture_path.name
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "$"
        return [f"FAIL {label} schema $.{loc}: {exc.message}"]
    errors.extend(_contains_forbidden(data, label))
    errors.extend(_check_owner_confirmed(data, label))
    return errors


def validate_equipment() -> list[str]:
    """Schema, rate recomputation, and profile/basis agreement for equipment."""
    errors: list[str] = []
    profiles = sorted(EQUIPMENT_DIR.glob("*.json"))
    if not profiles:
        return ["FAIL no equipment profiles found"]

    for profile_path in profiles:
        errs = validate_schema(profile_path, EQUIPMENT_PROFILE_SCHEMA)
        if errs:
            errors.extend(errs)
            continue
        print(f"PASS {profile_path.relative_to(ROOT).as_posix()}")

    for basis_path in sorted(EQUIPMENT_BASIS_DIR.glob("*.json")):
        errs = validate_schema(basis_path, EQUIPMENT_BASIS_SCHEMA)
        if errs:
            errors.extend(errs)
            continue

        basis = load_json(basis_path)
        label = basis_path.name
        electricity = basis["electricity"]
        derived_kwh = derive_equipment_electricity_cost_per_hour(
            electricity["connected_load_kw"],
            electricity["load_factor"],
            electricity["price_per_kwh"],
        )
        if not money_equal(electricity["electricity_cost_per_hour"], derived_kwh):
            errors.append(
                f"FAIL {label}: electricity_cost_per_hour "
                f"{electricity['electricity_cost_per_hour']} != derived {derived_kwh}"
            )

        assembled = assemble_equipment_hour_rate(
            basis["equipment_burden_rate_per_hour"],
            electricity["electricity_cost_per_hour"],
            basis["consumables_cost_per_hour"],
        )
        if not money_equal(basis["equipment_hour_rate"], assembled.equipment_hour_rate):
            errors.append(
                f"FAIL {label}: equipment_hour_rate {basis['equipment_hour_rate']} "
                f"!= burden + electricity + consumables "
                f"({assembled.equipment_hour_rate})"
            )

        matching = [
            p for p in profiles if load_json(p).get("equipment_id") == basis["equipment_id"]
        ]
        if not matching:
            errors.append(f"FAIL {label}: no equipment profile for {basis['equipment_id']}")
            continue
        profile = load_json(matching[0])
        profile_kw = profile["connected_load_estimate"]["total_kw"]
        if not money_equal(profile_kw, electricity["connected_load_kw"]):
            errors.append(
                f"FAIL {label}: connected_load_kw {electricity['connected_load_kw']} "
                f"does not mirror profile total_kw {profile_kw}"
            )
        components_kw = sum(
            c["kw"] for c in profile["connected_load_estimate"]["components"]
        )
        if not money_equal(components_kw, profile_kw):
            errors.append(
                f"FAIL {matching[0].name}: connected load components sum "
                f"{components_kw} != total_kw {profile_kw}"
            )
        if not errors:
            print(f"PASS {basis_path.relative_to(ROOT).as_posix()}")
    return errors


def validate_variant(input_name: str, estimate_name: str) -> list[str]:
    """Lineage, recomputation, and policy gates for one governed variant."""
    errors: list[str] = []
    input_path = ESTIMATES_DIR / input_name
    estimate_path = ESTIMATES_DIR / estimate_name
    product = load_json(PRODUCT_FIXTURE)
    estimate_input = load_json(input_path)
    estimate = load_json(estimate_path)
    label = estimate_name

    if estimate_input["product_id"] != product["product_id"]:
        errors.append(f"FAIL {label}: product_id mismatch product vs estimate-input")
    if estimate["product_id"] != product["product_id"]:
        errors.append(f"FAIL {label}: product_id mismatch product vs estimate")
    if estimate["estimate_input_id"] != estimate_input["estimate_input_id"]:
        errors.append(f"FAIL {label}: estimate_input_id mismatch")
    if estimate["variant_id"] != estimate_input["variant_id"]:
        errors.append(f"FAIL {label}: variant_id mismatch")

    refs = [
        (estimate_input["product_ref"], "product_ref"),
        (estimate_input["machine_profile_ref"], "machine_profile_ref"),
        (estimate_input["cost_basis_ref"], "cost_basis_ref"),
        (estimate["estimate_input_ref"], "estimate_input_ref"),
    ]
    for ref in estimate_input["equipment_refs"]:
        refs.append((ref["equipment_profile_ref"], "equipment_profile_ref"))
        refs.append((ref["cost_basis_ref"], "equipment cost_basis_ref"))

    for ref, name in refs:
        if not ref or ref.startswith(("/", "\\")) or ".." in Path(ref).parts:
            errors.append(f"FAIL {label}: {name} must be repo-relative without '..': {ref!r}")
        elif not (ROOT / ref).is_file():
            errors.append(f"FAIL {label}: missing {name}: {ref}")
    if errors:
        return errors

    if estimate_input["provenance"]["confidence"] == "draft" and estimate["status"] not in {
        "draft",
        "superseded",
        "retired",
    }:
        errors.append(f"FAIL {label}: draft provenance cannot overstate estimate status")

    domain_input = load_thin_skin_estimate_input(input_path)
    recomputed = calculate_thin_skin_build_estimate(
        domain_input,
        estimate_id=estimate["estimate_id"],
        estimate_input_ref=estimate["estimate_input_ref"],
        effective_date=estimate["calculation"]["effective_date"],
        repo_root=ROOT,
    )
    expected = asdict(recomputed)

    for key, value in expected["cost_summary"].items():
        actual = estimate["cost_summary"].get(key)
        if not money_equal(actual, value):
            errors.append(
                f"FAIL {label} cost_summary.{key}: fixture={actual!r} recomputed={value!r}"
            )
    for key, value in expected["time_summary"].items():
        actual = estimate["time_summary"].get(key)
        if actual != value:
            errors.append(
                f"FAIL {label} time_summary.{key}: fixture={actual!r} recomputed={value!r}"
            )

    summary = estimate["cost_summary"]

    # The eighteenth field must be the sum of the other seventeen.
    component_total = as_money(
        sum(v for k, v in summary.items() if k != "total_direct_manufacturing_cost")
    )
    if not money_equal(summary["total_direct_manufacturing_cost"], component_total):
        errors.append(
            f"FAIL {label}: total_direct_manufacturing_cost "
            f"{summary['total_direct_manufacturing_cost']} != sum of categories "
            f"{component_total}"
        )

    # Machine and equipment dollars must trace to their governed derivations.
    if not money_equal(
        summary["machine_time_cost"], estimate["machine_costing"]["derived_machine_time_cost"]
    ):
        errors.append(f"FAIL {label}: machine_time_cost != machine_costing.derived")
    if estimate["machine_costing"]["cost_basis_role"] != "internal_technical_cost":
        errors.append(f"FAIL {label}: machine cost_basis_role must be internal_technical_cost")

    occupancy_total = as_money(
        sum(e["derived_occupancy_cost"] for e in estimate["equipment_costing"])
    )
    if not money_equal(summary["equipment_occupancy_cost"], occupancy_total):
        errors.append(
            f"FAIL {label}: equipment_occupancy_cost != sum of equipment_costing"
        )
    for record in estimate["equipment_costing"]:
        if record["cost_basis_role"] != "internal_technical_cost":
            errors.append(
                f"FAIL {label}: equipment {record['equipment_id']} cost_basis_role "
                f"must be internal_technical_cost"
            )

    # Every WBS leaf carries exactly one operation, and CNC occupancy never
    # lands on an equipment record.
    op_codes = [o["wbs_code"] for o in estimate_input["operations"]]
    if len(op_codes) != len(set(op_codes)):
        errors.append(f"FAIL {label}: duplicate wbs_code in operations")
    for op in estimate_input["operations"]:
        tm = op["time_model"]
        if tm["machine_runtime_minutes"] > 0 and op["equipment_id"]:
            errors.append(
                f"FAIL {label}: operation {op['operation_id']} books both CNC runtime "
                f"and equipment occupancy; split it so the two never blend"
            )

    # Double-count gate: measured rework and a full process reserve must not
    # both carry the same risk. See THIN_SKIN_GUITAR_BUILD_ESTIMATE_V1.md.
    total_rework = estimate["time_summary"]["total_rework_minutes"]
    reserve_rate = estimate_input["process_yield_reserve_policy"]["reserve_rate"]
    if total_rework > 0 and reserve_rate > 0.05:
        errors.append(
            f"FAIL {label}: operations book {total_rework} rework minutes while the "
            f"process reserve is still {reserve_rate:.0%}. Populating measured rework "
            f"requires reducing the reserve, or process risk is counted twice."
        )

    # The reserve base must never include the scrap allowance.
    risk = estimate["risk_basis"]
    assembled_base = as_money(
        risk["process_reserve_material_base"]
        + risk["process_reserve_machine_base"]
        + risk["process_reserve_equipment_base"]
        + risk["process_reserve_labor_base"]
    )
    if not money_equal(risk["process_reserve_base"], assembled_base):
        errors.append(f"FAIL {label}: process_reserve_base does not match its components")
    if not money_equal(
        summary["process_rework_and_yield_reserve"],
        as_money(risk["process_reserve_base"] * risk["process_reserve_rate"]),
    ):
        errors.append(f"FAIL {label}: process reserve is not rate x base")
    if not money_equal(
        summary["material_scrap_allowance"],
        as_money(risk["material_scrap_base"] * risk["material_scrap_rate"]),
    ):
        errors.append(f"FAIL {label}: material scrap allowance is not rate x base")

    return errors


def validate_variant_comparability() -> list[str]:
    """Variants A and B must differ only where the documentation says they do."""
    errors: list[str] = []
    a = load_json(ESTIMATES_DIR / VARIANTS[0][0])
    b = load_json(ESTIMATES_DIR / VARIANTS[1][0])

    a_ops = {o["wbs_code"]: o["time_model"] for o in a["operations"]}
    b_ops = {o["wbs_code"]: o["time_model"] for o in b["operations"]}
    if set(a_ops) != set(b_ops):
        errors.append("FAIL variants do not share the same WBS leaves")
        return errors
    differing = sorted(code for code in a_ops if a_ops[code] != b_ops[code])
    if differing != ["1100"]:
        errors.append(
            f"FAIL variant operation times differ at {differing}; the governed "
            f"comparison permits only WBS 1100 (core stock preparation)"
        )

    a_core = [m for m in a["material_inputs"] if m["category"] == "core_material"]
    b_core = [m for m in b["material_inputs"] if m["category"] == "core_material"]
    if len(a_core) != 1 or len(b_core) != 1:
        errors.append("FAIL each variant must declare exactly one core_material input")
    a_rest = [m for m in a["material_inputs"] if m["category"] != "core_material"]
    b_rest = [m for m in b["material_inputs"] if m["category"] != "core_material"]
    if a_rest != b_rest:
        errors.append("FAIL variants differ in non-core material inputs")
    if a["purchased_component_inputs"] != b["purchased_component_inputs"]:
        errors.append("FAIL variants differ in purchased components")
    return errors


def main() -> int:
    all_errors: list[str] = []

    if not PRODUCT_FIXTURE.exists():
        all_errors.append(f"FAIL missing fixture {PRODUCT_FIXTURE}")
    else:
        errs = validate_schema(PRODUCT_FIXTURE, PRODUCT_SCHEMA)
        all_errors.extend(errs)
        if not errs:
            print(f"PASS {PRODUCT_FIXTURE.relative_to(ROOT).as_posix()}")

    all_errors.extend(validate_equipment())

    for input_name, estimate_name in VARIANTS:
        for fixture, schema in [
            (ESTIMATES_DIR / input_name, INPUT_SCHEMA),
            (ESTIMATES_DIR / estimate_name, ESTIMATE_SCHEMA),
        ]:
            if not fixture.exists():
                all_errors.append(f"FAIL missing fixture {fixture}")
                continue
            errs = validate_schema(fixture, schema)
            all_errors.extend(errs)
            if not errs:
                print(f"PASS {fixture.relative_to(ROOT).as_posix()}")
        all_errors.extend(validate_variant(input_name, estimate_name))

    all_errors.extend(validate_variant_comparability())

    if all_errors:
        for err in all_errors:
            print(err)
        return 1

    print("PASS lineage, recomputation, risk policy, and variant comparability")
    return 0


if __name__ == "__main__":
    sys.exit(main())
