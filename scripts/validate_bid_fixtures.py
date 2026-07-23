#!/usr/bin/env python3
"""Validate bid fixtures against schema and optional machine-costing refs.

Usage:
    python scripts/validate_bid_fixtures.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.bids.machine_costing import derive_machine_time_cost  # noqa: E402

FIXTURES_DIR = ROOT / "fixtures" / "bids"
SCHEMA_PATH = ROOT / "schemas" / "bids" / "bid_v1.schema.json"

_STATUS_RANK = {
    "draft": 0,
    "reviewed": 1,
    "approved": 2,
}


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_ref(ref: str) -> Path:
    """Resolve a fixture ref relative to the repository root."""
    path = Path(ref)
    if path.is_absolute():
        return path
    return ROOT / path


def validate_machine_costing(fixture: dict, fixture_path: Path) -> list[str]:
    """Cross-validate an optional machine_costing block against artifacts."""
    mc = fixture.get("machine_costing")
    if mc is None:
        return []

    errors: list[str] = []
    prefix = f"FAIL {fixture_path.name}"

    profile_ref = mc.get("machine_profile_ref")
    cost_basis_ref = mc.get("cost_basis_ref")
    if not isinstance(profile_ref, str) or not profile_ref:
        errors.append(f"{prefix}\n  machine_costing.machine_profile_ref is required")
        return errors
    if not isinstance(cost_basis_ref, str) or not cost_basis_ref:
        errors.append(f"{prefix}\n  machine_costing.cost_basis_ref is required")
        return errors

    profile_path = _resolve_ref(profile_ref)
    cost_basis_path = _resolve_ref(cost_basis_ref)

    if not profile_path.is_file():
        errors.append(
            f"{prefix}\n  machine_profile_ref does not exist: {profile_ref}"
        )
    if not cost_basis_path.is_file():
        errors.append(
            f"{prefix}\n  cost_basis_ref does not exist: {cost_basis_ref}"
        )
    if errors:
        return errors

    profile = load_json(profile_path)
    cost_basis = load_json(cost_basis_path)

    if profile.get("machine_id") != mc.get("machine_id"):
        errors.append(
            f"{prefix}\n  machine_id mismatch: bid={mc.get('machine_id')!r} "
            f"profile={profile.get('machine_id')!r}"
        )
    if cost_basis.get("machine_id") != mc.get("machine_id"):
        errors.append(
            f"{prefix}\n  cost basis machine_id mismatch: bid={mc.get('machine_id')!r} "
            f"cost_basis={cost_basis.get('machine_id')!r}"
        )
    if cost_basis.get("cost_basis_id") != mc.get("cost_basis_id"):
        errors.append(
            f"{prefix}\n  cost_basis_id mismatch: bid={mc.get('cost_basis_id')!r} "
            f"fixture={cost_basis.get('cost_basis_id')!r}"
        )

    expected_rate = cost_basis.get("machine_hour_rate")
    if expected_rate != mc.get("machine_hour_rate"):
        errors.append(
            f"{prefix}\n  machine_hour_rate mismatch: bid={mc.get('machine_hour_rate')!r} "
            f"cost_basis={expected_rate!r}"
        )

    try:
        recomputed = derive_machine_time_cost(
            float(mc["machine_hour_rate"]),
            float(mc["runtime_minutes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"{prefix}\n  cannot recompute derived cost: {exc}")
        return errors

    if recomputed != mc.get("derived_machine_time_cost"):
        errors.append(
            f"{prefix}\n  derived_machine_time_cost {mc.get('derived_machine_time_cost')!r} "
            f"!= recomputed {recomputed!r}"
        )

    line_item_cost = fixture.get("cost_basis", {}).get("machine_time_cost")
    if line_item_cost != mc.get("derived_machine_time_cost"):
        errors.append(
            f"{prefix}\n  cost_basis.machine_time_cost {line_item_cost!r} "
            f"!= machine_costing.derived_machine_time_cost "
            f"{mc.get('derived_machine_time_cost')!r}"
        )

    basis_status = cost_basis.get("status")
    bid_status = mc.get("provenance_status")
    if basis_status in _STATUS_RANK and bid_status in _STATUS_RANK:
        if _STATUS_RANK[bid_status] > _STATUS_RANK[basis_status]:
            errors.append(
                f"{prefix}\n  provenance_status {bid_status!r} overstates "
                f"cost-basis status {basis_status!r}"
            )
    elif bid_status != basis_status:
        errors.append(
            f"{prefix}\n  provenance_status {bid_status!r} does not match "
            f"cost-basis status {basis_status!r}"
        )

    return errors


def validate_fixture(fixture_path: Path, schema: dict) -> tuple[bool, list[str]]:
    """Validate a fixture against schema and optional machine-costing rules."""
    try:
        fixture = load_json(fixture_path)
    except json.JSONDecodeError as e:
        return False, [f"FAIL {fixture_path.name}\n  JSON parse error: {e}"]

    messages: list[str] = []
    try:
        jsonschema.validate(fixture, schema)
        messages.append(f"PASS {fixture_path.name}")
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "$"
        return False, [f"FAIL {fixture_path.name}\n  $.{path}: {e.message}"]

    cross_errors = validate_machine_costing(fixture, fixture_path)
    if cross_errors:
        return False, cross_errors

    return True, messages


def main() -> int:
    """Run all validations."""
    if not SCHEMA_PATH.exists():
        print(f"Schema not found: {SCHEMA_PATH}")
        return 1

    if not FIXTURES_DIR.exists():
        print(f"Fixtures directory not found: {FIXTURES_DIR}")
        return 1

    schema = load_json(SCHEMA_PATH)

    # Exclude summary files (validated by validate_bid_summaries.py)
    fixtures = [
        f for f in FIXTURES_DIR.glob("*.json") if "_summary_" not in f.name
    ]

    if not fixtures:
        print("No fixtures found to validate")
        return 0

    all_passed = True
    for fixture_path in sorted(fixtures):
        passed, messages = validate_fixture(fixture_path, schema)
        for message in messages:
            print(message)
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
