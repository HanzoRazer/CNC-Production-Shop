#!/usr/bin/env python3
"""Validate bid fixtures against schema and optional machine-costing refs.

Usage:
    python scripts/validate_bid_fixtures.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail

Machine-costing cross-checks import only the calculator money helpers (not the
bids package) so this script stays a lightweight fixture gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.calculators.machine_cost_basis import (  # noqa: E402
    derive_machine_time_cost,
    money_equal,
)

FIXTURES_DIR = ROOT / "fixtures" / "bids"
SCHEMA_PATH = ROOT / "schemas" / "bids" / "bid_v1.schema.json"

# Progressive review ladder. Terminal statuses require exact match.
_PROGRESSIVE_STATUS_RANK = {
    "draft": 0,
    "reviewed": 1,
    "approved": 2,
}
_TERMINAL_STATUSES = frozenset({"superseded", "retired"})


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_portable_repo_ref(ref: str) -> bool:
    """Reject absolute, parent-escaping, or empty refs."""
    if not ref or ref.startswith("/") or ref.startswith("\\"):
        return False
    if len(ref) >= 2 and ref[1] == ":":
        return False
    parts = Path(ref).parts
    if ".." in parts:
        return False
    return True


def _resolve_ref(ref: str) -> Path:
    """Resolve a portable repo-relative fixture ref."""
    if not _is_portable_repo_ref(ref):
        raise ValueError(f"ref must be repository-relative without '..': {ref!r}")
    return ROOT / ref


def _provenance_status_ok(bid_status: object, basis_status: object) -> bool:
    """Return True when bid provenance does not overstate the cost basis."""
    if not isinstance(bid_status, str) or not isinstance(basis_status, str):
        return False
    if bid_status in _TERMINAL_STATUSES or basis_status in _TERMINAL_STATUSES:
        # Terminal lifecycle states are not ranked; require exact agreement.
        return bid_status == basis_status
    if bid_status in _PROGRESSIVE_STATUS_RANK and basis_status in _PROGRESSIVE_STATUS_RANK:
        return _PROGRESSIVE_STATUS_RANK[bid_status] <= _PROGRESSIVE_STATUS_RANK[basis_status]
    return bid_status == basis_status


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

    try:
        profile_path = _resolve_ref(profile_ref)
        cost_basis_path = _resolve_ref(cost_basis_ref)
    except ValueError as exc:
        errors.append(f"{prefix}\n  {exc}")
        return errors

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
    if not money_equal(expected_rate, mc.get("machine_hour_rate")):
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

    if not money_equal(recomputed, mc.get("derived_machine_time_cost")):
        errors.append(
            f"{prefix}\n  derived_machine_time_cost {mc.get('derived_machine_time_cost')!r} "
            f"!= recomputed {recomputed!r}"
        )

    line_item_cost = fixture.get("cost_basis", {}).get("machine_time_cost")
    if not money_equal(line_item_cost, mc.get("derived_machine_time_cost")):
        errors.append(
            f"{prefix}\n  cost_basis.machine_time_cost {line_item_cost!r} "
            f"!= machine_costing.derived_machine_time_cost "
            f"{mc.get('derived_machine_time_cost')!r}"
        )

    if not _provenance_status_ok(mc.get("provenance_status"), cost_basis.get("status")):
        errors.append(
            f"{prefix}\n  provenance_status {mc.get('provenance_status')!r} overstates "
            f"or mismatches cost-basis status {cost_basis.get('status')!r}"
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
