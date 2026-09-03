"""Classifier contracts for eligibility vs verification, including real artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.release.classify_candidate_result import (
    CLASS_ELIGIBILITY,
    CLASS_READY,
    CLASS_VERIFICATION,
    aggregate_classifications,
    classify_payload,
    format_aggregate,
    is_eligibility_blocker,
    load_aggregate_payloads,
)
from scripts.release.model import RESULT_BLOCKED, RESULT_READY
from scripts.release.tag_eligibility import (
    ELIGIBILITY_BLOCKER_KINDS,
    EXISTING_CANONICAL_TAG_KIND,
    NON_ELIGIBILITY_POLICY_KINDS,
    canonical_tag_absent_check_message,
    eligibility_blocker_kind,
    existing_canonical_tag_blocker,
    inspect_tag_eligibility,
    is_canonical_tag_absent_check_blocker,
    policy_blocker_kind,
)
from tests.releases.test_release_automation import _eligibility_payload
from tests.releases.test_release_readiness import _commit_release_tree, _init_repo

ROOT = Path(__file__).resolve().parents[2]
CLOSEOUT_ARTIFACTS = ROOT / "tests" / "releases" / "fixtures" / "closeout_33336268384" / "artifacts"
CLASSIFIER = ROOT / "scripts" / "release" / "classify_candidate_result.py"


def _run_classifier(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLASSIFIER), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_eligibility_catalog_has_only_existing_canonical_tag() -> None:
    assert EXISTING_CANONICAL_TAG_KIND in ELIGIBILITY_BLOCKER_KINDS
    assert ELIGIBILITY_BLOCKER_KINDS == frozenset({EXISTING_CANONICAL_TAG_KIND})
    assert EXISTING_CANONICAL_TAG_KIND not in NON_ELIGIBILITY_POLICY_KINDS
    assert "canonical_tag_absent_check" in NON_ELIGIBILITY_POLICY_KINDS
    assert "dirty_working_tree" in NON_ELIGIBILITY_POLICY_KINDS
    assert "missing_changelog" in NON_ELIGIBILITY_POLICY_KINDS
    assert "changelog_unready" in NON_ELIGIBILITY_POLICY_KINDS
    assert "missing_git_metadata" in NON_ELIGIBILITY_POLICY_KINDS
    assert "expected_commit_mismatch" in NON_ELIGIBILITY_POLICY_KINDS
    assert "tag_inspection_error" in NON_ELIGIBILITY_POLICY_KINDS


def test_existing_tag_blocker_is_generated_not_improvised() -> None:
    assert existing_canonical_tag_blocker("0.1.1") == "canonical tag v0.1.1 already exists"
    assert eligibility_blocker_kind(existing_canonical_tag_blocker("0.1.1")) == (
        EXISTING_CANONICAL_TAG_KIND
    )


def test_inspect_tag_eligibility_emits_catalog_blocker(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    subprocess.run(["git", "tag", "v0.1.2"], cwd=tmp_path, check=True, capture_output=True)
    eligibility = inspect_tag_eligibility(tmp_path, "0.1.2")
    assert eligibility.detail == existing_canonical_tag_blocker("0.1.2")
    assert is_eligibility_blocker(eligibility.detail, version="0.1.2", canonical_tag="v0.1.2")


def test_readiness_absent_check_is_not_eligibility() -> None:
    message = canonical_tag_absent_check_message("0.1.1")
    assert message == "canonical tag v0.1.1 does not exist"
    assert is_canonical_tag_absent_check_blocker(message, version="0.1.1")
    assert eligibility_blocker_kind(message) is None
    assert policy_blocker_kind(message) == "canonical_tag_absent_check"
    assert policy_blocker_kind("working tree clean") == "dirty_working_tree"
    assert policy_blocker_kind("CHANGELOG.md exists") == "missing_changelog"
    assert (
        policy_blocker_kind("changelog has a 0.1.1 section or release-ready Unreleased material")
        == "changelog_unready"
    )
    assert policy_blocker_kind("git metadata present at --root") == "missing_git_metadata"
    assert (
        policy_blocker_kind("HEAD abc does not match expected_commit def")
        == "expected_commit_mismatch"
    )
    assert policy_blocker_kind("wheel build failed") is None


def test_known_policy_blockers_are_not_classified_as_eligibility() -> None:
    payload = _eligibility_payload()
    for blocker, kind in (
        ("working tree clean", "dirty_working_tree"),
        ("CHANGELOG.md exists", "missing_changelog"),
        (
            "changelog has a 0.1.1 section or release-ready Unreleased material",
            "changelog_unready",
        ),
        ("git metadata present at --root", "missing_git_metadata"),
        (
            "HEAD 18125a09bfc1d1cf9a8470ce32ccd07970e0e9fb does not match "
            "expected_commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "expected_commit_mismatch",
        ),
        (canonical_tag_absent_check_message("0.1.1"), "canonical_tag_absent_check"),
    ):
        payload["blockers"] = [blocker]
        item = classify_payload(payload)
        assert policy_blocker_kind(blocker) == kind
        assert item.kind == CLASS_VERIFICATION
        assert kind not in ELIGIBILITY_BLOCKER_KINDS


def test_inconsistent_tag_eligibility_field_is_not_eligibility() -> None:
    payload = _eligibility_payload()
    payload["tag_eligibility"] = "PASS"
    item = classify_payload(payload)
    assert item.kind == CLASS_VERIFICATION


def test_ready_result_with_failed_tag_eligibility_is_not_ready() -> None:
    payload = _eligibility_payload()
    payload["result"] = RESULT_READY
    payload["blockers"] = []
    payload["tag_eligibility"] = "FAIL"
    item = classify_payload(payload)
    assert item.kind == CLASS_VERIFICATION


def test_closeout_fixture_layout_has_exactly_one_payload_per_python() -> None:
    payloads, problems = load_aggregate_payloads(CLOSEOUT_ARTIFACTS)
    assert problems == []
    assert len(payloads) == 2
    by_python = {payload["python_version"] for _, payload in payloads}
    assert by_python == {"3.11", "3.12"}
    for _, payload in payloads:
        assert payload["blockers"] == [existing_canonical_tag_blocker("0.1.1")]
        assert payload["tag_eligibility"] == "FAIL"
        assert payload["result"] == RESULT_BLOCKED
        for field in (
            "version_authority",
            "tests",
            "wheel_build",
            "fresh_install",
            "package_parity",
            "msme_resources",
            "msme_cli",
            "manifest",
        ):
            assert payload[field] == "PASS"


def test_aggregate_closeout_artifacts_both_legs_eligibility_verify_success() -> None:
    """The reviewer's cited case, against captured workflow artifacts.

    Exactly one payload per Python version, both eligibility-blocked, and
    ``needs.verify.result`` is success.
    """
    proc = _run_classifier(
        "--aggregate",
        str(CLOSEOUT_ARTIFACTS),
        "--verify-result",
        "success",
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "VERIFICATION: PASS" in proc.stdout
    assert "RESULT: BLOCKED" in proc.stdout
    assert existing_canonical_tag_blocker("0.1.1") in proc.stdout
    assert "verification legs failed" not in proc.stdout
    assert "missing release evidence" not in proc.stdout
    assert "ambiguous" not in proc.stdout


def test_aggregate_classifications_closeout_payloads_keep_eligibility_precise() -> None:
    payloads, problems = load_aggregate_payloads(CLOSEOUT_ARTIFACTS)
    assert problems == []
    items = [classify_payload(payload) for _, payload in payloads]
    assert {item.kind for item in items} == {CLASS_ELIGIBILITY}
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert result == RESULT_BLOCKED
    assert verification == "PASS"
    assert blockers == [existing_canonical_tag_blocker("0.1.1")]
    text = format_aggregate(result, blockers, verification)
    assert "VERIFICATION: PASS" in text
    assert "verification legs failed" not in text


def test_aggregate_rejects_duplicate_payload_for_one_python(tmp_path: Path) -> None:
    dest = tmp_path / "release-candidate-3.11"
    dest.mkdir()
    dest.joinpath("release_evidence_0.1.1.json").write_text(
        json.dumps(_eligibility_payload("3.11")) + "\n", encoding="utf-8"
    )
    dest.joinpath("release_evidence_copy.json").write_text(
        json.dumps(_eligibility_payload("3.11")) + "\n", encoding="utf-8"
    )
    (tmp_path / "release-candidate-3.12").mkdir()
    (tmp_path / "release-candidate-3.12" / "release_evidence_0.1.1.json").write_text(
        json.dumps(_eligibility_payload("3.12")) + "\n", encoding="utf-8"
    )
    payloads, problems = load_aggregate_payloads(tmp_path)
    assert any("ambiguous release evidence for Python 3.11" in item for item in problems)
    items = [classify_payload(payload) for _, payload in payloads]
    result, blockers, verification = aggregate_classifications(
        items, verify_result="success", load_problems=problems
    )
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert any("ambiguous" in item for item in blockers)


def test_aggregate_rejects_unexpected_evidence_file(tmp_path: Path) -> None:
    shutil.copytree(CLOSEOUT_ARTIFACTS, tmp_path / "artifacts")
    extra = tmp_path / "artifacts" / "stale" / "release_evidence_0.1.0.json"
    extra.parent.mkdir()
    extra.write_text(json.dumps(_eligibility_payload("3.11")) + "\n", encoding="utf-8")
    proc = _run_classifier(
        "--aggregate",
        str(tmp_path / "artifacts"),
        "--verify-result",
        "success",
    )
    assert proc.returncode == 1
    assert "VERIFICATION: FAIL" in proc.stdout
    assert "unexpected release evidence files" in proc.stdout


def test_aggregate_rejects_mixed_ready_and_eligibility() -> None:
    ready = _eligibility_payload("3.11")
    ready["result"] = RESULT_READY
    ready["tag_eligibility"] = "PASS"
    ready["blockers"] = []
    items = [
        classify_payload(ready),
        classify_payload(_eligibility_payload("3.12")),
    ]
    assert items[0].kind == CLASS_READY
    assert items[1].kind == CLASS_ELIGIBILITY
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert any("disagree on tag eligibility" in item for item in blockers)


def test_aggregate_reports_verification_failure_over_eligibility() -> None:
    failed = _eligibility_payload("3.11")
    failed["fresh_install"] = "FAIL"
    failed["blockers"] = ["fresh install was not run", existing_canonical_tag_blocker("0.1.1")]
    items = [
        classify_payload(failed),
        classify_payload(_eligibility_payload("3.12")),
    ]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert any("fresh install was not run" in item for item in blockers)


def test_aggregate_rejects_version_disagreement() -> None:
    other = _eligibility_payload("3.12")
    other["version"] = "0.1.2"
    other["canonical_tag"] = "v0.1.2"
    other["blockers"] = [existing_canonical_tag_blocker("0.1.2")]
    items = [
        classify_payload(_eligibility_payload("3.11")),
        classify_payload(other),
    ]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert any("disagree on version" in item for item in blockers)


def test_aggregate_missing_leg_with_verify_success_is_verification_failure() -> None:
    items = [classify_payload(_eligibility_payload("3.11"))]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert any("missing release evidence for Python 3.12" in item for item in blockers)
    assert "verification legs failed" not in "".join(blockers)


def test_non_object_evidence_fails_closed_in_verify_dir(tmp_path: Path) -> None:
    (tmp_path / "release_evidence_0.1.1.json").write_text("[]\n", encoding="utf-8")
    proc = _run_classifier("--evidence-dir", str(tmp_path))
    assert proc.returncode == 1
    assert "release evidence JSON missing or ambiguous" in proc.stdout
