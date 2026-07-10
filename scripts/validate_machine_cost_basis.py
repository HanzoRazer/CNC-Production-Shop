#!/usr/bin/env python3
"""Validate machine cost-basis fixtures against schema and cross-check derivations.

Beyond JSON Schema validation, this checks the governed derivations:
  - electricity.electricity_cost_per_hour == connected_load_kw * load_factor * price_per_kwh
  - machine_hour_rate == burden + electricity + tooling
  - the referenced machine profile exists and its connected_load_estimate.total_kw
    matches electricity.connected_load_kw

Usage:
    python scripts/validate_machine_cost_basis.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail
"""

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "fixtures" / "machines" / "cost_basis"
PROFILES_DIR = ROOT / "fixtures" / "machines"
SCHEMA_PATH = ROOT / "schemas" / "machines" / "machine_cost_basis_v1.schema.json"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def _load_profiles_by_id() -> dict[str, dict]:
    """Load machine profiles keyed by machine_id (non-recursive, profiles dir only)."""
    profiles: dict[str, dict] = {}
    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            record = load_json(path)
        except json.JSONDecodeError:
            continue
        machine_id = record.get("machine_id")
        if machine_id:
            profiles[machine_id] = record
    return profiles


def validate_fixture(
    fixture_path: Path, schema: dict, profiles: dict[str, dict]
) -> tuple[bool, str]:
    """Validate a fixture against the schema and cross-check derivations.

    Returns:
        (success, message)
    """
    try:
        fixture = load_json(fixture_path)
    except json.JSONDecodeError as e:
        return False, f"FAIL {fixture_path.name}\n  JSON parse error: {e}"

    try:
        jsonschema.validate(fixture, schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "$"
        return False, f"FAIL {fixture_path.name}\n  $.{path}: {e.message}"

    elec = fixture["electricity"]
    expected_elec = round(
        elec["connected_load_kw"] * elec["load_factor"] * elec["price_per_kwh"], 2
    )
    if expected_elec != elec["electricity_cost_per_hour"]:
        return False, (
            f"FAIL {fixture_path.name}\n  electricity_cost_per_hour "
            f"{elec['electricity_cost_per_hour']} != derived {expected_elec}"
        )

    expected_rate = round(
        fixture["machine_burden_rate_per_hour"]
        + elec["electricity_cost_per_hour"]
        + fixture["tooling_cost_per_hour"],
        2,
    )
    if expected_rate != fixture["machine_hour_rate"]:
        return False, (
            f"FAIL {fixture_path.name}\n  machine_hour_rate "
            f"{fixture['machine_hour_rate']} != derived {expected_rate}"
        )

    machine_id = fixture["machine_id"]
    profile = profiles.get(machine_id)
    if profile is None:
        return False, (f"FAIL {fixture_path.name}\n  references unknown machine_id={machine_id!r}")
    profile_load = profile["connected_load_estimate"]["total_kw"]
    if profile_load != elec["connected_load_kw"]:
        return False, (
            f"FAIL {fixture_path.name}\n  connected_load_kw {elec['connected_load_kw']} "
            f"!= profile total_kw {profile_load}"
        )

    return True, f"PASS {fixture_path.name}"


def main() -> int:
    """Run all validations."""
    if not SCHEMA_PATH.exists():
        print(f"Schema not found: {SCHEMA_PATH}")
        return 1

    if not FIXTURES_DIR.exists():
        print(f"Fixtures directory not found: {FIXTURES_DIR}")
        return 1

    schema = load_json(SCHEMA_PATH)
    profiles = _load_profiles_by_id()

    fixtures = list(FIXTURES_DIR.glob("*.json"))
    if not fixtures:
        print("No fixtures found to validate")
        return 0

    all_passed = True
    for fixture_path in sorted(fixtures):
        passed, message = validate_fixture(fixture_path, schema, profiles)
        print(message)
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
