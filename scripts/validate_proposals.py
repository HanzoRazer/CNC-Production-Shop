#!/usr/bin/env python3
"""Validate proposal fixtures against schema.

Usage:
    python scripts/validate_proposals.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail
"""

import json
import sys
from pathlib import Path

import jsonschema

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "proposals"
SCHEMA_PATH = (
    Path(__file__).parent.parent / "schemas" / "proposals" / "proposal_v1.schema.json"
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def validate_fixture(fixture_path: Path, schema: dict) -> tuple[bool, str]:
    """Validate a fixture against the schema.

    Returns:
        (success, message)
    """
    try:
        fixture = load_json(fixture_path)
    except json.JSONDecodeError as e:
        return False, f"FAIL {fixture_path.name}\n  JSON parse error: {e}"

    try:
        jsonschema.validate(fixture, schema)
        return True, f"PASS {fixture_path.name}"
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "$"
        return False, f"FAIL {fixture_path.name}\n  $.{path}: {e.message}"


def main() -> int:
    """Run all validations."""
    if not SCHEMA_PATH.exists():
        print(f"Schema not found: {SCHEMA_PATH}")
        return 1

    if not FIXTURES_DIR.exists():
        print(f"Fixtures directory not found: {FIXTURES_DIR}")
        return 1

    schema = load_json(SCHEMA_PATH)
    fixtures = list(FIXTURES_DIR.glob("*.json"))

    if not fixtures:
        print("No proposal fixtures found to validate")
        return 0

    all_passed = True
    for fixture_path in sorted(fixtures):
        passed, message = validate_fixture(fixture_path, schema)
        print(message)
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
