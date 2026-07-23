#!/usr/bin/env python3
"""Validate guitar product, estimate-input, and calculated estimate fixtures.

Usage:
    python scripts/validate_guitar_estimates.py

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

from business.calculators.machine_cost_basis import money_equal  # noqa: E402
from business.estimates.guitar import (  # noqa: E402
    calculate_guitar_build_estimate,
    operation_machine_minutes,
)
from business.estimates.loading import load_guitar_estimate_input  # noqa: E402

PRODUCT_SCHEMA = ROOT / "schemas" / "products" / "guitar_product_definition_v1.schema.json"
INPUT_SCHEMA = ROOT / "schemas" / "estimates" / "guitar_estimate_input_v1.schema.json"
ESTIMATE_SCHEMA = ROOT / "schemas" / "estimates" / "guitar_build_estimate_v1.schema.json"

PRODUCT_FIXTURE = ROOT / "fixtures" / "products" / "cnc_electric_guitar_baseline_v1.json"
INPUT_FIXTURE = (
    ROOT / "fixtures" / "estimates" / "guitar" / "cnc_electric_guitar_baseline_input_v1.json"
)
ESTIMATE_FIXTURE = (
    ROOT
    / "fixtures"
    / "estimates"
    / "guitar"
    / "cnc_electric_guitar_baseline_estimate_v1.json"
)

FORBIDDEN_PRICE_KEYS = {
    "customer_price",
    "quote_price",
    "target_margin_pct",
    "margin",
    "markup",
    "dealer_discount",
    "commercial_rate",
    "billing_rate",
}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_ref(ref: str) -> Path:
    if (
        not ref
        or ref.startswith("/")
        or ref.startswith("\\")
        or (len(ref) >= 2 and ref[1] == ":")
        or ".." in Path(ref).parts
    ):
        raise ValueError(f"ref must be repository-relative without '..': {ref!r}")
    return ROOT / ref


def _contains_forbidden(obj: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_PRICE_KEYS:
                errors.append(f"forbidden field {path}.{key}")
            errors.extend(_contains_forbidden(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            errors.extend(_contains_forbidden(value, f"{path}[{idx}]"))
    return errors


def validate_schema(fixture_path: Path, schema_path: Path) -> list[str]:
    errors: list[str] = []
    data = load_json(fixture_path)
    schema = load_json(schema_path)
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "$"
        errors.append(f"FAIL {fixture_path.name} schema $.{loc}: {exc.message}")
        return errors
    forbidden = _contains_forbidden(data)
    if forbidden:
        errors.extend(f"FAIL {fixture_path.name}: {msg}" for msg in forbidden)
    return errors


def validate_lineage_and_recompute() -> list[str]:
    errors: list[str] = []
    product = load_json(PRODUCT_FIXTURE)
    estimate_input = load_json(INPUT_FIXTURE)
    estimate = load_json(ESTIMATE_FIXTURE)

    if estimate_input["product_id"] != product["product_id"]:
        errors.append("FAIL product_id mismatch between product and estimate-input")
    if estimate["product_id"] != product["product_id"]:
        errors.append("FAIL product_id mismatch between product and estimate")
    if estimate["estimate_input_id"] != estimate_input["estimate_input_id"]:
        errors.append("FAIL estimate_input_id mismatch")

    try:
        product_path = _resolve_ref(estimate_input["product_ref"])
        profile_path = _resolve_ref(estimate_input["machine_profile_ref"])
        basis_path = _resolve_ref(estimate_input["cost_basis_ref"])
        input_path = _resolve_ref(estimate["estimate_input_ref"])
    except ValueError as exc:
        return [f"FAIL ref resolution: {exc}"]

    for path, label in [
        (product_path, "product_ref"),
        (profile_path, "machine_profile_ref"),
        (basis_path, "cost_basis_ref"),
        (input_path, "estimate_input_ref"),
    ]:
        if not path.is_file():
            errors.append(f"FAIL missing {label}: {path}")
    if errors:
        return errors

    profile = load_json(profile_path)
    basis = load_json(basis_path)
    if profile.get("machine_id") != estimate_input["machine_id"]:
        errors.append("FAIL machine profile machine_id mismatch")
    if basis.get("machine_id") != estimate_input["machine_id"]:
        errors.append("FAIL cost basis machine_id mismatch")
    if basis.get("cost_basis_id") != estimate_input["cost_basis_id"]:
        errors.append("FAIL cost_basis_id mismatch")

    if estimate_input["provenance"]["confidence"] == "draft" and estimate["status"] not in {
        "draft",
        "superseded",
        "retired",
    }:
        errors.append("FAIL draft provenance cannot overstate estimate status")

    domain_input = load_guitar_estimate_input(INPUT_FIXTURE)
    recomputed = calculate_guitar_build_estimate(
        domain_input,
        estimate_id=estimate["estimate_id"],
        estimate_input_ref=estimate["estimate_input_ref"],
        effective_date=estimate["calculation"]["effective_date"],
    )
    expected = asdict(recomputed)

    for key, value in expected["cost_summary"].items():
        actual = estimate["cost_summary"].get(key)
        if not money_equal(actual, value):
            errors.append(
                f"FAIL cost_summary.{key}: fixture={actual!r} recomputed={value!r}"
            )

    total_minutes = sum(
        operation_machine_minutes(op, domain_input.quantity)
        for op in domain_input.operations
    )
    if not money_equal(estimate["machine_costing"]["runtime_minutes"], total_minutes):
        errors.append("FAIL machine_costing.runtime_minutes mismatch")
    if not money_equal(
        estimate["machine_costing"]["derived_machine_time_cost"],
        expected["machine_costing"]["derived_machine_time_cost"],
    ):
        errors.append("FAIL machine_costing.derived_machine_time_cost mismatch")
    if not money_equal(
        estimate["cost_summary"]["machine_time_cost"],
        estimate["machine_costing"]["derived_machine_time_cost"],
    ):
        errors.append("FAIL machine_time_cost != machine_costing.derived")

    if estimate["machine_costing"]["cost_basis_role"] != "internal_technical_cost":
        errors.append("FAIL cost_basis_role must be internal_technical_cost")

    return errors


def main() -> int:
    all_errors: list[str] = []
    pairs = [
        (PRODUCT_FIXTURE, PRODUCT_SCHEMA),
        (INPUT_FIXTURE, INPUT_SCHEMA),
        (ESTIMATE_FIXTURE, ESTIMATE_SCHEMA),
    ]
    for fixture, schema in pairs:
        if not fixture.exists():
            all_errors.append(f"FAIL missing fixture {fixture}")
            continue
        errs = validate_schema(fixture, schema)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"PASS {fixture.relative_to(ROOT).as_posix()}")

    all_errors.extend(validate_lineage_and_recompute())
    if all_errors:
        for err in all_errors:
            print(err)
        return 1

    print("PASS lineage and recomputation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
