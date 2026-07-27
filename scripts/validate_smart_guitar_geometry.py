#!/usr/bin/env python3
"""Validate the Smart Guitar component register and derived cavity geometry.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Usage:
    python scripts/validate_smart_guitar_geometry.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail

A cavity that does not fit is reported as a FAIL. An unresolved spec conflict
is reported but does NOT fail: unresolved conflicts are a deliberate output of
this record, and suppressing them would defeat the point.
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

from business.geometry.cavity_derivation import (  # noqa: E402
    as_mm,
    derive_cavity_geometry,
    mm_equal,
)
from business.geometry.loading import load_component_register  # noqa: E402

SCHEMAS = ROOT / "schemas" / "geometry"
REGISTER_SCHEMA = SCHEMAS / "smart_guitar_component_register_v1.schema.json"
GEOMETRY_SCHEMA = SCHEMAS / "smart_guitar_cavity_geometry_v1.schema.json"

FIXTURES = ROOT / "fixtures" / "geometry"
REGISTER = FIXTURES / "smart_guitar_component_register_v1.json"
GEOMETRY = FIXTURES / "smart_guitar_cavity_geometry_v1.json"

# This is a physical record. Commercial and scheduling concepts belong to other
# layers and must not leak in.
FORBIDDEN_KEYS = {
    "cost",
    "unit_cost",
    "price",
    "customer_price",
    "margin",
    "markup",
    "labor_minutes",
    "machine_minutes",
    "runtime_minutes",
    "hourly_rate",
    "machine_hour_rate",
}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _walk(obj: object, path: str = "$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from _walk(value, f"{path}[{idx}]")


def validate_schema(fixture_path: Path, schema_path: Path) -> list[str]:
    errors: list[str] = []
    data = load_json(fixture_path)
    label = fixture_path.name
    try:
        jsonschema.validate(data, load_json(schema_path))
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "$"
        return [f"FAIL {label} schema $.{loc}: {exc.message}"]

    for path, key, _value in _walk(data):
        if key in FORBIDDEN_KEYS:
            errors.append(f"FAIL {label}: forbidden non-geometry field {path}")
    return errors


def validate_derivation() -> list[str]:
    """Recompute the geometry from the register and compare every field."""
    errors: list[str] = []
    stored = load_json(GEOMETRY)
    register_raw = load_json(REGISTER)

    if stored["register_id"] != register_raw["register_id"]:
        errors.append("FAIL register_id mismatch between register and geometry")
    ref = stored["register_ref"]
    if ref.startswith(("/", "\\")) or ".." in Path(ref).parts:
        errors.append(f"FAIL register_ref must be repo-relative without '..': {ref!r}")
    elif not (ROOT / ref).is_file():
        errors.append(f"FAIL missing register_ref: {ref}")
    if errors:
        return errors

    register = load_component_register(REGISTER)
    recomputed = asdict(
        derive_cavity_geometry(
            register,
            geometry_id=stored["geometry_id"],
            register_ref=stored["register_ref"],
            effective_date=stored["calculation"]["effective_date"],
        )
    )

    for key, value in recomputed["body"].items():
        actual = stored["body"].get(key)
        matches = mm_equal(actual, value) if isinstance(value, float) else actual == value
        if not matches:
            errors.append(f"FAIL body.{key}: fixture={actual!r} recomputed={value!r}")

    stored_cavities = {c["cavity_id"]: c for c in stored["cavities"]}
    for cavity in recomputed["cavities"]:
        cid = cavity["cavity_id"]
        if cid not in stored_cavities:
            errors.append(f"FAIL cavity {cid} missing from stored geometry")
            continue
        for key, value in cavity.items():
            actual = stored_cavities[cid].get(key)
            if isinstance(value, float):
                matches = mm_equal(actual, value)
            elif isinstance(value, (list, tuple)):
                matches = list(actual or []) == list(value)
            else:
                matches = actual == value
            if not matches:
                errors.append(
                    f"FAIL cavity {cid}.{key}: fixture={actual!r} recomputed={value!r}"
                )

    extra = set(stored_cavities) - {c["cavity_id"] for c in recomputed["cavities"]}
    if extra:
        errors.append(f"FAIL stored geometry has cavities not in the register: {sorted(extra)}")

    return errors


def validate_fit_and_consistency() -> list[str]:
    """Fit verdicts, internal arithmetic, and conflict propagation."""
    errors: list[str] = []
    stored = load_json(GEOMETRY)
    register_raw = load_json(REGISTER)
    body = stored["body"]

    for cavity in stored["cavities"]:
        cid = cavity["cavity_id"]

        expected_floor = as_mm(
            body["stated_thickness_mm"] - cavity["derived_depth_mm"]
        )
        if not mm_equal(cavity["floor_remaining_mm"], expected_floor):
            errors.append(
                f"FAIL {cid}: floor_remaining {cavity['floor_remaining_mm']} != "
                f"thickness - depth ({expected_floor})"
            )

        expected_fit = cavity["floor_remaining_mm"] >= cavity["min_floor_mm"]
        if cavity["fit_ok"] != expected_fit:
            errors.append(f"FAIL {cid}: fit_ok does not follow from floor vs min_floor")

        # A cavity that does not fit the stated blank is a hard failure.
        if not cavity["fit_ok"]:
            errors.append(
                f"FAIL {cid}: does not fit the stated blank — floor_remaining "
                f"{cavity['floor_remaining_mm']} mm below min_floor "
                f"{cavity['min_floor_mm']} mm"
            )

        # Deltas must be stated minus derived, and a negative delta means the
        # source spec is too small for its own contents.
        for axis in ("length", "width", "depth"):
            stated = cavity[f"stated_{axis}_mm"]
            derived = cavity[f"derived_{axis}_mm"]
            delta = cavity[f"{axis}_delta_mm"]
            if stated is None:
                if delta is not None:
                    errors.append(f"FAIL {cid}: {axis}_delta_mm set without a stated value")
                continue
            if not mm_equal(delta, as_mm(stated - derived)):
                errors.append(
                    f"FAIL {cid}: {axis}_delta_mm {delta} != stated - derived "
                    f"({as_mm(stated - derived)})"
                )
            if delta is not None and delta < 0 and not cavity["findings"]:
                errors.append(
                    f"FAIL {cid}: stated {axis} is smaller than derived but no "
                    f"finding was recorded"
                )

    governing = max(
        stored["cavities"], key=lambda c: c["derived_depth_mm"] + c["min_floor_mm"]
    )
    expected_required = as_mm(
        governing["derived_depth_mm"] + governing["min_floor_mm"]
    )
    if not mm_equal(body["required_thickness_mm"], expected_required):
        errors.append(
            f"FAIL body.required_thickness_mm {body['required_thickness_mm']} != "
            f"max(depth + min_floor) ({expected_required})"
        )
    if body["governing_cavity_id"] != governing["cavity_id"]:
        errors.append("FAIL body.governing_cavity_id is not the deepest-plus-floor cavity")
    if not mm_equal(
        body["margin_mm"],
        as_mm(body["stated_thickness_mm"] - body["required_thickness_mm"]),
    ):
        errors.append("FAIL body.margin_mm != stated - required")
    expected_verdict = "sufficient" if body["margin_mm"] >= 0 else "insufficient"
    if body["verdict"] != expected_verdict:
        errors.append("FAIL body.verdict does not follow from margin_mm")
    if body["verdict"] == "insufficient":
        errors.append(
            f"FAIL stated blank {body['stated_thickness_mm']} mm is thinner than the "
            f"required {body['required_thickness_mm']} mm"
        )

    # Conflicts must propagate verbatim; the derived record is where a reviewer
    # will look, so it must not quietly carry fewer conflicts than the register.
    if stored["conflicts"] != register_raw["conflicts"]:
        errors.append("FAIL conflicts in geometry do not match the register verbatim")

    # Every component the register requires must be placed in some cavity.
    placed = {cid for c in stored["cavities"] for cid in c["component_ids"]}
    required = {c["component_id"] for c in register_raw["components"] if c["required"]}
    missing = required - placed
    if missing:
        errors.append(f"FAIL required components not placed: {sorted(missing)}")

    return errors


def report_unresolved() -> None:
    """Unresolved conflicts are surfaced loudly but do not fail the build."""
    stored = load_json(GEOMETRY)
    unresolved = [c for c in stored["conflicts"] if c["status"] == "unresolved"]
    ruled = [c for c in stored["conflicts"] if c["status"] == "ruled"]
    print(f"\nCONFLICTS: {len(ruled)} ruled, {len(unresolved)} unresolved")
    for conflict in unresolved:
        print(f"  OPEN {conflict['conflict_id']}: {conflict['field']}")
        print(f"       {conflict['ruling']}")


def main() -> int:
    all_errors: list[str] = []

    for fixture, schema in [(REGISTER, REGISTER_SCHEMA), (GEOMETRY, GEOMETRY_SCHEMA)]:
        if not fixture.exists():
            all_errors.append(f"FAIL missing fixture {fixture}")
            continue
        errs = validate_schema(fixture, schema)
        all_errors.extend(errs)
        if not errs:
            print(f"PASS {fixture.relative_to(ROOT).as_posix()}")

    if not all_errors:
        all_errors.extend(validate_derivation())
    if not all_errors:
        all_errors.extend(validate_fit_and_consistency())

    if all_errors:
        for err in all_errors:
            print(err)
        return 1

    print("PASS derivation, fit verdicts, and conflict propagation")
    report_unresolved()
    return 0


if __name__ == "__main__":
    sys.exit(main())
