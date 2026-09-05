"""Candidate disposition: blockers are not verification failures.

Pins the run-33336268384 defect: successful verification plus an existing
canonical tag must be BLOCKED with failures == [], never a generic
verification failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release.build_release_candidate import build_release_candidate, main
from scripts.release.candidate_result import (
    EXIT_FAILED,
    EXIT_INVOCATION,
    EXIT_OK,
    aggregate_candidate_results,
    derive_candidate_disposition,
    derive_eligibility_status,
    exit_code_for_disposition,
    format_workflow_summary,
    serialize_candidate_result,
)
from scripts.release.generate_release_evidence import format_compact_summary, render_evidence
from scripts.release.model import (
    FEATURE_PACKAGES,
    RESULT_BLOCKED,
    RESULT_FAILED,
    RESULT_READY,
    tag_for_version,
)
from scripts.release.verify_installed_candidate import InstalledVerification
from scripts.release.verify_release_artifact import ArtifactVerification, verify_release_artifact
from tests.releases.test_release_artifact_verification import make_wheel
from tests.releases.test_release_readiness import (
    _commit_release_tree,
    _init_repo,
    _write_changelog,
    _write_pyproject,
)

ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "scripts" / "release" / "build_release_candidate.py"
WITNESS = ROOT / "tests" / "releases" / "witness_run_33336268384.json"
WITNESS_TAG = "canonical tag v0.1.1 already exists"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _successful_install(version: str) -> InstalledVerification:
    return InstalledVerification(
        ok=True,
        distribution_version=version,
        msme_api_version="0.2.0",
        package_versions={name: version for name in FEATURE_PACKAGES},
        site_packages=True,
        resources_ok=True,
        msme_cli_ok=True,
        cam_assist_ok=True,
    )


def _patch_successful_verification(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    import scripts.release.build_release_candidate as orch

    def fake_build(_root: Path, output_dir: Path, ver: str) -> Path:
        return make_wheel(output_dir, ver)

    monkeypatch.setattr(orch, "build_wheel", fake_build)
    monkeypatch.setattr(
        orch,
        "verify_installed_candidate",
        lambda *_args, **_kwargs: _successful_install(version),
    )


def _run_candidate(
    tmp_path: Path,
    *,
    version: str,
    root: Path,
    test_summary: str = "pytest passed",
    expected_commit: str = "",
    release_state: str = "release_candidate",
) -> dict[str, object]:
    return build_release_candidate(
        version=version,
        root=root,
        output_dir=tmp_path / "dist-release-candidate",
        test_summary=test_summary,
        ci_summary="local-test",
        expected_commit=expected_commit,
        release_state=release_state,
        created_at="2026-09-01T00:00:00Z",
        example_only=True,
    )


# ------------------------------------------------------------------ unit: disposition


def test_no_failures_no_blockers_is_ready_for_tag() -> None:
    assert derive_candidate_disposition([], []) == RESULT_READY


def test_existing_tag_blocker_without_failures_is_blocked() -> None:
    assert derive_candidate_disposition([], [WITNESS_TAG]) == RESULT_BLOCKED


def test_failures_without_blockers_is_failed() -> None:
    assert derive_candidate_disposition(["wheel build failed"], []) == RESULT_FAILED


def test_failures_take_precedence_over_blockers() -> None:
    assert (
        derive_candidate_disposition(
            ["fresh-install verification failed"],
            [WITNESS_TAG],
        )
        == RESULT_FAILED
    )


def test_blocked_has_blockers_and_empty_failures() -> None:
    payload = serialize_candidate_result(
        verification_status="PASS",
        eligibility_status="BLOCKED",
        disposition=RESULT_BLOCKED,
        blockers=[WITNESS_TAG],
        failures=[],
    )
    assert payload["blockers"] == [WITNESS_TAG]
    assert payload["failures"] == []
    assert payload["disposition"] == RESULT_BLOCKED
    assert payload["result"] == payload["disposition"]


def test_failed_has_non_empty_failures() -> None:
    payload = serialize_candidate_result(
        verification_status="FAIL",
        eligibility_status="NOT_EVALUATED",
        disposition=RESULT_FAILED,
        blockers=[],
        failures=["fresh-install verification failed"],
    )
    assert payload["failures"]
    assert payload["disposition"] == RESULT_FAILED
    assert payload["result"] == payload["disposition"]


def test_ready_for_tag_has_neither_blockers_nor_failures() -> None:
    payload = serialize_candidate_result(
        verification_status="PASS",
        eligibility_status="PASS",
        disposition=RESULT_READY,
        blockers=[],
        failures=[],
    )
    assert payload["blockers"] == []
    assert payload["failures"] == []
    assert payload["disposition"] == RESULT_READY
    assert payload["result"] == payload["disposition"]


def test_result_alias_cannot_drift_from_disposition() -> None:
    for disposition in (RESULT_READY, RESULT_BLOCKED, RESULT_FAILED):
        payload = serialize_candidate_result(
            verification_status="PASS" if disposition != RESULT_FAILED else "FAIL",
            eligibility_status="PASS" if disposition == RESULT_READY else "BLOCKED",
            disposition=disposition,
            blockers=[WITNESS_TAG] if disposition != RESULT_READY else [],
            failures=["x"] if disposition == RESULT_FAILED else [],
        )
        assert payload["result"] == payload["disposition"] == disposition


def test_eligibility_not_evaluated_when_unknowable() -> None:
    assert derive_eligibility_status(evaluated=False, blockers=[]) == "NOT_EVALUATED"


def test_eligibility_blocked_when_tag_exists() -> None:
    assert derive_eligibility_status(evaluated=True, blockers=[WITNESS_TAG]) == "BLOCKED"


def test_eligibility_pass_when_evaluated_and_clear() -> None:
    assert derive_eligibility_status(evaluated=True, blockers=[]) == "PASS"


def test_exit_codes_distinguish_blocked_from_failed() -> None:
    assert exit_code_for_disposition(RESULT_READY) == EXIT_OK
    assert exit_code_for_disposition(RESULT_BLOCKED) == EXIT_OK
    assert exit_code_for_disposition(RESULT_FAILED) == EXIT_FAILED
    assert EXIT_OK == 0
    assert EXIT_FAILED == 2
    assert EXIT_INVOCATION == 3


# ------------------------------------------------------------------ witness regression


def test_witness_fixture_pins_run_33336268384_contract() -> None:
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["workflow_run"] == "33336268384"
    assert witness["source_main"] == "18125a09bfc1d1cf9a8470ce32ccd07970e0e9fb"
    assert witness["version"] == "0.1.1"
    assert witness["disposition"] == RESULT_BLOCKED
    assert witness["result"] == witness["disposition"]
    assert witness["verification_status"] == "PASS"
    assert witness["eligibility_status"] == "BLOCKED"
    assert witness["blockers"] == [WITNESS_TAG]
    assert witness["failures"] == []


def test_existing_v0_1_1_with_successful_verification_is_blocked_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 33336268384: verification passed; sole blocker is v0.1.1."""
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    _git(tmp_path, "tag", tag_for_version("0.1.1"))
    _patch_successful_verification(monkeypatch, "0.1.1")

    payload = _run_candidate(tmp_path, version="0.1.1", root=tmp_path)
    out = tmp_path / "dist-release-candidate"

    assert payload["verification_status"] == "PASS"
    assert payload["eligibility_status"] == "BLOCKED"
    assert payload["disposition"] == RESULT_BLOCKED
    assert payload["result"] == payload["disposition"]
    assert payload["failures"] == []
    assert payload["blockers"] == [WITNESS_TAG]
    assert payload["tag_eligibility"] == "FAIL"
    assert payload["wheel_build"] == "PASS"
    assert payload["fresh_install"] == "PASS"
    assert payload["package_parity"] == "PASS"
    assert payload["manifest"] == "PASS"

    wheel_name = "cnc_production_shop-0.1.1-py3-none-any.whl"
    assert (out / wheel_name).is_file()
    assert (out / "SHA256SUMS").is_file()
    assert (out / "release_manifest_0.1.1.json").is_file()
    assert (out / "release_evidence_0.1.1.md").is_file()
    assert (out / "release_evidence_0.1.1.json").is_file()
    assert (out / "release_notes_0.1.1.md").is_file()
    assert (out / "artifact_verification_0.1.1.json").is_file()


def test_blocked_orchestrator_cli_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    _git(tmp_path, "tag", tag_for_version("0.1.1"))
    _patch_successful_verification(monkeypatch, "0.1.1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release_candidate.py",
            "--version",
            "0.1.1",
            "--output-dir",
            str(tmp_path / "cli-out"),
            "--root",
            str(tmp_path),
            "--test-summary",
            "pytest passed",
            "--created-at",
            "2026-09-01T00:00:00Z",
            "--example-only",
        ],
    )
    assert main() == EXIT_OK


# ------------------------------------------------------------------ failures remain hard


def test_wheel_build_failure_is_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.release.build_release_candidate as orch
    from scripts.release.model import ReleasePolicyError

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")

    def explode(*_args: object, **_kwargs: object) -> Path:
        raise ReleasePolicyError("wheel build failed:\nbombed")

    monkeypatch.setattr(orch, "build_wheel", explode)
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_FAILED
    assert payload["verification_status"] == "FAIL"
    assert payload["failures"]
    assert any("wheel build failed" in item for item in payload["failures"])
    assert payload["blockers"] == []
    assert payload["result"] == payload["disposition"]


def test_fresh_install_failure_is_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    monkeypatch.setattr(
        orch, "build_wheel", lambda _r, output_dir, ver: make_wheel(output_dir, ver)
    )
    monkeypatch.setattr(
        orch,
        "verify_installed_candidate",
        lambda *_a, **_k: InstalledVerification(
            ok=False, blockers=["fresh-install verification failed"]
        ),
    )
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_FAILED
    assert any("fresh-install" in item for item in payload["failures"])
    assert payload["blockers"] == []


def test_package_parity_failure_is_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    monkeypatch.setattr(
        orch, "build_wheel", lambda _r, output_dir, ver: make_wheel(output_dir, ver)
    )
    drifted = InstalledVerification(
        ok=True,
        distribution_version="0.1.2",
        msme_api_version="0.2.0",
        package_versions={name: "9.9.9" for name in FEATURE_PACKAGES},
        site_packages=True,
        resources_ok=True,
        msme_cli_ok=True,
        cam_assist_ok=True,
    )
    monkeypatch.setattr(orch, "verify_installed_candidate", lambda *_a, **_k: drifted)
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_FAILED
    assert payload["package_parity"] == "FAIL"
    assert any(
        "package" in item.lower() or "parity" in item.lower() for item in payload["failures"]
    )


def test_invalid_manifest_is_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.release.build_release_candidate as orch
    from scripts.release.model import ReleasePolicyError

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    _patch_successful_verification(monkeypatch, "0.1.2")

    def boom(**_kwargs: object) -> dict[str, object]:
        raise ReleasePolicyError("generated manifest failed validation")

    monkeypatch.setattr(orch, "generate_release_manifest", boom)
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_FAILED
    assert any("manifest" in item for item in payload["failures"])


def test_failures_and_tag_blocker_keep_both_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    _git(tmp_path, "tag", tag_for_version("0.1.1"))
    monkeypatch.setattr(
        orch, "build_wheel", lambda _r, output_dir, ver: make_wheel(output_dir, ver)
    )
    monkeypatch.setattr(
        orch,
        "verify_installed_candidate",
        lambda *_a, **_k: InstalledVerification(
            ok=False, blockers=["fresh-install verification failed"]
        ),
    )
    payload = _run_candidate(tmp_path, version="0.1.1", root=tmp_path)
    assert payload["disposition"] == RESULT_FAILED
    assert payload["verification_status"] == "FAIL"
    assert payload["eligibility_status"] == "BLOCKED"
    assert payload["blockers"] == [WITNESS_TAG]
    assert "fresh-install verification failed" in payload["failures"]
    assert payload["result"] == payload["disposition"]


def test_dirty_tree_is_blocked_not_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    (tmp_path / "dirt").write_text("nope\n", encoding="utf-8")
    _patch_successful_verification(monkeypatch, "0.1.2")
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_BLOCKED
    assert payload["verification_status"] == "PASS"
    assert payload["failures"] == []
    assert any("working tree" in item for item in payload["blockers"])


def test_changelog_not_ready_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_pyproject(tmp_path / "pyproject.toml", "0.1.2")
    _write_changelog(tmp_path / "CHANGELOG.md", "## Unreleased\n\n")
    from tests.releases.test_release_readiness import _plant_source_packages

    _plant_source_packages(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "empty unreleased")
    _patch_successful_verification(monkeypatch, "0.1.2")
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_BLOCKED
    assert payload["failures"] == []
    assert any("changelog" in item for item in payload["blockers"])


# ------------------------------------------------------------------ invocation / config


def test_malformed_version_is_invocation_not_blocked(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR),
            "--version",
            "v0.1.1",
            "--output-dir",
            str(tmp_path / "out"),
            "--test-summary",
            "pytest passed",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == EXIT_INVOCATION
    assert "RESULT: BLOCKED" not in proc.stdout
    assert "READY_FOR_TAG" not in proc.stdout
    assert not list((tmp_path / "out").glob("*.whl")) if (tmp_path / "out").exists() else True


def test_version_mismatch_is_invocation_and_does_not_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    built = {"called": False}

    def should_not_build(*_a: object, **_k: object) -> Path:
        built["called"] = True
        raise AssertionError("wheel build must not run for a version mismatch")

    monkeypatch.setattr(orch, "build_wheel", should_not_build)
    with pytest.raises(Exception, match="does not match authoritative project version"):
        _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert built["called"] is False


def test_expected_commit_mismatch_is_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    monkeypatch.setattr(
        orch,
        "build_wheel",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not build")),
    )
    with pytest.raises(Exception, match="does not match expected_commit"):
        _run_candidate(
            tmp_path,
            version="0.1.1",
            root=tmp_path,
            expected_commit="ab" * 20,
        )


def test_unauthorized_release_state_is_invocation(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    with pytest.raises(Exception, match="release_state"):
        _run_candidate(
            tmp_path,
            version="0.1.1",
            root=tmp_path,
            release_state="released",
        )


def test_malformed_expected_commit_is_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.release.build_release_candidate as orch

    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    monkeypatch.setattr(
        orch,
        "build_wheel",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not build")),
    )
    with pytest.raises(Exception, match="commit_sha"):
        _run_candidate(
            tmp_path,
            version="0.1.1",
            root=tmp_path,
            expected_commit="abc",
        )


# ------------------------------------------------------------------ tags that must not block


def test_historical_witness_tag_does_not_block_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    _git(tmp_path, "tag", "msme-001-foundation-original")
    _patch_successful_verification(monkeypatch, "0.1.2")
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_READY
    assert payload["failures"] == []
    assert payload["blockers"] == []
    assert payload["eligibility_status"] == "PASS"


def test_unrelated_noncanonical_tag_does_not_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    _git(tmp_path, "tag", "docs-preview")
    _patch_successful_verification(monkeypatch, "0.1.2")
    payload = _run_candidate(tmp_path, version="0.1.2", root=tmp_path)
    assert payload["disposition"] == RESULT_READY
    assert payload["blockers"] == []
    assert payload["failures"] == []


# ------------------------------------------------------------------ renderer + workflow aggregation


def test_compact_summary_separates_blockers_and_failures() -> None:
    blocked = format_compact_summary(
        {
            "version": "0.1.1",
            "commit_sha": "a" * 40,
            "version_authority": "PASS",
            "tests": "PASS",
            "wheel_build": "PASS",
            "fresh_install": "PASS",
            "package_parity": "PASS",
            "manifest": "PASS",
            "sha256": "b" * 64,
            "tag_eligibility": "FAIL",
            "verification_status": "PASS",
            "eligibility_status": "BLOCKED",
            "disposition": RESULT_BLOCKED,
            "result": RESULT_BLOCKED,
            "blockers": [WITNESS_TAG],
            "failures": [],
        }
    )
    assert "RESULT: BLOCKED" in blocked
    assert "VERIFICATION: PASS" in blocked
    assert "ELIGIBILITY: BLOCKED" in blocked
    assert WITNESS_TAG in blocked
    assert "verification legs failed" not in blocked.lower()
    failed = format_compact_summary(
        {
            "version": "0.1.2",
            "commit_sha": "a" * 40,
            "version_authority": "PASS",
            "tests": "PASS",
            "wheel_build": "FAIL",
            "fresh_install": "FAIL",
            "package_parity": "FAIL",
            "manifest": "FAIL",
            "sha256": "",
            "tag_eligibility": "PASS",
            "verification_status": "FAIL",
            "eligibility_status": "PASS",
            "disposition": RESULT_FAILED,
            "result": RESULT_FAILED,
            "blockers": [],
            "failures": ["wheel build failed"],
        }
    )
    assert "RESULT: FAILED" in failed
    assert "wheel build failed" in failed
    evidence = render_evidence(
        {
            "result": RESULT_BLOCKED,
            "disposition": RESULT_BLOCKED,
            "verification_status": "PASS",
            "eligibility_status": "BLOCKED",
            "version": "0.1.1",
            "blockers": [WITNESS_TAG],
            "failures": [],
        }
    )
    assert "BLOCKED" in evidence
    assert "must not be tagged" in evidence
    assert WITNESS_TAG in evidence


def test_workflow_summary_blocked_names_blocker_not_verification_failure() -> None:
    payloads = [
        {
            "python_version": "3.11",
            "verification_status": "PASS",
            "eligibility_status": "BLOCKED",
            "disposition": RESULT_BLOCKED,
            "result": RESULT_BLOCKED,
            "blockers": [WITNESS_TAG],
            "failures": [],
        },
        {
            "python_version": "3.12",
            "verification_status": "PASS",
            "eligibility_status": "BLOCKED",
            "disposition": RESULT_BLOCKED,
            "result": RESULT_BLOCKED,
            "blockers": [WITNESS_TAG],
            "failures": [],
        },
    ]
    combined = aggregate_candidate_results(payloads, verify_job_result="success")
    text = format_workflow_summary(combined)
    assert "Python 3.11" in text or "3.11" in text
    assert "PASS" in text
    assert "3.12" in text
    assert "Verification: PASS" in text
    assert "Eligibility: BLOCKED" in text
    assert "RESULT: BLOCKED" in text
    assert WITNESS_TAG in text
    assert "verification legs failed" not in text.lower()
    assert "Failures:" in text
    assert combined["disposition"] == RESULT_BLOCKED
    assert combined["failures"] == []


def test_workflow_summary_failed_names_actual_failure() -> None:
    payloads = [
        {
            "python_version": "3.11",
            "verification_status": "FAIL",
            "eligibility_status": "NOT_EVALUATED",
            "disposition": RESULT_FAILED,
            "result": RESULT_FAILED,
            "blockers": [],
            "failures": ["fresh-install verification failed"],
        }
    ]
    combined = aggregate_candidate_results(payloads, verify_job_result="failure")
    text = format_workflow_summary(combined)
    assert "RESULT: FAILED" in text
    assert "fresh-install verification failed" in text
    assert combined["disposition"] == RESULT_FAILED


def test_workflow_summary_ready_only_without_blockers_or_failures() -> None:
    payloads = [
        {
            "python_version": "3.11",
            "verification_status": "PASS",
            "eligibility_status": "PASS",
            "disposition": RESULT_READY,
            "result": RESULT_READY,
            "blockers": [],
            "failures": [],
        },
        {
            "python_version": "3.12",
            "verification_status": "PASS",
            "eligibility_status": "PASS",
            "disposition": RESULT_READY,
            "result": RESULT_READY,
            "blockers": [],
            "failures": [],
        },
    ]
    combined = aggregate_candidate_results(payloads, verify_job_result="success")
    text = format_workflow_summary(combined)
    assert "RESULT: READY_FOR_TAG" in text
    assert combined["disposition"] == RESULT_READY
    assert combined["blockers"] == []
    assert combined["failures"] == []


def test_missing_evidence_after_job_failure_is_not_eligibility_block() -> None:
    combined = aggregate_candidate_results([], verify_job_result="failure")
    text = format_workflow_summary(combined)
    assert combined["disposition"] == RESULT_FAILED
    assert "RESULT: BLOCKED" not in text
    assert "canonical tag" not in text


def test_artifact_verification_helper_still_classifies_duplicates(
    tmp_path: Path,
) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", duplicate_member=True)
    result: ArtifactVerification = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert result.duplicate_members
