"""Execution invariants for the first governed 0.1.1 release."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.release.model import (
    parse_artifact_hash,
    parse_distribution_version,
    parse_release_id,
    release_id_for_version,
    tag_for_version,
    wheel_filename_for_version,
)
from scripts.validate_release_manifests import SCHEMA_PATH, load_json, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.1"
MANIFEST = ROOT / "fixtures" / "releases" / "release_manifest_0.1.1.json"
NOTES = ROOT / "docs" / "releases" / "RELEASE_0.1.1.md"
EVIDENCE = ROOT / "docs" / "releases" / "RELEASE_EVIDENCE_0.1.1.md"
SUMS = ROOT / "dist-release" / "SHA256SUMS"


def test_approved_version_is_semver() -> None:
    assert parse_distribution_version(VERSION) == VERSION
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == VERSION


def test_changelog_and_notes_identify_0_1_1() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = NOTES.read_text(encoding="utf-8")
    assert "## Unreleased" in changelog
    assert "## [0.1.1] - 2026-08-24" in changelog
    assert "## [0.1.0]" not in changelog
    assert "cnc-production-shop 0.1.1" in notes
    assert "REL-CNC-0.1.1" in notes
    assert NOTES.is_file()
    assert EVIDENCE.is_file()


def test_release_manifest_matches_approved_version() -> None:
    import jsonschema

    manifest = load_json(MANIFEST)
    jsonschema.Draft202012Validator(load_json(SCHEMA_PATH)).validate(manifest)
    assert validate_semantics(manifest, MANIFEST) == []
    assert manifest["example_only"] is False
    assert manifest["distribution_version"] == VERSION
    assert parse_release_id(manifest["release_id"]) == VERSION
    assert manifest["release_id"] == release_id_for_version(VERSION)
    assert manifest["release_state"] in {"release_candidate", "released"}
    assert manifest["subsystem_versions"]["MSME_API_VERSION"] == "0.2.0"
    filename = manifest["artifacts"][0]["filename"]
    assert filename == wheel_filename_for_version(VERSION)
    digest = parse_artifact_hash(manifest["artifacts"][0]["sha256"])
    if manifest["release_state"] == "released":
        assert manifest["tag"] == tag_for_version(VERSION)
    else:
        assert manifest["tag"] == ""
    sums = SUMS.read_text(encoding="utf-8").strip()
    hex_digest = digest.removeprefix("sha256:")
    assert hex_digest in sums
    assert filename in sums


def test_wheel_bytes_are_not_committed() -> None:
    assert _git_tracked_release_wheels() == []


def _git_tracked_release_wheels() -> list[str]:
    import subprocess

    proc = subprocess.run(
        ["git", "ls-files", "dist-release/*.whl"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line]
