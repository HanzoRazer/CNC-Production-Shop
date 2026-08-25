#!/usr/bin/env python3
"""Generate a ReleaseManifestV1 document from already-collected evidence.

Usage:
    python scripts/release/generate_release_manifest.py \\
        --version 0.1.1 \\
        --commit-sha <40 hex> \\
        --wheel path.whl \\
        --sha256 <64 hex> \\
        --notes-ref docs/releases/RELEASE_0.1.1.md \\
        --test-summary "..." \\
        --ci-summary "..." \\
        --output release_manifest_0.1.1.json

Does not consult the network. Does not create tags or mutate pyproject.toml.
Reads source metadata; does not rewrite it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    AUTOMATION_RELEASE_STATES,
    DISTRIBUTION_NAME,
    ReleasePolicyError,
    format_artifact_hash,
    parse_commit_sha,
    parse_created_at,
    parse_distribution_version,
    parse_release_state,
    python_version_label,
    read_assigned_string_constant,
    release_id_for_version,
    sha256_hex,
    tag_for_version,
    version_from_wheel_filename,
    wheel_filename_for_version,
)
from scripts.validate_release_manifests import validate_manifest_document  # noqa: E402


def _msme_api_version(root: Path) -> str:
    init = root / "musical_spatial_mapping" / "__init__.py"
    return read_assigned_string_constant(init.read_text(encoding="utf-8"), "MSME_API_VERSION")


def _resolve_notes_ref(root: Path, notes_ref: str, notes_file: Path | None) -> str:
    if notes_file is not None:
        if not notes_file.is_file():
            raise ReleasePolicyError(f"notes_ref does not exist: {notes_file}")
        return notes_ref
    path_text = notes_ref.split("#", 1)[0]
    if not path_text:
        raise ReleasePolicyError("notes_ref is empty")
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.is_file():
        raise ReleasePolicyError(f"notes_ref does not exist: {notes_ref}")
    return notes_ref


def generate_release_manifest(
    *,
    version: str,
    commit_sha: str,
    wheel: Path,
    sha256_hex_digest: str,
    python_versions: list[str],
    test_summary: str,
    ci_summary: str,
    notes_ref: str,
    root: Path,
    created_at: str,
    release_state: str = "release_candidate",
    tag: str = "",
    example_only: bool = False,
    msme_api_version: str | None = None,
    notes_file: Path | None = None,
) -> dict[str, object]:
    """Build and validate a release-candidate (or synthetic) manifest."""
    parsed = parse_distribution_version(version)
    state = parse_release_state(release_state)
    if not example_only and state not in AUTOMATION_RELEASE_STATES:
        raise ReleasePolicyError(
            f"automation may only emit release_state={sorted(AUTOMATION_RELEASE_STATES)}; "
            f"got {state!r}"
        )
    if not test_summary.strip():
        raise ReleasePolicyError("test_summary is required evidence")
    if not ci_summary.strip():
        raise ReleasePolicyError("ci_summary is required evidence")

    expected_name = wheel_filename_for_version(parsed)
    if version_from_wheel_filename(wheel.name) != parsed or wheel.name != expected_name:
        raise ReleasePolicyError(f"wheel name {wheel.name!r} does not match version {parsed}")
    if not wheel.is_file():
        raise ReleasePolicyError(f"wheel does not exist: {wheel}")
    actual_digest = sha256_hex(wheel.read_bytes())
    if sha256_hex_digest != actual_digest:
        raise ReleasePolicyError("declared SHA-256 does not match the wheel bytes")

    labeled: list[str] = []
    for item in python_versions:
        parts = item.split(".")
        if len(parts) != 2:
            raise ReleasePolicyError(f"malformed Python version {item!r}")
        try:
            labeled.append(python_version_label(int(parts[0]), int(parts[1])))
        except ValueError as exc:
            raise ReleasePolicyError(f"malformed Python version {item!r}") from exc
    if not labeled:
        raise ReleasePolicyError("python_versions is required evidence")

    resolved_notes = _resolve_notes_ref(root, notes_ref, notes_file)
    api = msme_api_version if msme_api_version is not None else _msme_api_version(root)
    if not api:
        raise ReleasePolicyError("MSME_API_VERSION is required evidence")

    if tag and tag != tag_for_version(parsed):
        raise ReleasePolicyError(f"tag {tag!r} does not match version {parsed}")
    if state in {"released", "withdrawn"} and not tag:
        raise ReleasePolicyError(f"{state} manifests require tag {tag_for_version(parsed)}")

    manifest: dict[str, object] = {
        "release_id": release_id_for_version(parsed),
        "distribution_name": DISTRIBUTION_NAME,
        "distribution_version": parsed,
        "release_state": state,
        "commit_sha": parse_commit_sha(commit_sha),
        "tag": tag,
        "created_at": parse_created_at(created_at),
        "python_versions": labeled,
        "artifacts": [
            {
                "filename": expected_name,
                "sha256": format_artifact_hash(actual_digest),
            }
        ],
        "test_summary": test_summary.strip(),
        "ci_summary": ci_summary.strip(),
        "subsystem_versions": {"MSME_API_VERSION": api},
        "notes_ref": resolved_notes,
        "example_only": example_only,
    }
    errors = validate_manifest_document(manifest, Path("<generated>"))
    if errors:
        raise ReleasePolicyError("generated manifest failed validation:\n" + "\n".join(errors))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="64 lowercase hex chars, no prefix")
    parser.add_argument("--python-versions", required=True, help="comma-separated, e.g. 3.11")
    parser.add_argument("--test-summary", required=True)
    parser.add_argument("--ci-summary", required=True)
    parser.add_argument("--notes-ref", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--release-state", default="release_candidate")
    parser.add_argument("--tag", default="")
    parser.add_argument("--example-only", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        versions = [item.strip() for item in args.python_versions.split(",") if item.strip()]
        manifest = generate_release_manifest(
            version=args.version,
            commit_sha=args.commit_sha,
            wheel=args.wheel,
            sha256_hex_digest=args.sha256,
            python_versions=versions,
            test_summary=args.test_summary,
            ci_summary=args.ci_summary,
            notes_ref=args.notes_ref,
            root=args.root.resolve(),
            created_at=args.created_at,
            release_state=args.release_state,
            tag=args.tag,
            example_only=args.example_only,
        )
    except ReleasePolicyError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(manifest, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
