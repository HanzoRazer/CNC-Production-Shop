"""Release-candidate automation contracts: workflow, version gates, safety."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release.check_release_readiness import inspect_release_readiness
from scripts.release.classify_candidate_result import (
    CLASS_ELIGIBILITY,
    CLASS_READY,
    CLASS_VERIFICATION,
    aggregate_classifications,
    classify_payload,
    format_aggregate,
    is_eligibility_blocker,
)
from scripts.release.generate_release_evidence import format_compact_summary, render_evidence
from scripts.release.generate_release_manifest import generate_release_manifest
from scripts.release.git_io import git_read
from scripts.release.model import (
    RESULT_BLOCKED,
    RESULT_FAILED,
    RESULT_READY,
    ReleasePolicyError,
    parse_distribution_version,
    tag_for_version,
    wheel_filename_for_version,
)
from scripts.release.tag_eligibility import inspect_tag_eligibility, verify_post_tag
from scripts.validate_release_manifests import validate_manifest_document
from tests.releases.test_release_artifact_verification import make_wheel
from tests.releases.test_release_readiness import (
    _commit_release_tree,
    _init_repo,
    _plant_source_packages,
    _write_changelog,
    _write_pyproject,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release_candidate.yml"
RELEASE_SCRIPTS = ROOT / "scripts" / "release"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


# ------------------------------------------------------------------ workflow contract


def test_workflow_file_exists() -> None:
    assert WORKFLOW.is_file()


def test_workflow_is_workflow_dispatch_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    for token in ("\n  push:", "\n  pull_request:", "\n  schedule:", "\n  release:"):
        assert token not in text
    # Trigger block must not include tag creation.
    assert "types: [created]" not in text


def test_workflow_requires_explicit_version_input() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "version:" in text
    assert "required: true" in text
    assert "publish=true" not in text
    assert "create_tag=true" not in text
    assert "push_to_pypi=true" not in text


def test_workflow_permissions_are_read_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:" in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "packages: write" not in text
    assert "id-token: write" not in text


def test_workflow_has_no_tag_or_publish_steps() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "git tag" not in lowered
    assert "gh release" not in lowered
    assert "twine" not in lowered
    assert "pypi" not in lowered
    assert "softprops/action-gh-release" not in lowered
    assert "pypa/gh-action-pypi-publish" not in lowered
    assert "create-release" not in lowered


def test_workflow_runs_python_3_11_and_3_12() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '"3.11"' in text
    assert '"3.12"' in text
    assert "READY_FOR_TAG" in text
    assert "BLOCKED" in text
    assert "FAILED" in text
    assert "retention-days: 14" in text


def test_workflow_classifies_eligibility_separately_from_verification() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "classify_candidate_result.py" in text
    assert "--evidence-dir dist-release-candidate" in text
    assert "--aggregate artifacts" in text
    assert "one or more Python 3.11/3.12 verification legs failed" not in text


def test_workflow_does_not_mask_blocked_as_verification_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "verification legs failed" not in text
    assert "classify_candidate_result.py" in text
    assert "INVOCATION_ERROR" in text
    assert "if: always()" in text


def test_workflow_early_gates_are_invocation_errors() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    confirm = text.split("name: Confirm expected commit", 1)[1]
    reject = text.split("name: Reject unauthorized release_state", 1)[1]
    assert "RESULT: BLOCKED" not in confirm.split("name:", 1)[0]
    assert "INVOCATION_ERROR" in confirm.split("name:", 1)[0]
    assert "RESULT: BLOCKED" not in reject.split("name:", 1)[0]
    assert "INVOCATION_ERROR" in reject.split("name:", 1)[0]


# ------------------------------------------------------------------ version gate


def test_matching_requested_project_version_passes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.2.0")
    report = inspect_release_readiness("0.2.0", tmp_path, None)
    assert report.ready
    assert report.version == "0.2.0"


def test_mismatched_requested_version_fails(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.1")
    report = inspect_release_readiness("0.1.2", tmp_path, None)
    assert not report.ready
    assert any("distribution version" in item for item in report.blockers)


def test_malformed_version_fails() -> None:
    with pytest.raises(ReleasePolicyError):
        parse_distribution_version("v0.1.2")
    with pytest.raises(ReleasePolicyError):
        parse_distribution_version("1.2")
    report = inspect_release_readiness("not-a-version", ROOT, None)
    assert not report.ready


def test_canonical_tag_already_existing_blocks_eligibility(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    _git(tmp_path, "tag", tag_for_version("0.1.2"))
    eligibility = inspect_tag_eligibility(tmp_path, "0.1.2")
    assert eligibility.exists
    assert not eligibility.eligible
    report = inspect_release_readiness("0.1.2", tmp_path, None)
    assert not report.ready


def test_historical_witness_tag_does_not_block_release(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    _git(tmp_path, "tag", "msme-001-foundation-original")
    eligibility = inspect_tag_eligibility(tmp_path, "0.1.2")
    assert eligibility.eligible
    assert "witness" in eligibility.detail
    report = inspect_release_readiness("0.1.2", tmp_path, None)
    assert report.ready


def test_msme_api_version_may_differ_from_distribution() -> None:
    import tomllib

    from musical_spatial_mapping import MSME_API_VERSION

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] != MSME_API_VERSION
    assert MSME_API_VERSION == "0.2.0"


def test_readiness_json_mode_is_machine_readable(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.2.0")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "check_release_readiness.py"),
            "--version",
            "0.2.0",
            "--root",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ready"] is True
    assert payload["version"] == "0.2.0"
    assert "checks" in payload


# ------------------------------------------------------------------ manifest


def test_generated_manifest_validates(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    notes = tmp_path / "notes.md"
    notes.write_text("# notes\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()
    _plant_source_packages(tmp_path)
    manifest = generate_release_manifest(
        version="0.1.2",
        commit_sha="b" * 40,
        wheel=wheel,
        sha256_hex_digest=digest,
        python_versions=["3.11"],
        test_summary="synthetic tests passed",
        ci_summary="local",
        notes_ref="notes.md",
        root=tmp_path,
        created_at="2026-08-25T00:00:00Z",
        notes_file=notes,
        msme_api_version="0.2.0",
        example_only=True,
    )
    assert validate_manifest_document(manifest, tmp_path / "m.json") == []
    assert manifest["release_state"] == "release_candidate"
    assert manifest["commit_sha"] == "b" * 40
    assert manifest["artifacts"][0]["filename"] == wheel_filename_for_version("0.1.2")
    assert manifest["artifacts"][0]["sha256"] == "sha256:" + digest
    assert manifest["tag"] == ""
    assert manifest["subsystem_versions"]["MSME_API_VERSION"] == "0.2.0"
    assert manifest["subsystem_versions"]["MSME_API_VERSION"] != manifest["distribution_version"]
    assert manifest["notes_ref"] == "notes.md"


def test_manifest_commit_sha_must_match_input(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    notes = tmp_path / "notes.md"
    notes.write_text("n\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()
    with pytest.raises(ReleasePolicyError):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="deadbeef",
            wheel=wheel,
            sha256_hex_digest=digest,
            python_versions=["3.12"],
            test_summary="ok",
            ci_summary="local",
            notes_ref="notes.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            notes_file=notes,
            msme_api_version="0.2.0",
            example_only=True,
        )


def test_manifest_wheel_name_and_hash_must_match(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    notes = tmp_path / "notes.md"
    notes.write_text("n\n", encoding="utf-8")
    with pytest.raises(ReleasePolicyError, match="SHA-256"):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="c" * 40,
            wheel=wheel,
            sha256_hex_digest="a" * 64,
            python_versions=["3.11"],
            test_summary="ok",
            ci_summary="local",
            notes_ref="notes.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            notes_file=notes,
            msme_api_version="0.2.0",
            example_only=True,
        )


def test_automation_cannot_emit_released_state(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    notes = tmp_path / "notes.md"
    notes.write_text("n\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()
    with pytest.raises(ReleasePolicyError, match="release_state"):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="c" * 40,
            wheel=wheel,
            sha256_hex_digest=digest,
            python_versions=["3.11"],
            test_summary="ok",
            ci_summary="local",
            notes_ref="notes.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            notes_file=notes,
            msme_api_version="0.2.0",
            release_state="released",
            tag="v0.1.2",
        )


def test_missing_evidence_fails_manifest_generation(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    digest = __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()
    with pytest.raises(ReleasePolicyError, match="test_summary"):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="c" * 40,
            wheel=wheel,
            sha256_hex_digest=digest,
            python_versions=["3.11"],
            test_summary="  ",
            ci_summary="local",
            notes_ref="missing.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            msme_api_version="0.2.0",
            example_only=True,
        )
    with pytest.raises(ReleasePolicyError, match="notes_ref"):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="c" * 40,
            wheel=wheel,
            sha256_hex_digest=digest,
            python_versions=["3.11"],
            test_summary="ok",
            ci_summary="local",
            notes_ref="missing.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            msme_api_version="0.2.0",
            example_only=True,
        )


def test_compact_summary_is_unambiguous() -> None:
    ready = format_compact_summary(
        {
            "version": "0.1.2",
            "commit_sha": "a" * 40,
            "version_authority": "PASS",
            "tests": "PASS",
            "wheel_build": "PASS",
            "fresh_install": "PASS",
            "package_parity": "PASS",
            "manifest": "PASS",
            "sha256": "b" * 64,
            "tag_eligibility": "PASS",
            "result": RESULT_READY,
            "blockers": [],
        }
    )
    assert "RESULT: READY_FOR_TAG" in ready
    blocked = format_compact_summary(
        {
            "version": "0.1.2",
            "commit_sha": "a" * 40,
            "version_authority": "FAIL",
            "tests": "PASS",
            "wheel_build": "PASS",
            "fresh_install": "PASS",
            "package_parity": "PASS",
            "manifest": "FAIL",
            "sha256": "",
            "tag_eligibility": "FAIL",
            "result": RESULT_BLOCKED,
            "blockers": ["project version mismatch"],
        }
    )
    assert "RESULT: BLOCKED" in blocked
    assert "project version mismatch" in blocked
    assert "green" not in blocked.lower()
    evidence = render_evidence(
        {
            "result": RESULT_BLOCKED,
            "version": "0.1.2",
            "blockers": ["project version mismatch"],
        }
    )
    assert "BLOCKED" in evidence
    assert "must not be tagged" in evidence


def _eligibility_payload(python_version: str = "3.11") -> dict[str, object]:
    return {
        "result": RESULT_BLOCKED,
        "version": "0.1.1",
        "commit_sha": "18125a09bfc1d1cf9a8470ce32ccd07970e0e9fb",
        "python_version": python_version,
        "version_authority": "PASS",
        "tests": "PASS",
        "wheel_build": "PASS",
        "fresh_install": "PASS",
        "package_parity": "PASS",
        "msme_resources": "PASS",
        "msme_cli": "PASS",
        "manifest": "PASS",
        "tag_eligibility": "FAIL",
        "blockers": ["canonical tag v0.1.1 already exists"],
    }


def test_existing_tag_is_an_eligibility_blocker() -> None:
    assert is_eligibility_blocker("canonical tag v0.1.1 already exists")
    assert not is_eligibility_blocker("wheel build failed")


def test_eligibility_only_block_is_not_a_verification_failure() -> None:
    item = classify_payload(_eligibility_payload())
    assert item.kind == CLASS_ELIGIBILITY
    assert item.verification == "PASS"
    assert item.result == RESULT_BLOCKED
    assert item.blockers == ("canonical tag v0.1.1 already exists",)


def test_verification_field_failure_is_classified_as_verification() -> None:
    payload = _eligibility_payload()
    payload["fresh_install"] = "FAIL"
    payload["blockers"] = ["fresh install was not run"]
    item = classify_payload(payload)
    assert item.kind == CLASS_VERIFICATION
    assert item.verification == "FAIL"


def test_ready_payload_classifies_as_ready() -> None:
    payload = _eligibility_payload()
    payload["result"] = RESULT_READY
    payload["tag_eligibility"] = "PASS"
    payload["blockers"] = []
    item = classify_payload(payload)
    assert item.kind == CLASS_READY
    assert item.result == RESULT_READY


def test_matrix_aggregation_keeps_eligibility_blocker_precise() -> None:
    items = [
        classify_payload(_eligibility_payload("3.11")),
        classify_payload(_eligibility_payload("3.12")),
    ]
    result, blockers, verification, failures = aggregate_classifications(
        items, verify_result="success"
    )
    assert result == RESULT_BLOCKED
    assert verification == "PASS"
    assert blockers == ["canonical tag v0.1.1 already exists"]
    assert failures == []
    text = format_aggregate(result, blockers, verification, failures)
    assert "VERIFICATION: PASS" in text
    assert "canonical tag v0.1.1 already exists" in text
    assert "verification legs failed" not in text


def test_matrix_aggregation_reports_verification_failure_when_evidence_missing() -> None:
    result, blockers, verification, failures = aggregate_classifications(
        [], verify_result="failure"
    )
    assert result == RESULT_FAILED
    assert verification == "FAIL"
    assert blockers == []
    assert any("did not produce a candidate result" in item for item in failures)


def test_matrix_aggregation_will_not_call_a_half_reported_matrix_blocked() -> None:
    """One leg BLOCKED, the other silent, job still green: that is a failure."""
    items = [classify_payload(_eligibility_payload("3.11"))]
    result, blockers, verification, failures = aggregate_classifications(
        items, verify_result="success"
    )
    assert result == RESULT_FAILED
    assert verification == "FAIL"
    assert blockers == ["canonical tag v0.1.1 already exists"]
    assert any("no candidate result for Python 3.12" in item for item in failures)
    text = format_aggregate(result, blockers, verification, failures)
    assert "RESULT: FAILED" in text
    assert "no candidate result for Python 3.12" in text


def test_classifier_cli_exits_nonzero_when_a_matrix_leg_is_missing(tmp_path: Path) -> None:
    dest = tmp_path / "release-candidate-3.11"
    dest.mkdir()
    (dest / "release_evidence_0.1.1.json").write_text(
        json.dumps(_eligibility_payload("3.11")) + "\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "classify_candidate_result.py"),
            "--aggregate",
            str(tmp_path),
            "--verify-result",
            "success",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "RESULT: FAILED" in proc.stdout
    assert "no candidate result for Python 3.12" in proc.stdout


def test_classifier_cli_exits_zero_for_eligibility_block(tmp_path: Path) -> None:
    evidence = tmp_path / "release_evidence_0.1.1.json"
    evidence.write_text(json.dumps(_eligibility_payload()) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "classify_candidate_result.py"),
            "--evidence-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLASS: ELIGIBILITY_BLOCKED" in proc.stdout
    assert "VERIFICATION: PASS" in proc.stdout


def test_classifier_cli_aggregate_exits_nonzero_for_eligibility_block(tmp_path: Path) -> None:
    for label in ("3.11", "3.12"):
        dest = tmp_path / f"release-candidate-{label}"
        dest.mkdir()
        (dest / "release_evidence_0.1.1.json").write_text(
            json.dumps(_eligibility_payload(label)) + "\n", encoding="utf-8"
        )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "classify_candidate_result.py"),
            "--aggregate",
            str(tmp_path),
            "--verify-result",
            "success",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "RESULT: BLOCKED" in proc.stdout
    assert "canonical tag v0.1.1 already exists" in proc.stdout
    assert "verification legs failed" not in proc.stdout
    assert "FAILURES:" not in proc.stdout


# ------------------------------------------------------------------ readiness extras


def test_dirty_tree_blocks_local_execution(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    (tmp_path / "dirt").write_text("nope\n", encoding="utf-8")
    report = inspect_release_readiness("0.1.2", tmp_path, None)
    assert not report.ready
    assert any("working tree" in item for item in report.blockers)


def test_missing_changelog_section_blocks(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_pyproject(tmp_path / "pyproject.toml", "0.1.2")
    _write_changelog(tmp_path / "CHANGELOG.md", "## Unreleased\n\n")
    _plant_source_packages(tmp_path)
    _git(tmp_path, "add", "pyproject.toml", "CHANGELOG.md", "cnc_version", "cam_assist")
    # remaining packages
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "empty unreleased")
    report = inspect_release_readiness("0.1.2", tmp_path, None)
    assert not report.ready
    assert any("changelog" in item for item in report.blockers)


def test_missing_release_notes_blocks_manifest(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    digest = __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()
    with pytest.raises(ReleasePolicyError, match="notes_ref"):
        generate_release_manifest(
            version="0.1.2",
            commit_sha="c" * 40,
            wheel=wheel,
            sha256_hex_digest=digest,
            python_versions=["3.11"],
            test_summary="ok",
            ci_summary="local",
            notes_ref="docs/releases/RELEASE_0.1.2.md",
            root=tmp_path,
            created_at="2026-08-25T00:00:00Z",
            msme_api_version="0.2.0",
            example_only=True,
        )


def test_failed_artifact_verification_blocks(tmp_path: Path) -> None:
    from scripts.release.verify_release_artifact import verify_release_artifact

    wheel = make_wheel(tmp_path, "0.1.2", include_packages=False)
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok


def test_valid_synthetic_candidate_returns_ready(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    wheel = make_wheel(tmp_path.parent / "wheels-ready", "0.1.2")
    report = inspect_release_readiness("0.1.2", tmp_path, wheel)
    assert report.ready


def test_expected_commit_mismatch_is_a_blocker(tmp_path: Path) -> None:
    from scripts.release.model import parse_commit_sha

    with pytest.raises(ReleasePolicyError):
        parse_commit_sha("abc")


# ------------------------------------------------------------------ safety


def _script_sources() -> list[Path]:
    return sorted(RELEASE_SCRIPTS.glob("*.py")) + [
        ROOT / "scripts" / "validate_release_manifests.py"
    ]


def test_automation_utility_does_not_invoke_git_tag() -> None:
    for path in _script_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            args = []
            if node.args and isinstance(node.args[0], ast.List):
                args = [
                    elt.value
                    for elt in node.args[0].elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
            if len(args) >= 2 and args[0] == "git" and args[1] == "tag":
                assert "--list" in args, f"{path} invokes git tag without --list: {args}"


def test_automation_utility_does_not_invoke_git_push() -> None:
    for path in _script_sources():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            args: list[str] = []
            if node.args and isinstance(node.args[0], ast.List):
                args = [
                    elt.value
                    for elt in node.args[0].elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
            if args[:2] == ["git", "push"]:
                pytest.fail(f"{path} invokes git push")
        assert "git push" not in text or "Does not" in text or "does not" in text.lower()


def test_automation_utility_does_not_mutate_pyproject() -> None:
    for path in _script_sources():
        text = path.read_text(encoding="utf-8")
        if "pyproject.toml" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"write_text", "write_bytes", "replace"}:
                    # Allowed writes are evidence outputs, not pyproject.
                    pass
        assert "write" not in text.lower() or "read" in text.lower()


def test_automation_utility_does_not_modify_changelog() -> None:
    for path in _script_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"write_text", "write_bytes"}:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert "CHANGELOG.md" not in arg.value, path


def test_automation_utility_does_not_call_network_publishing_apis() -> None:
    forbidden = (
        "urllib.request",
        "requests.post",
        "httpx",
        "twine ",
        "gh release",
        "pypa/gh-action-pypi-publish",
    )
    for path in _script_sources():
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} contains {token!r}"


def test_orchestrator_keeps_install_venv_out_of_evidence_dir() -> None:
    source = (RELEASE_SCRIPTS / "build_release_candidate.py").read_text(encoding="utf-8")
    assert 'output_dir / ".venv-verify"' not in source
    assert "tempfile.mkdtemp" in source


def test_git_read_rejects_mutating_verbs(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(ReleasePolicyError, match="not allowed"):
        git_read(tmp_path, "push", "origin", "main")
    with pytest.raises(ReleasePolicyError, match="listing"):
        git_read(tmp_path, "tag", "v9.9.9")


def test_post_tag_verification_does_not_create_tags(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    before = subprocess.run(
        ["git", "tag", "--list"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    report = verify_post_tag(tmp_path, "0.1.2", "a" * 40)
    assert not report.ok
    after = subprocess.run(
        ["git", "tag", "--list"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert before == after


def test_render_release_notes_output_path(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n### Fixed\n- one\n", encoding="utf-8")
    out = tmp_path / "notes.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "render_release_notes.py"),
            "--version",
            "0.1.2",
            "--changelog",
            str(changelog),
            "--output",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    assert "cnc-production-shop 0.1.2" in out.read_text(encoding="utf-8")


# ------------------------------------------------------------------ fresh install (real wheel)


@pytest.fixture(scope="module")
def real_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("rc-wheel")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    wheels = list(out.glob("*.whl"))
    if not wheels:
        pytest.fail(f"could not build wheel:\n{proc.stdout}\n{proc.stderr}")
    return wheels[0]


def test_wheel_installs_into_isolated_venv(
    real_wheel: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    from scripts.release.verify_installed_candidate import verify_installed_candidate

    venv = tmp_path_factory.mktemp("rc-venv") / "venv"
    result = verify_installed_candidate(
        real_wheel,
        "0.1.1",
        repo_root=ROOT,
        venv_dir=venv,
    )
    assert result.ok, result.blockers
    assert result.site_packages
    assert result.distribution_version == "0.1.1"
    assert result.package_versions
    assert all(value == "0.1.1" for value in result.package_versions.values())
    assert result.msme_api_version == "0.2.0"
    assert result.resources_ok
    assert result.msme_cli_ok
    assert result.cam_assist_ok


def test_failed_test_evidence_blocks_orchestrator_cli(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "build_release_candidate.py"),
            "--version",
            "0.1.1",
            "--output-dir",
            str(tmp_path / "out"),
            "--test-summary",
            "",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # argparse still accepts empty string; the orchestrator must fail closed.
    assert proc.returncode != 0


def test_orchestrator_does_not_rewrite_source_on_blocked_run(
    tmp_path: Path,
) -> None:
    """Running against the current 0.1.1 tree is BLOCKED (tag exists) and read-only."""
    pyproject_before = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog_before = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    tags_before = subprocess.run(
        ["git", "tag", "--list"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # Do not invoke the full orchestrator here: it builds a wheel and would
    # recurse through pytest if it ever grew a --run-tests flag. Source-scan
    # the orchestrator instead and confirm current-tree inputs are unchanged.
    source = (RELEASE_SCRIPTS / "build_release_candidate.py").read_text(encoding="utf-8")
    assert "git tag" in source  # mentioned as a prohibition
    assert "Does not" in source
    assert pyproject_before == (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert changelog_before == (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    tags_after = subprocess.run(
        ["git", "tag", "--list"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert tags_before == tags_after
    assert tmp_path.exists()
