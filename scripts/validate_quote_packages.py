#!/usr/bin/env python3
"""Validate quote package and revision files against schemas.

Dev Order: CNC-QUOTE-PACKAGE-1

Validates:
1. Quote package files against quote_package_v1.schema.json
2. Quote revision files against quote_revision_v1.schema.json
3. All referenced artifact paths exist
"""

import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "quotes"
PROJECTS_DIR = Path(__file__).parent.parent / "projects"
ROOT_DIR = Path(__file__).parent.parent


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def validate_references(revision: dict, revision_path: Path) -> list[str]:
    """Validate that all referenced paths exist."""
    errors = []

    # Check workbook_ref
    if revision.get("workbook_ref"):
        ref_path = ROOT_DIR / revision["workbook_ref"]
        if not ref_path.exists():
            errors.append(f"workbook_ref not found: {revision['workbook_ref']}")

    # Check option references
    for option in revision.get("options", []):
        for ref_field in ["bid_ref", "bid_summary_ref", "proposal_ref", "markdown_ref"]:
            ref_value = option.get(ref_field)
            if ref_value:
                ref_path = ROOT_DIR / ref_value
                if not ref_path.exists():
                    errors.append(
                        f"Option {option['option_id']}: {ref_field} not found: {ref_value}"
                    )

    return errors


def main() -> int:
    """Validate all quote packages and revisions."""
    package_schema = load_json(SCHEMA_DIR / "quote_package_v1.schema.json")
    revision_schema = load_json(SCHEMA_DIR / "quote_revision_v1.schema.json")

    errors: list[str] = []
    packages_validated = 0
    revisions_validated = 0

    # Find all quote package files
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        # Validate packages
        for package_file in project_dir.glob("*_quote_package_*.json"):
            print(f"Validating package: {package_file.name}")
            try:
                package = load_json(package_file)
                jsonschema.validate(package, package_schema)
                packages_validated += 1
            except jsonschema.ValidationError as e:
                errors.append(f"{package_file.name}: {e.message}")
            except json.JSONDecodeError as e:
                errors.append(f"{package_file.name}: Invalid JSON - {e}")

        # Validate revisions
        for revision_file in project_dir.glob("*_quote_revision_*.json"):
            print(f"Validating revision: {revision_file.name}")
            try:
                revision = load_json(revision_file)
                jsonschema.validate(revision, revision_schema)
                revisions_validated += 1

                # Validate references
                ref_errors = validate_references(revision, revision_file)
                errors.extend(ref_errors)

            except jsonschema.ValidationError as e:
                errors.append(f"{revision_file.name}: {e.message}")
            except json.JSONDecodeError as e:
                errors.append(f"{revision_file.name}: Invalid JSON - {e}")

    # Report results
    print()
    print(f"Packages validated: {packages_validated}")
    print(f"Revisions validated: {revisions_validated}")

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
