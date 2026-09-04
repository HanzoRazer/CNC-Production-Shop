"""Shared release-classifier assertions.

Prefer structured result/verification/exit-code checks over exact prose.
The compact ``RESULT`` / ``VERIFICATION`` fields are the operator-facing
contract. Classification labels, load-error sentences, and blocker copy
are not, except the governed existing-tag message produced by
``existing_canonical_tag_blocker``.
"""

from __future__ import annotations

import subprocess

from scripts.release.classify_candidate_result import (
    CLASS_ELIGIBILITY,
    CLASS_VERIFICATION,
    VERIFICATION_FIELDS,
    CandidateClassification,
    verification_passed,
)
from scripts.release.model import RESULT_BLOCKED, tag_for_version
from scripts.release.tag_eligibility import (
    ELIGIBILITY_BLOCKER_KINDS,
    EXISTING_CANONICAL_TAG_KIND,
    canonical_tag_absent_check_message,
    eligibility_blocker_kind,
    existing_canonical_tag_blocker,
)

# One sample per catalogued eligibility kind. Add a row when a kind is added.
ELIGIBILITY_KIND_SAMPLES: dict[str, str] = {
    EXISTING_CANONICAL_TAG_KIND: existing_canonical_tag_blocker("0.1.1"),
}

# Policy/source blockers that must not classify as eligibility. Messages are
# representative, not an exhaustive snapshot of production copy.
NON_ELIGIBILITY_POLICY_SAMPLES: tuple[str, ...] = (
    "working tree clean",
    "CHANGELOG.md exists",
    "changelog has a 0.1.1 section or release-ready Unreleased material",
    "git metadata present at --root",
    "HEAD 18125a09bfc1d1cf9a8470ce32ccd07970e0e9fb does not match "
    "expected_commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    canonical_tag_absent_check_message("0.1.1"),
)


def eligibility_payload(
    python_version: str = "3.11",
    *,
    version: str = "0.1.1",
    blocker: str | None = None,
) -> dict[str, object]:
    """Evidence payload whose only blocker is a catalogued eligibility reason."""
    return {
        "result": RESULT_BLOCKED,
        "version": version,
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
        "canonical_tag": tag_for_version(version),
        "blockers": [blocker if blocker is not None else existing_canonical_tag_blocker(version)],
    }


def cli_field(stdout: str, name: str) -> str:
    prefix = f"{name}: "
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise AssertionError(f"{name!r} field missing from classifier output:\n{stdout}")


def assert_eligibility_classification(item: CandidateClassification) -> None:
    assert item.kind == CLASS_ELIGIBILITY
    assert item.verification == "PASS"
    assert item.result == RESULT_BLOCKED
    assert item.blockers
    assert all(
        eligibility_blocker_kind(blocker, version=item.version) in ELIGIBILITY_BLOCKER_KINDS
        for blocker in item.blockers
    )


def assert_verification_classification(
    item: CandidateClassification,
    *,
    verified: bool | None = None,
) -> None:
    assert item.kind == CLASS_VERIFICATION
    assert item.result == RESULT_BLOCKED
    if verified is not None:
        assert item.verification == ("PASS" if verified else "FAIL")


def assert_aggregate_eligibility_only(result: str, blockers: list[str], verification: str) -> None:
    assert result == RESULT_BLOCKED
    assert verification == "PASS"
    assert blockers
    assert all(eligibility_blocker_kind(item) in ELIGIBILITY_BLOCKER_KINDS for item in blockers)


def assert_aggregate_verification_failure(
    result: str, blockers: list[str], verification: str
) -> None:
    assert result == RESULT_BLOCKED
    assert verification == "FAIL"
    assert blockers


def assert_cli_eligibility_only(
    proc: subprocess.CompletedProcess[str],
    *,
    aggregate: bool,
) -> None:
    """Verify-job CLI exits 0; aggregator CLI exits 1. Neither is a verify-leg failure."""
    expected = 1 if aggregate else 0
    assert proc.returncode == expected, proc.stdout + proc.stderr
    assert cli_field(proc.stdout, "RESULT") == RESULT_BLOCKED
    assert cli_field(proc.stdout, "VERIFICATION") == "PASS"
    assert "verification legs failed" not in proc.stdout


def assert_cli_verification_failure(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert cli_field(proc.stdout, "RESULT") == RESULT_BLOCKED
    assert cli_field(proc.stdout, "VERIFICATION") == "FAIL"


def assert_verified_payload(payload: dict[str, object]) -> None:
    assert verification_passed(payload)
    assert all(field in payload for field in VERIFICATION_FIELDS)
