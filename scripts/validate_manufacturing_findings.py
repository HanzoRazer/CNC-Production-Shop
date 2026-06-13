#!/usr/bin/env python3
"""Validate manufacturing findings files against schema.

Dev Order: ECO-LOOM-MFG-FINDINGS-1

Validates:
1. Manufacturing findings files against manufacturing_findings_v1.schema.json
"""

import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "manufacturing"
PROJECTS_DIR = Path(__file__).parent.parent / "projects"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def main() -> int:
    """Validate all manufacturing findings files."""
    schema_path = SCHEMA_DIR / "manufacturing_findings_v1.schema.json"

    if not schema_path.exists():
        print(f"Schema not found: {schema_path}")
        return 1

    schema = load_json(schema_path)

    errors: list[str] = []
    documents_validated = 0

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for findings_file in project_dir.glob("*_manufacturing_findings_*.json"):
            print(f"Validating: {findings_file.name}")
            try:
                findings = load_json(findings_file)
                jsonschema.validate(findings, schema)
                documents_validated += 1

            except jsonschema.ValidationError as e:
                errors.append(f"{findings_file.name}: {e.message}")
            except json.JSONDecodeError as e:
                errors.append(f"{findings_file.name}: Invalid JSON - {e}")

    print()
    print(f"Documents validated: {documents_validated}")

    if errors:
        print()
        print("ERRORS:")
        for error in errors:
            print(f"  - {error}")
        print()
        print("RESULT: FAIL")
        return 1

    print()
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
