#!/usr/bin/env python3
"""Validate quote classification files against schema.

Dev Order: ECO-LOOM-QUOTE-CORRECTION-1

Validates:
1. Quote classification files against quote_classification_v1.schema.json
2. Repo-local paths in applies_to exist (external PDFs are skipped)
"""

import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "quotes"
PROJECTS_DIR = Path(__file__).parent.parent / "projects"
ROOT_DIR = Path(__file__).parent.parent

REPO_PATH_PREFIXES = (
    "projects/",
    "fixtures/",
    "exports/",
    "schemas/",
    "scripts/",
    "tests/",
    "business/",
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def is_repo_path(path_str: str) -> bool:
    """Check if a path is a repo-local path (not external document)."""
    return path_str.startswith(REPO_PATH_PREFIXES)


def validate_applies_to(classification: dict) -> list[str]:
    """Validate that repo-local applies_to paths exist."""
    errors = []

    for ref in classification.get("applies_to", []):
        if is_repo_path(ref):
            ref_path = ROOT_DIR / ref
            if not ref_path.exists():
                errors.append(f"applies_to path not found: {ref}")

    return errors


def main() -> int:
    """Validate all quote classification files."""
    schema_path = SCHEMA_DIR / "quote_classification_v1.schema.json"

    if not schema_path.exists():
        print(f"Schema not found: {schema_path}")
        return 1

    schema = load_json(schema_path)

    errors: list[str] = []
    classifications_validated = 0

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for classification_file in project_dir.glob("*_quote_clarification_*.json"):
            print(f"Validating classification: {classification_file.name}")
            try:
                classification = load_json(classification_file)
                jsonschema.validate(classification, schema)
                classifications_validated += 1

                ref_errors = validate_applies_to(classification)
                errors.extend(ref_errors)

            except jsonschema.ValidationError as e:
                errors.append(f"{classification_file.name}: {e.message}")
            except json.JSONDecodeError as e:
                errors.append(f"{classification_file.name}: Invalid JSON - {e}")

    print()
    print(f"Classifications validated: {classifications_validated}")

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
