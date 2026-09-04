"""Classifier contracts for eligibility vs verification, including real artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.release.classify_candidate_result import (
    CLASS_READY,
    aggregate_classifications,
    classify_payload,
    is_eligibility_blocker,
    load_aggregate_payloads,
)
from scripts.release.model import RESULT_BLOCKED, RESULT_READY
from scripts.release.tag_eligibility import (
    ELIGIBILITY_BLOCKER_KINDS,
    EXISTING_CANONICAL_TAG_KIND,
    NON_ELIGIBILITY_POLICY_KINDS,
    eligibility_blocker_kind,
    existing_canonical_tag_blocker,
    inspect_tag_eligibility,
)
from tests.releases.classifier_contracts import (
    ELIGIBILITY_KIND_SAMPLES,
    NON_ELIGIBILITY_POLICY_SAMPLES,
    assert_aggregate_eligibility_only,
    assert_aggregate_verification_failure,
    assert_cli_eligibility_only,
    assert_cli_verification_failure,
    assert_eligibility_classification,
    assert_verification_classification,
    assert_verified_payload,
    eligibility_payload,
)
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


def test_eligibility_catalog_does_not_overlap_policy_kinds() -> None:
    assert EXISTING_CANONICAL_TAG_KIND in ELIGIBILITY_BLOCKER_KINDS
    assert ELIGIBILITY_BLOCKER_KINDS.isdisjoint(NON_ELIGIBILITY_POLICY_KINDS)
    assert set(ELIGIBILITY_KIND_SAMPLES) == set(ELIGIBILITY_BLOCKER_KINDS)


def test_governed_existing_tag_message_is_the_operator_facing_contract() -> None:
    """Documented compact-summary wording. Only this eligibility phrase is pinned."""
    assert existing_canonical_tag_blocker("0.1.1") == "canonical tag v0.1.1 already exists"


def test_every_catalogued_eligibility_kind_classifies_as_eligibility() -> None:
    for kind, sample in ELIGIBILITY_KIND_SAMPLES.items():
        assert eligibility_blocker_kind(sample) == kind
        item = classify_payload(eligibility_payload(blocker=sample))
        assert_eligibility_classification(item)


def test_inspect_tag_eligibility_emits_catalog_blocker(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.2")
    subprocess.run(["git", "tag", "v0.1.2"], cwd=tmp_path, check=True, capture_output=True)
    eligibility = inspect_tag_eligibility(tmp_path, "0.1.2")
    assert (
        eligibility_blocker_kind(eligibility.detail, version="0.1.2") in ELIGIBILITY_BLOCKER_KINDS
    )
    assert is_eligibility_blocker(eligibility.detail, version="0.1.2", canonical_tag="v0.1.2")


def test_known_policy_blockers_are_not_classified_as_eligibility() -> None:
    for blocker in NON_ELIGIBILITY_POLICY_SAMPLES:
        payload = eligibility_payload(blocker=blocker)
        item = classify_payload(payload)
        assert eligibility_blocker_kind(blocker) is None
        assert_verification_classification(item, verified=True)


def test_inconsistent_tag_eligibility_field_is_not_eligibility() -> None:
    payload = eligibility_payload()
    payload["tag_eligibility"] = "PASS"
    assert_verification_classification(classify_payload(payload))


def test_ready_result_with_failed_tag_eligibility_is_not_ready() -> None:
    payload = eligibility_payload()
    payload["result"] = RESULT_READY
    payload["blockers"] = []
    payload["tag_eligibility"] = "FAIL"
    assert_verification_classification(classify_payload(payload), verified=True)


def test_closeout_fixture_has_one_verified_payload_per_required_python() -> None:
    payloads, problems = load_aggregate_payloads(CLOSEOUT_ARTIFACTS)
    assert problems == []
    by_python = {payload["python_version"] for _, payload in payloads}
    assert by_python == {"3.11", "3.12"}
    for _, payload in payloads:
        assert_verified_payload(payload)
        assert payload["result"] == RESULT_BLOCKED
        assert payload["tag_eligibility"] == "FAIL"
        assert_eligibility_classification(classify_payload(payload))


def test_aggregate_closeout_artifacts_both_legs_eligibility_verify_success() -> None:
    """Exactly one payload per Python version, both eligibility-blocked, verify success."""
    proc = _run_classifier(
        "--aggregate",
        str(CLOSEOUT_ARTIFACTS),
        "--verify-result",
        "success",
    )
    assert_cli_eligibility_only(proc, aggregate=True)


def test_aggregate_classifications_closeout_payloads_keep_eligibility_precise() -> None:
    payloads, problems = load_aggregate_payloads(CLOSEOUT_ARTIFACTS)
    assert problems == []
    items = [classify_payload(payload) for _, payload in payloads]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert_aggregate_eligibility_only(result, blockers, verification)


def test_aggregate_rejects_duplicate_payload_for_one_python(tmp_path: Path) -> None:
    dest = tmp_path / "release-candidate-3.11"
    dest.mkdir()
    dest.joinpath("release_evidence_0.1.1.json").write_text(
        json.dumps(eligibility_payload("3.11")) + "\n", encoding="utf-8"
    )
    dest.joinpath("release_evidence_copy.json").write_text(
        json.dumps(eligibility_payload("3.11")) + "\n", encoding="utf-8"
    )
    (tmp_path / "release-candidate-3.12").mkdir()
    (tmp_path / "release-candidate-3.12" / "release_evidence_0.1.1.json").write_text(
        json.dumps(eligibility_payload("3.12")) + "\n", encoding="utf-8"
    )
    payloads, problems = load_aggregate_payloads(tmp_path)
    assert problems
    result, blockers, verification = aggregate_classifications(
        [classify_payload(payload) for _, payload in payloads],
        verify_result="success",
        load_problems=problems,
    )
    assert_aggregate_verification_failure(result, blockers, verification)


def test_aggregate_rejects_unexpected_evidence_file(tmp_path: Path) -> None:
    shutil.copytree(CLOSEOUT_ARTIFACTS, tmp_path / "artifacts")
    extra = tmp_path / "artifacts" / "stale" / "release_evidence_0.1.0.json"
    extra.parent.mkdir()
    extra.write_text(json.dumps(eligibility_payload("3.11")) + "\n", encoding="utf-8")
    proc = _run_classifier(
        "--aggregate",
        str(tmp_path / "artifacts"),
        "--verify-result",
        "success",
    )
    assert_cli_verification_failure(proc)


def test_aggregate_rejects_mixed_ready_and_eligibility() -> None:
    ready = eligibility_payload("3.11")
    ready["result"] = RESULT_READY
    ready["tag_eligibility"] = "PASS"
    ready["blockers"] = []
    items = [
        classify_payload(ready),
        classify_payload(eligibility_payload("3.12")),
    ]
    assert items[0].kind == CLASS_READY
    assert_eligibility_classification(items[1])
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert_aggregate_verification_failure(result, blockers, verification)


def test_aggregate_reports_verification_failure_over_eligibility() -> None:
    failed = eligibility_payload("3.11")
    failed["fresh_install"] = "FAIL"
    failed["blockers"] = ["fresh install was not run", existing_canonical_tag_blocker("0.1.1")]
    items = [
        classify_payload(failed),
        classify_payload(eligibility_payload("3.12")),
    ]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert_aggregate_verification_failure(result, blockers, verification)


def test_aggregate_rejects_version_disagreement() -> None:
    items = [
        classify_payload(eligibility_payload("3.11", version="0.1.1")),
        classify_payload(eligibility_payload("3.12", version="0.1.2")),
    ]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert_aggregate_verification_failure(result, blockers, verification)


def test_aggregate_missing_leg_with_verify_success_is_verification_failure() -> None:
    items = [classify_payload(eligibility_payload("3.11"))]
    result, blockers, verification = aggregate_classifications(items, verify_result="success")
    assert_aggregate_verification_failure(result, blockers, verification)


def test_non_object_evidence_fails_closed_in_verify_dir(tmp_path: Path) -> None:
    (tmp_path / "release_evidence_0.1.1.json").write_text("[]\n", encoding="utf-8")
    proc = _run_classifier("--evidence-dir", str(tmp_path))
    assert_cli_verification_failure(proc)
