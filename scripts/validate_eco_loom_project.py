#!/usr/bin/env python3
"""Validate Eco-Loom project capture files against schemas.

Usage:
    python scripts/validate_eco_loom_project.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail
"""

import json
import sys
from pathlib import Path

import jsonschema

PROJECT_DIR = Path(__file__).parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "projects"

VALIDATIONS = [
    (
        "eco_loom_project_capture_v1.json",
        "project_capture_v1.schema.json",
    ),
    (
        "eco_loom_assumption_register_v1.json",
        "assumption_register_v1.schema.json",
    ),
    (
        "eco_loom_open_questions_v1.json",
        "open_questions_v1.schema.json",
    ),
]


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def validate_file(fixture_name: str, schema_name: str) -> tuple[bool, str]:
    """Validate a fixture against its schema.

    Returns:
        (success, message)
    """
    fixture_path = PROJECT_DIR / fixture_name
    schema_path = SCHEMA_DIR / schema_name

    if not fixture_path.exists():
        return False, f"Fixture not found: {fixture_path}"

    if not schema_path.exists():
        return False, f"Schema not found: {schema_path}"

    try:
        fixture = load_json(fixture_path)
        schema = load_json(schema_path)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"

    try:
        jsonschema.validate(fixture, schema)
        return True, f"[PASS] {fixture_name}"
    except jsonschema.ValidationError as e:
        return False, f"[FAIL] {fixture_name}: {e.message}"


def main() -> int:
    """Run all validations."""
    all_passed = True
    messages = []

    for fixture_name, schema_name in VALIDATIONS:
        passed, message = validate_file(fixture_name, schema_name)
        messages.append(message)
        if not passed:
            all_passed = False

    for msg in messages:
        print(msg)

    print()
    if all_passed:
        print("RESULT: PASS")
        return 0
    else:
        print("RESULT: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
