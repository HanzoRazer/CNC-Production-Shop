"""Release-manifest schema and validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from scripts.release.model import tag_for_version
from scripts.validate_release_manifests import SCHEMA_PATH, load_json, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "releases" / "release_manifest_example_v1.json"
VALIDATOR = ROOT / "scripts" / "validate_release_manifests.py"


def _example() -> dict:
    return load_json(FIXTURE)


def test_example_manifest_validates() -> None:
    schema = load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(_example())
    assert validate_semantics(_example(), FIXTURE) == []


def test_example_is_synthetic_development() -> None:
    manifest = _example()
    assert manifest["example_only"] is True
    assert manifest["release_state"] == "development"
    assert manifest["distribution_name"] == "cnc-production-shop"
    assert manifest["tag"] == ""


def test_unknown_release_state_rejected_by_schema() -> None:
    schema = load_json(SCHEMA_PATH)
    payload = _example()
    payload["release_state"] = "shipped"
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(payload))
    assert errors


def test_artifact_filename_must_match_release_version() -> None:
    payload = _example()
    payload["artifacts"][0]["filename"] = "cnc_production_shop-0.1.0-py3-none-any.whl"
    errors = validate_semantics(payload, FIXTURE)
    assert any("does not match version" in e for e in errors)


def test_duplicate_artifact_entries_rejected() -> None:
    payload = _example()
    payload["artifacts"] = [payload["artifacts"][0], dict(payload["artifacts"][0])]
    errors = validate_semantics(payload, FIXTURE)
    assert any("duplicate artifact" in e for e in errors)


def test_released_state_requires_matching_tag() -> None:
    payload = _example()
    payload["release_state"] = "released"
    payload["tag"] = ""
    errors = validate_semantics(payload, FIXTURE)
    assert any("require tag" in e for e in errors)
    payload["tag"] = tag_for_version(payload["distribution_version"])
    assert validate_semantics(payload, FIXTURE) == []


def test_msme_api_version_may_differ_from_distribution() -> None:
    payload = _example()
    assert payload["distribution_version"] != payload["subsystem_versions"]["MSME_API_VERSION"]
    assert validate_semantics(payload, FIXTURE) == []


def test_schema_versions_are_not_on_the_manifest() -> None:
    schema = load_json(SCHEMA_PATH)
    payload = _example()
    payload["schema_version"] = "1.0"
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(payload))
    assert errors


def test_validator_returns_zero_on_valid_fixture() -> None:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_validator_returns_nonzero_on_invalid_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}\n", encoding="utf-8")
    errors = validate_semantics({"distribution_name": "nope"}, bad)
    assert errors
    schema = load_json(SCHEMA_PATH)
    assert list(jsonschema.Draft202012Validator(schema).iter_errors({}))
    empty = tmp_path / "empty"
    empty.mkdir()
    from scripts import validate_release_manifests as vmod

    monkeypatch.setattr(vmod, "FIXTURES_DIR", empty)
    assert vmod.main() == 1
