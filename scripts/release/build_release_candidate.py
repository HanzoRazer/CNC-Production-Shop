#!/usr/bin/env python3
"""Orchestrate governed release-candidate verification.

Usage:
    python scripts/release/build_release_candidate.py \\
        --version 0.1.1 \\
        --output-dir dist-release-candidate \\
        --test-summary "pytest passed"

Builds a wheel, inspects it, installs it into a fresh venv, writes the
release-candidate manifest and evidence, and prints READY_FOR_TAG, BLOCKED,
or FAILED.

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
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.candidate_result import (  # noqa: E402
    EXIT_FAILED,
    EXIT_INVOCATION,
    ReleaseInvocationError,
    derive_candidate_disposition,
    derive_eligibility_status,
    derive_verification_status,
    exit_code_for_disposition,
    serialize_candidate_result,
)
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


def _authoritative_project_version(root: Path) -> str:
    """Read ``[project].version`` from ``root``. Does not rewrite the file."""
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        version = data["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseInvocationError(f"authoritative project version unreadable: {exc}") from exc
    if not isinstance(version, str):
        raise ReleaseInvocationError("pyproject [project].version is not a string")
    try:
        return parse_distribution_version(version)
    except ReleasePolicyError as exc:
        raise ReleaseInvocationError(str(exc)) from exc


def _as_invocation(exc: ReleasePolicyError) -> ReleaseInvocationError:
    if isinstance(exc, ReleaseInvocationError):
        return exc
    return ReleaseInvocationError(str(exc))


def _is_version_identity_readiness(message: str) -> bool:
    return message.startswith("distribution version from --root") or message.startswith(
        "project distribution version:"
    )


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
    try:
        parsed = parse_distribution_version(version)
    except ReleasePolicyError as exc:
        raise _as_invocation(exc) from exc
    try:
        state = parse_release_state(release_state)
    except ReleasePolicyError as exc:
        raise _as_invocation(exc) from exc
    if state not in AUTOMATION_RELEASE_STATES:
        raise ReleaseInvocationError(
            f"build_release_candidate will not emit release_state={state!r}"
        )
    try:
        python_label = python_version_label(sys.version_info.major, sys.version_info.minor)
    except ReleasePolicyError as exc:
        raise _as_invocation(exc) from exc

    declared = _authoritative_project_version(root)
    if declared != parsed:
        raise ReleaseInvocationError(
            f"requested version {parsed} does not match authoritative project version {declared}"
        )

    commit_sha = ""
    head_error = ""
    try:
        commit_sha = head_commit_sha(root)
    except ReleasePolicyError as exc:
        head_error = str(exc)

    if expected_commit:
        try:
            wanted = parse_commit_sha(expected_commit.lower())
        except ReleasePolicyError as exc:
            raise _as_invocation(exc) from exc
        if head_error:
            raise ReleaseInvocationError(
                f"cannot confirm expected_commit against HEAD: {head_error}"
            )
        if commit_sha != wanted:
            raise ReleaseInvocationError(
                f"HEAD {commit_sha} does not match expected_commit {wanted}"
            )

    blockers: list[str] = []
    failures: list[str] = []
    if not test_summary.strip():
        failures.append("test evidence missing")
    if head_error:
        failures.append(head_error)

    eligibility_evaluated = False
    try:
        eligibility = inspect_tag_eligibility(root, parsed)
        eligibility_evaluated = True
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
        failures.append(f"could not evaluate tag eligibility: {exc}")

    readiness = inspect_release_readiness(parsed, root, None)
    if not readiness.ready:
        for item in readiness.blockers:
            if is_canonical_tag_absent_check_blocker(item, version=parsed):
                # inspect_tag_eligibility is the sole authority for this blocker.
                # Readiness only re-derives it, so a disagreement between the two
                # is an evidence defect, not a policy gate.
                if eligibility_evaluated and eligibility.eligible:
                    failures.append(
                        "readiness and tag eligibility disagree on whether "
                        f"{tag_for_version(parsed)} exists"
                    )
                continue
            if _is_version_identity_readiness(item):
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
        if tests_ok:
            output_dir.mkdir(parents=True, exist_ok=True)
            wheel = build_wheel(root, output_dir, parsed)
            artifact = verify_release_artifact(wheel, parsed)
            if not artifact.ok:
                failures.extend(artifact.blockers)
            else:
                installed = verify_installed_candidate(
                    wheel,
                    parsed,
                    repo_root=root,
                    venv_dir=verify_venv,
                )
                if not installed.ok:
                    failures.extend(installed.blockers)
                else:
                    drifted = installed.distribution_version != parsed or any(
                        value != parsed for value in installed.package_versions.values()
                    )
                    if drifted:
                        failures.append("package-version drift")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
    except ReleasePolicyError as exc:
        failures.append(str(exc))
        output_dir.mkdir(parents=True, exist_ok=True)
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
            failures.append(str(exc))
            manifest_ok = False
    else:
        failures.append("manifest not generated because artifact or commit evidence is incomplete")

    unique_blockers = list(dict.fromkeys(blockers))
    unique_failures = list(dict.fromkeys(failures))
    disposition = derive_candidate_disposition(unique_failures, unique_blockers)
    if disposition == RESULT_READY and not (
        artifact.ok
        and installed.ok
        and manifest_ok
        and eligibility_evaluated
        and eligibility.eligible
        and tests_ok
    ):
        unique_failures.append("internal gate aggregation failed closed")
        unique_failures = list(dict.fromkeys(unique_failures))
        disposition = derive_candidate_disposition(unique_failures, unique_blockers)

    verification_status = derive_verification_status(unique_failures)
    eligibility_status = derive_eligibility_status(
        evaluated=eligibility_evaluated,
        blockers=unique_blockers,
    )
    semantic = serialize_candidate_result(
        verification_status=verification_status,
        eligibility_status=eligibility_status,
        disposition=disposition,
        blockers=unique_blockers,
        failures=unique_failures,
    )

    if wheel is not None and artifact.sha256:
        (output_dir / "SHA256SUMS").write_text(
            format_sha256sums_line(wheel.name, artifact.sha256),
            encoding="utf-8",
        )
    (output_dir / f"artifact_verification_{parsed}.json").write_text(
        json.dumps(verification_to_json(artifact), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    package_parity_ok = (
        installed.ok
        and installed.distribution_version == parsed
        and bool(installed.package_versions)
        and all(value == parsed for value in installed.package_versions.values())
    )
    evidence_payload: dict[str, object] = {
        "result": semantic["result"],
        "disposition": semantic["disposition"],
        "verification_status": semantic["verification_status"],
        "eligibility_status": semantic["eligibility_status"],
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
        "package_parity": _pass_fail(package_parity_ok),
        "msme_resources": _pass_fail(artifact.resources_present and installed.resources_ok),
        "msme_cli": _pass_fail(installed.msme_cli_ok),
        "msme_api_version": installed.msme_api_version,
        "manifest": _pass_fail(manifest_ok),
        "canonical_tag": tag_for_version(parsed),
        "tag_eligibility": _pass_fail(eligibility_evaluated and eligibility.eligible),
        "blockers": semantic["blockers"],
        "failures": semantic["failures"],
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
    except ReleaseInvocationError as exc:
        sys.stderr.write(f"FAIL {exc}\n")
        sys.stdout.write(f"RESULT: INVOCATION_ERROR\n- {exc}\n")
        return EXIT_INVOCATION
    except ReleasePolicyError as exc:
        sys.stderr.write(f"FAIL {exc}\n")
        sys.stdout.write(f"RESULT: FAILED\nFAILURES:\n- {exc}\n")
        return EXIT_FAILED
    sys.stdout.write(format_compact_summary(payload))
    return exit_code_for_disposition(str(payload.get("disposition") or payload.get("result") or ""))


if __name__ == "__main__":
    raise SystemExit(main())
