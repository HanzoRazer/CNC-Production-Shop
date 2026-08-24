#!/usr/bin/env python3
"""Validate release manifest fixtures against schema and release-policy rules.

Usage:
    python scripts/validate_release_manifests.py

Exit codes:
    0 = all validations pass
    1 = one or more validations fail

Read-only. No network calls. Does not create tags or mutate pyproject.toml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    DISTRIBUTION_NAME,
    ReleasePolicyError,
    parse_artifact_hash,
    parse_commit_sha,
    parse_created_at,
    parse_distribution_version,
    parse_release_id,
    parse_release_state,
    release_id_for_version,
    tag_for_version,
    version_from_wheel_filename,
)

FIXTURES_DIR = ROOT / "fixtures" / "releases"
SCHEMA_PATH = ROOT / "schemas" / "releases" / "release_manifest_v1.schema.json"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} is not a JSON object")
    return data


def validate_semantics(manifest: dict, path: Path) -> list[str]:
    errors: list[str] = []
    try:
        version = parse_distribution_version(str(manifest["distribution_version"]))
        release_id = parse_release_id(str(manifest["release_id"]))
        if release_id != version:
            errors.append(f"{path}: release_id does not match distribution_version")
        if manifest.get("release_id") != release_id_for_version(version):
            errors.append(f"{path}: release_id must be REL-CNC-<version>")
    except (KeyError, ReleasePolicyError) as exc:
        errors.append(f"{path}: {exc}")
        return errors

    if manifest.get("distribution_name") != DISTRIBUTION_NAME:
        errors.append(f"{path}: distribution_name must be {DISTRIBUTION_NAME}")

    try:
        parse_release_state(str(manifest["release_state"]))
    except ReleasePolicyError as exc:
        errors.append(f"{path}: {exc}")

    try:
        parse_commit_sha(str(manifest["commit_sha"]))
    except ReleasePolicyError as exc:
        errors.append(f"{path}: {exc}")

    try:
        parse_created_at(str(manifest["created_at"]))
    except (KeyError, ReleasePolicyError) as exc:
        errors.append(f"{path}: {exc}")

    tag = str(manifest.get("tag", ""))
    state = str(manifest.get("release_state", ""))
    if state in {"released", "withdrawn"}:
        if tag != tag_for_version(version):
            errors.append(f"{path}: {state} manifests require tag {tag_for_version(version)}")
    elif tag and tag != tag_for_version(version):
        errors.append(f"{path}: tag {tag!r} does not match version {version}")

    seen_files: set[str] = set()
    for artifact in manifest.get("artifacts", []):
        filename = str(artifact.get("filename", ""))
        try:
            if version_from_wheel_filename(filename) != version:
                errors.append(f"{path}: artifact {filename} does not match version {version}")
        except ReleasePolicyError as exc:
            errors.append(f"{path}: {exc}")
        try:
            parse_artifact_hash(str(artifact.get("sha256", "")))
        except ReleasePolicyError as exc:
            errors.append(f"{path}: {exc}")
        if filename in seen_files:
            errors.append(f"{path}: duplicate artifact filename {filename}")
        seen_files.add(filename)

    subsystems = manifest.get("subsystem_versions", {})
    if "MSME_API_VERSION" not in subsystems:
        errors.append(f"{path}: subsystem_versions.MSME_API_VERSION is required")
    return errors


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"FAIL missing schema {SCHEMA_PATH}", file=sys.stderr)
        return 1
    schema = load_json(SCHEMA_PATH)
    paths = sorted(FIXTURES_DIR.glob("*.json"))
    if not paths:
        print(f"FAIL no fixtures in {FIXTURES_DIR}", file=sys.stderr)
        return 1
    failed = 0
    for path in paths:
        manifest = load_json(path)
        validator = jsonschema.Draft202012Validator(schema)
        schema_errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
        for err in schema_errors:
            loc = ".".join(str(p) for p in err.path) or "<root>"
            print(f"FAIL {path} schema {loc}: {err.message}")
            failed += 1
        for message in validate_semantics(manifest, path):
            print(f"FAIL {message}")
            failed += 1
        if not schema_errors:
            print(f"PASS {path.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
