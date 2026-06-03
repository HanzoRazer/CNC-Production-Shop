"""Validate Eco-Loom manufacturing fixtures against their JSON schemas.

Dev Order: ECOLOOM-GOVERNANCE-1

This is the executable governance layer for ECOLOOM-MFG-READINESS-1. It checks
that the manufacturing fixtures exist, parse as JSON, and conform to their
draft-2020-12 schemas (required fields present, numeric bounds respected,
unknown keys rejected). It is structure validation only -- it does not compute
quotes or bridge into the cost engine.

Usage:
    # Validate both known Eco-Loom fixtures against their schemas:
    python scripts/validate_eco_loom_fixture.py

    # Validate a single fixture against a single schema:
    python scripts/validate_eco_loom_fixture.py --fixture FIXTURE --schema SCHEMA

The CLI prints a clear PASS/FAIL line per fixture and exits non-zero if any
fixture fails, so it can gate CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
from jsonschema import Draft202012Validator

# ---------------------------------------------------------------------------
# Repository locations
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas" / "eco_loom"
FIXTURE_DIR = REPO_ROOT / "fixtures" / "eco_loom"

# (fixture filename, schema filename) pairs validated by the no-argument CLI.
ECO_LOOM_PAIRS: list[tuple[str, str]] = [
    ("eco_loom_cost_inputs_v1.json", "cost_inputs_v1.schema.json"),
    ("eco_loom_manufacturing_fixture_v1.json", "manufacturing_fixture_v1.schema.json"),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one fixture against one schema.

    Attributes:
        label: Human-readable identifier for the validated fixture.
        ok: True if the instance conforms to the schema.
        errors: Sorted, human-readable validation error messages (empty if ok).
    """

    label: str
    ok: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core validation helpers (importable by tests)
# ---------------------------------------------------------------------------


def load_json(path: Path) -> Any:
    """Load and parse a JSON file.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_schema(schema_filename: str) -> dict[str, Any]:
    """Load an Eco-Loom schema by filename from schemas/eco_loom/."""
    schema: dict[str, Any] = load_json(SCHEMA_DIR / schema_filename)
    return schema


def validate_instance(
    instance: Any, schema: dict[str, Any], label: str = "instance"
) -> ValidationResult:
    """Validate an in-memory instance against a JSON schema.

    Structure validation only: required fields, types, numeric bounds, and
    (because the schemas set additionalProperties=false) unknown keys.

    Args:
        instance: The parsed JSON value to validate.
        schema: A JSON Schema (draft 2020-12) dict.
        label: Identifier used in the result and messages.

    Returns:
        A ValidationResult with ok and any error messages.
    """
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    messages = [_format_error(err) for err in errors]
    return ValidationResult(label=label, ok=not messages, errors=messages)


def validate_file(fixture_path: Path, schema_path: Path) -> ValidationResult:
    """Validate a fixture file on disk against a schema file on disk.

    Confirms the fixture exists and parses before checking conformance. A
    missing file or JSON parse error is reported as a failing result rather
    than raised, so the CLI can report it cleanly.
    """
    label = fixture_path.name
    if not fixture_path.exists():
        return ValidationResult(
            label=label, ok=False, errors=[f"fixture not found: {fixture_path}"]
        )
    try:
        instance = load_json(fixture_path)
    except json.JSONDecodeError as exc:
        return ValidationResult(label=label, ok=False, errors=[f"invalid JSON: {exc}"])
    schema = load_json(schema_path)
    return validate_instance(instance, schema, label=label)


def validate_eco_loom_pairs() -> list[ValidationResult]:
    """Validate every known Eco-Loom (fixture, schema) pair."""
    return [
        validate_file(FIXTURE_DIR / fixture_name, SCHEMA_DIR / schema_name)
        for fixture_name, schema_name in ECO_LOOM_PAIRS
    ]


def _format_error(error: Any) -> str:
    """Render a jsonschema ValidationError as a concise one-line message."""
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _report(results: list[ValidationResult]) -> bool:
    """Print PASS/FAIL for each result. Returns True if all passed."""
    all_ok = True
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        click.echo(f"[{status}] {result.label}")
        if not result.ok:
            all_ok = False
            for message in result.errors:
                click.echo(f"        - {message}")
    click.echo("")
    click.echo("RESULT: PASS" if all_ok else "RESULT: FAIL")
    return all_ok


@click.command()
@click.option(
    "--fixture",
    "fixture",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a single fixture JSON file (requires --schema).",
)
@click.option(
    "--schema",
    "schema",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a single schema JSON file (requires --fixture).",
)
def main(fixture: Path | None, schema: Path | None) -> None:
    """Validate Eco-Loom manufacturing fixtures against their JSON schemas."""
    if (fixture is None) != (schema is None):
        raise click.UsageError("--fixture and --schema must be provided together.")

    if fixture is not None and schema is not None:
        results = [validate_file(fixture, schema)]
    else:
        results = validate_eco_loom_pairs()

    all_ok = _report(results)
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
