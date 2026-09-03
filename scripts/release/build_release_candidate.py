#!/usr/bin/env python3
"""Orchestrate governed release-candidate verification.

Usage:
    python scripts/release/build_release_candidate.py \\
        --version 0.1.1 \\
        --output-dir dist-release-candidate \\
        --test-summary "pytest passed"

Builds a wheel, inspects it, installs it into a fresh venv, writes the
release-candidate manifest and evidence, and prints READY_FOR_TAG or BLOCKED.

Does not:
    choose a version
    edit pyproject.toml
    edit CHANGELOG.md
    git commit
    git tag
    git push
    publish

Reads the source tree. Does not rewrite it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.check_release_readiness import inspect_release_readiness  # noqa: E402
from scripts.release.generate_release_evidence import (  # noqa: E402
    format_compact_summary,
    render_evidence,
)
from scripts.release.generate_release_manifest import generate_release_manifest  # noqa: E402
from scripts.release.git_io import head_commit_sha  # noqa: E402
from scripts.release.model import (  # noqa: E402
    AUTOMATION_RELEASE_STATES,
    DISTRIBUTION_NAME,
    RESULT_BLOCKED,
    RESULT_READY,
    ReleasePolicyError,
    format_sha256sums_line,
    parse_commit_sha,
    parse_distribution_version,
    parse_release_state,
    python_version_label,
    release_id_for_version,
    tag_for_version,
    wheel_filename_for_version,
)
from scripts.release.render_release_notes import render  # noqa: E402
from scripts.release.tag_eligibility import (  # noqa: E402
    TagEligibility,
    inspect_tag_eligibility,
    is_canonical_tag_absent_check_blocker,
)
from scripts.release.verify_installed_candidate import (  # noqa: E402
    InstalledVerification,
    verify_installed_candidate,
)
from scripts.release.verify_release_artifact import (  # noqa: E402
    ArtifactVerification,
    verification_to_json,
    verify_release_artifact,
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def build_wheel(root: Path, output_dir: Path, version: str) -> Path:
    """Build the installable wheel into ``output_dir`` using ``pip wheel``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / ".wheel-build"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "-w", str(staging)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
    )
    wheels = list(staging.glob("*.whl"))
    expected = wheel_filename_for_version(version)
    if proc.returncode != 0 or not wheels:
        detail = (proc.stdout + proc.stderr)[-1500:]
        raise ReleasePolicyError(f"wheel build failed:\n{detail}")
    built = wheels[0]
    if built.name != expected:
        raise ReleasePolicyError(f"built wheel {built.name!r} is not {expected!r}")
    destination = output_dir / expected
    shutil.copy2(built, destination)
    shutil.rmtree(staging)
    return destination


def _existing_notes_ref(root: Path, version: str) -> str | None:
    committed = root / "docs" / "releases" / f"RELEASE_{version}.md"
    if committed.is_file():
        return f"docs/releases/RELEASE_{version}.md"
    return None


def build_release_candidate(
    *,
    version: str,
    root: Path,
    output_dir: Path,
    test_summary: str,
    ci_summary: str,
    expected_commit: str = "",
    release_state: str = "release_candidate",
    created_at: str | None = None,
    example_only: bool = False,
) -> dict[str, object]:
    """Run the candidate pipeline and write evidence under ``output_dir``."""
    blockers: list[str] = []
    parsed = parse_distribution_version(version)
    state = parse_release_state(release_state)
    if state not in AUTOMATION_RELEASE_STATES:
        raise ReleasePolicyError(f"build_release_candidate will not emit release_state={state!r}")
    if not test_summary.strip():
        blockers.append("test evidence missing")

    try:
        commit_sha = head_commit_sha(root)
    except ReleasePolicyError as exc:
        commit_sha = ""
        blockers.append(str(exc))

    if expected_commit:
        try:
            wanted = parse_commit_sha(expected_commit.lower())
            if commit_sha and commit_sha != wanted:
                blockers.append(f"HEAD {commit_sha} does not match expected_commit {wanted}")
        except ReleasePolicyError as exc:
            blockers.append(str(exc))

    python_label = python_version_label(sys.version_info.major, sys.version_info.minor)
    try:
        eligibility = inspect_tag_eligibility(root, parsed)
        if not eligibility.eligible:
            blockers.append(eligibility.detail)
    except ReleasePolicyError as exc:
        eligibility = TagEligibility(
            version=parsed,
            canonical_tag=tag_for_version(parsed),
            exists=False,
            eligible=False,
            detail=str(exc),
        )
        blockers.append(str(exc))

    readiness = inspect_release_readiness(parsed, root, None)
    if not readiness.ready:
        for item in readiness.blockers:
            if (
                is_canonical_tag_absent_check_blocker(item, version=parsed)
                and not eligibility.eligible
            ):
                continue
            blockers.append(item)

    version_authority_ok = all(
        item.ok
        for item in readiness.checks
        if item.message.startswith("distribution version")
        or item.message.startswith("package __version__")
        or item.message.startswith("feature packages")
        or item.message.startswith("cnc_version")
    )

    wheel: Path | None = None
    artifact = ArtifactVerification(
        distribution=DISTRIBUTION_NAME,
        version=parsed,
        wheel="",
        sha256="",
        ok=False,
        blockers=["wheel was not built"],
    )
    installed = InstalledVerification(ok=False, blockers=["fresh install was not run"])
    tests_ok = bool(test_summary.strip())
    verify_venv = Path(tempfile.mkdtemp(prefix="cnc-rc-install-"))
    try:
        if not tests_ok:
            raise ReleasePolicyError("test evidence missing; refusing to build a candidate wheel")
        wheel = build_wheel(root, output_dir, parsed)
        artifact = verify_release_artifact(wheel, parsed)
        if not artifact.ok:
            blockers.extend(artifact.blockers)
        else:
            installed = verify_installed_candidate(
                wheel,
                parsed,
                repo_root=root,
                venv_dir=verify_venv,
            )
            if not installed.ok:
                blockers.extend(installed.blockers)
    except ReleasePolicyError as exc:
        blockers.append(str(exc))
    finally:
        shutil.rmtree(verify_venv, ignore_errors=True)

    notes_preview = output_dir / f"release_notes_{parsed}.md"
    changelog_text = (
        (root / "CHANGELOG.md").read_text(encoding="utf-8")
        if (root / "CHANGELOG.md").is_file()
        else ""
    )
    notes_preview.write_text(
        render(parsed, changelog_text=changelog_text, manifest=None, date=None),
        encoding="utf-8",
    )
    committed_notes = _existing_notes_ref(root, parsed)
    if committed_notes is not None:
        notes_ref = committed_notes
        notes_file = root / committed_notes
    else:
        notes_ref = notes_preview.name
        notes_file = notes_preview

    manifest: dict[str, object] | None = None
    manifest_ok = False
    timestamp = created_at or _utc_now()
    if wheel is not None and artifact.ok and artifact.sha256 and commit_sha:
        try:
            manifest = generate_release_manifest(
                version=parsed,
                commit_sha=commit_sha,
                wheel=wheel,
                sha256_hex_digest=artifact.sha256,
                python_versions=[python_label],
                test_summary=test_summary or "test evidence missing",
                ci_summary=ci_summary,
                notes_ref=notes_ref,
                root=root,
                created_at=timestamp,
                release_state=state,
                tag="",
                example_only=example_only,
                msme_api_version=installed.msme_api_version or None,
                notes_file=notes_file,
            )
            manifest_path = output_dir / f"release_manifest_{parsed}.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            manifest_ok = True
        except ReleasePolicyError as exc:
            blockers.append(str(exc))
            manifest_ok = False
    else:
        blockers.append("manifest not generated because artifact or commit evidence is incomplete")

    unique_blockers: list[str] = []
    for item in blockers:
        if item not in unique_blockers:
            unique_blockers.append(item)

    result = RESULT_READY if not unique_blockers else RESULT_BLOCKED
    if result == RESULT_READY and not (
        artifact.ok and installed.ok and manifest_ok and eligibility.eligible and tests_ok
    ):
        result = RESULT_BLOCKED
        unique_blockers.append("internal gate aggregation failed closed")

    if wheel is not None and artifact.sha256:
        (output_dir / "SHA256SUMS").write_text(
            format_sha256sums_line(wheel.name, artifact.sha256),
            encoding="utf-8",
        )
    (output_dir / f"artifact_verification_{parsed}.json").write_text(
        json.dumps(verification_to_json(artifact), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    evidence_payload: dict[str, object] = {
        "result": result,
        "distribution": DISTRIBUTION_NAME,
        "version": parsed,
        "release_id": release_id_for_version(parsed),
        "release_state": state,
        "commit_sha": commit_sha,
        "python_version": python_label,
        "workflow_run": ci_summary,
        "test_summary": test_summary,
        "ci_summary": ci_summary,
        "wheel": artifact.wheel,
        "sha256": artifact.sha256,
        "duplicate_members": list(artifact.duplicate_members),
        "version_authority": _pass_fail(version_authority_ok),
        "tests": _pass_fail(tests_ok),
        "wheel_build": _pass_fail(wheel is not None and artifact.ok),
        "fresh_install": _pass_fail(installed.ok),
        "package_parity": _pass_fail(
            installed.ok
            and installed.distribution_version == parsed
            and all(value == parsed for value in installed.package_versions.values())
        ),
        "msme_resources": _pass_fail(artifact.resources_present and installed.resources_ok),
        "msme_cli": _pass_fail(installed.msme_cli_ok),
        "msme_api_version": installed.msme_api_version,
        "manifest": _pass_fail(manifest_ok),
        "canonical_tag": tag_for_version(parsed),
        "tag_eligibility": _pass_fail(eligibility.eligible),
        "blockers": unique_blockers,
    }
    (output_dir / f"release_evidence_{parsed}.md").write_text(
        render_evidence(evidence_payload),
        encoding="utf-8",
    )
    (output_dir / f"release_evidence_{parsed}.json").write_text(
        json.dumps(evidence_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--test-summary",
        required=True,
        help="evidence that tests already ran; this utility does not invoke pytest",
    )
    parser.add_argument(
        "--ci-summary",
        default="local",
        help="CI run identity or 'local'",
    )
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--release-state", default="release_candidate")
    parser.add_argument("--created-at", default=None)
    parser.add_argument("--example-only", action="store_true")
    args = parser.parse_args()
    try:
        payload = build_release_candidate(
            version=args.version,
            root=args.root.resolve(),
            output_dir=args.output_dir.resolve(),
            test_summary=args.test_summary,
            ci_summary=args.ci_summary,
            expected_commit=args.expected_commit,
            release_state=args.release_state,
            created_at=args.created_at,
            example_only=args.example_only,
        )
    except ReleasePolicyError as exc:
        sys.stderr.write(f"FAIL {exc}\n")
        sys.stdout.write(f"RESULT: {RESULT_BLOCKED}\nBLOCKERS:\n- {exc}\n")
        return 1
    sys.stdout.write(format_compact_summary(payload))
    return 0 if payload.get("result") == RESULT_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
