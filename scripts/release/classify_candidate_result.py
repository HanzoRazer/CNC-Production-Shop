#!/usr/bin/env python3
"""Classify release-candidate evidence without collapsing eligibility into failure.

Usage:
    python scripts/release/classify_candidate_result.py --evidence-dir dist-release-candidate
    python scripts/release/classify_candidate_result.py --aggregate artifacts

This is the only classifier. It reads the evidence written by
``build_release_candidate.py`` and reports one of three dispositions:
``READY_FOR_TAG``, ``BLOCKED`` (verification passed, policy declines the tag),
or ``FAILED`` (verification or evidence generation broke).

The semantics live in ``candidate_result``; this module reads evidence off disk
and renders it. It answers two different questions and keeps them apart:

* *Does the evidence say what it claims?* Shape defects -- an unreadable file,
  two payloads for one Python leg, legs disagreeing on version or commit, a
  payload whose ``tag_eligibility`` field contradicts its own blockers -- are
  evidence-generation failures, so they land in ``failures``.
* *Does policy permit the tag?* Eligibility and readiness conditions land in
  ``blockers``.

Payloads written before the blockers/failures split are still understood.
Their single ``blockers`` list is re-split using the governed catalogue in
``tag_eligibility``, never a prefix match: an eligibility kind or a known
policy kind stays a blocker, and unrecognised wording fails closed into
``failures``.

Exit codes:
    --evidence-dir  0 for READY_FOR_TAG or BLOCKED; 1 for FAILED or missing evidence.
    --aggregate     0 only for READY_FOR_TAG.

Does not create tags, mutate source, or publish.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.candidate_result import (  # noqa: E402
    aggregate_candidate_results,
    derive_candidate_disposition,
    derive_eligibility_status,
    derive_verification_status,
)
from scripts.release.model import (  # noqa: E402
    ELIGIBILITY_NOT_EVALUATED,
    RESULT_BLOCKED,
    RESULT_FAILED,
    RESULT_READY,
    SUPPORTED_PYTHON_VERSIONS,
    VERIFICATION_FAIL,
)
from scripts.release.tag_eligibility import (  # noqa: E402
    ELIGIBILITY_BLOCKER_KINDS,
    eligibility_blocker_kind,
    is_existing_canonical_tag_blocker,
    policy_blocker_kind,
)

VERIFICATION_FIELDS = (
    "version_authority",
    "tests",
    "wheel_build",
    "fresh_install",
    "package_parity",
    "msme_resources",
    "msme_cli",
    "manifest",
)

CLASS_READY = "READY_FOR_TAG"
CLASS_ELIGIBILITY = "ELIGIBILITY_BLOCKED"
CLASS_VERIFICATION = "VERIFICATION_FAILED"

_KIND_FOR_DISPOSITION = {
    RESULT_READY: CLASS_READY,
    RESULT_BLOCKED: CLASS_ELIGIBILITY,
    RESULT_FAILED: CLASS_VERIFICATION,
}

REQUIRED_PYTHON_LEGS = SUPPORTED_PYTHON_VERSIONS
WORKFLOW_ARTIFACT_PREFIX = "release-candidate-"


@dataclass(frozen=True)
class CandidateClassification:
    kind: str
    result: str
    verification: str
    tag_eligibility: str
    blockers: tuple[str, ...]
    python_version: str
    version: str
    commit_sha: str
    failures: tuple[str, ...] = ()


def is_eligibility_blocker(item: str, *, version: str = "", canonical_tag: str = "") -> bool:
    """Return True for a catalogued existing-tag eligibility blocker."""
    return is_existing_canonical_tag_blocker(item, version=version, canonical_tag=canonical_tag)


def verification_passed(payload: dict[str, object]) -> bool:
    return all(str(payload.get(field) or "") == "PASS" for field in VERIFICATION_FIELDS)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if value in (None, ""):
        return ()
    return (str(value),) if str(value).strip() else ()


def _payload_inconsistencies(
    payload: dict[str, object],
    blockers: tuple[str, ...],
) -> tuple[str, ...]:
    """Ways a payload can contradict itself. Each one is an evidence defect."""
    declared = str(payload.get("tag_eligibility") or "")
    if not declared:
        return ()
    version = str(payload.get("version") or "")
    canonical_tag = str(payload.get("canonical_tag") or "")
    has_eligibility_blocker = any(
        eligibility_blocker_kind(item, version=version, canonical_tag=canonical_tag)
        in ELIGIBILITY_BLOCKER_KINDS
        for item in blockers
    )
    if declared == "PASS" and has_eligibility_blocker:
        return ("evidence reports tag_eligibility PASS alongside an eligibility blocker",)
    if declared == "FAIL" and not blockers:
        return ("evidence reports tag_eligibility FAIL with no blocker to justify it",)
    return ()


def _split_legacy_channels(payload: dict[str, object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Recover (blockers, failures) from a payload that had only ``blockers``."""
    recorded = _strings(payload.get("blockers"))
    if not verification_passed(payload):
        return (), recorded or ("verification evidence incomplete or failed",)
    version = str(payload.get("version") or "")
    canonical_tag = str(payload.get("canonical_tag") or "")
    blockers: list[str] = []
    failures: list[str] = []
    for item in recorded:
        catalogued = eligibility_blocker_kind(
            item, version=version, canonical_tag=canonical_tag
        ) or policy_blocker_kind(item, version=version)
        # A catalogued eligibility or policy condition is a governed gate.
        # Anything the catalogue does not recognise fails closed: unknown
        # wording in the one undifferentiated channel could be either.
        (blockers if catalogued else failures).append(item)
    return tuple(blockers), tuple(failures)


def classify_payload(payload: dict[str, object]) -> CandidateClassification:
    """Classify one evidence payload. Recomputes the disposition; does not trust it."""
    semantic = "failures" in payload
    if semantic:
        blockers = _strings(payload.get("blockers"))
        failures = _strings(payload.get("failures"))
        evaluated = str(payload.get("eligibility_status") or "") != ELIGIBILITY_NOT_EVALUATED
    else:
        blockers, failures = _split_legacy_channels(payload)
        evaluated = str(payload.get("tag_eligibility") or "") in {"PASS", "FAIL"}

    failures = failures + _payload_inconsistencies(payload, blockers)
    disposition = derive_candidate_disposition(failures, blockers)
    verification = derive_verification_status(failures)
    if not semantic and not verification_passed(payload):
        verification = VERIFICATION_FAIL
    eligibility_status = derive_eligibility_status(evaluated=evaluated, blockers=blockers)
    return CandidateClassification(
        kind=_KIND_FOR_DISPOSITION[disposition],
        result=disposition,
        verification=verification,
        tag_eligibility="PASS" if eligibility_status == "PASS" else "FAIL",
        blockers=blockers,
        python_version=str(payload.get("python_version") or ""),
        version=str(payload.get("version") or ""),
        commit_sha=str(payload.get("commit_sha") or ""),
        failures=failures,
    )


def load_evidence_payloads(root: Path) -> list[tuple[Path, dict[str, object]]]:
    """Load ``release_evidence_*.json`` files under ``root``.

    An unreadable or non-object file fails closed as an empty result, so the
    caller treats the directory as missing or ambiguous rather than acting on a
    partial view of it.
    """
    found: list[tuple[Path, dict[str, object]]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("release_evidence_*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        found.append((path, payload))
    return found


def _relative_to_root(path: Path, root: Path) -> str:
    """Posix form so the message reads the same on a runner and a workstation."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_aggregate_payloads(
    root: Path,
) -> tuple[list[tuple[Path, dict[str, object]]], list[str]]:
    """Load evidence from the workflow download-artifact layout.

    Expected:

    ``<root>/release-candidate-3.11/release_evidence_*.json``
    ``<root>/release-candidate-3.12/release_evidence_*.json``

    Exactly one object per required Python version. Extra, unreadable, or
    non-object evidence files are reported as problems (fail closed). A leg
    whose directory is simply absent is left to the missing-leg check.
    """
    problems: list[str] = []
    found: list[tuple[Path, dict[str, object]]] = []
    claimed: set[Path] = set()

    for label in REQUIRED_PYTHON_LEGS:
        artifact_dir = root / f"{WORKFLOW_ARTIFACT_PREFIX}{label}"
        if not artifact_dir.is_dir():
            continue
        matches = sorted(
            path for path in artifact_dir.glob("release_evidence_*.json") if path.is_file()
        )
        if len(matches) > 1:
            problems.append(f"ambiguous release evidence for Python {label}")
            claimed.update(path.resolve() for path in matches)
            continue
        if not matches:
            continue
        path = matches[0]
        claimed.add(path.resolve())
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"unreadable release evidence for Python {label}: {exc}")
            continue
        if not isinstance(payload, dict):
            problems.append(f"release evidence for Python {label} is not a JSON object")
            continue
        payload_python = str(payload.get("python_version") or "")
        if payload_python and payload_python != label:
            problems.append(
                f"{WORKFLOW_ARTIFACT_PREFIX}{label} evidence reports python_version "
                f"{payload_python!r}"
            )
        found.append((path, payload))

    extras = [
        path
        for path in sorted(root.rglob("release_evidence_*.json"))
        if path.is_file() and path.resolve() not in claimed
    ]
    if extras:
        names = ", ".join(_relative_to_root(path, root) for path in extras)
        problems.append(f"unexpected release evidence files: {names}")

    return found, problems


def format_classification(item: CandidateClassification) -> str:
    lines = [
        f"VERIFICATION: {item.verification}",
        f"TAG ELIGIBILITY: {item.tag_eligibility}",
        f"CLASS: {item.kind}",
        f"PYTHON: {item.python_version}",
        f"VERSION: {item.version}",
        f"SOURCE SHA: {item.commit_sha}",
        "",
        f"RESULT: {item.result}",
    ]
    if item.blockers:
        lines.append("BLOCKERS:")
        lines.extend(f"- {blocker}" for blocker in item.blockers)
    if item.failures:
        lines.append("FAILURES:")
        lines.extend(f"- {failure}" for failure in item.failures)
    return "\n".join(lines) + "\n"


def classify_evidence_dir(evidence_dir: Path) -> CandidateClassification:
    payloads = load_evidence_payloads(evidence_dir)
    if len(payloads) != 1:
        return CandidateClassification(
            kind=CLASS_VERIFICATION,
            result=RESULT_FAILED,
            verification=VERIFICATION_FAIL,
            tag_eligibility="FAIL",
            blockers=(),
            python_version="",
            version="",
            commit_sha="",
            failures=("release evidence JSON missing or ambiguous",),
        )
    return classify_payload(payloads[0][1])


def _as_payload(item: CandidateClassification) -> dict[str, object]:
    return {
        "python_version": item.python_version,
        "verification_status": item.verification,
        "eligibility_status": derive_eligibility_status(
            evaluated=item.tag_eligibility == "PASS",
            blockers=item.blockers,
        ),
        "disposition": item.result,
        "result": item.result,
        "blockers": list(item.blockers),
        "failures": list(item.failures),
    }


def _shape_failures(items: list[CandidateClassification]) -> list[str]:
    """Ways the matrix as a whole can be malformed, independent of any one leg."""
    problems: list[str] = []
    seen: dict[str, CandidateClassification] = {}
    duplicates: list[str] = []
    for item in items:
        if not item.python_version:
            problems.append("release evidence missing python_version")
            continue
        if item.python_version in seen:
            if item.python_version not in duplicates:
                duplicates.append(item.python_version)
            continue
        seen[item.python_version] = item
    if duplicates:
        problems.append("duplicate release evidence for Python " + ", ".join(duplicates))

    unexpected = sorted(label for label in seen if label not in REQUIRED_PYTHON_LEGS)
    if unexpected:
        problems.append("unexpected Python legs: " + ", ".join(unexpected))

    versions = {item.version for item in items if item.version}
    if len(versions) > 1:
        problems.append("matrix legs disagree on version: " + ", ".join(sorted(versions)))
    shas = {item.commit_sha for item in items if item.commit_sha}
    if len(shas) > 1:
        problems.append("matrix legs disagree on commit")

    kinds = {item.kind for item in items}
    if CLASS_READY in kinds and CLASS_ELIGIBILITY in kinds:
        problems.append("matrix legs disagree on tag eligibility")
    return problems


def aggregate_classifications(
    items: list[CandidateClassification],
    *,
    verify_result: str,
    load_problems: list[str] | None = None,
) -> tuple[str, list[str], str, list[str]]:
    """Return (result, blockers, verification, failures) for the matrix.

    Evidence-shape problems are failures, not blockers: a matrix that cannot
    describe itself has not verified anything, whatever its legs claim.
    """
    shape = list(load_problems or []) + _shape_failures(items)
    combined = aggregate_candidate_results(
        [_as_payload(item) for item in items],
        verify_job_result=verify_result,
    )
    raw_blockers = combined.get("blockers")
    raw_failures = combined.get("failures")
    blocker_list = list(raw_blockers) if isinstance(raw_blockers, list) else []
    failure_list = shape + [
        item
        for item in (raw_failures if isinstance(raw_failures, list) else [])
        if item not in shape
    ]
    return (
        derive_candidate_disposition(failure_list, blocker_list),
        blocker_list,
        derive_verification_status(failure_list),
        failure_list,
    )


def format_aggregate(
    result: str,
    blockers: list[str],
    verification: str,
    failures: list[str] | None = None,
) -> str:
    lines = [
        f"VERIFICATION: {verification}",
        f"TAG ELIGIBILITY: {'PASS' if result == RESULT_READY else 'FAIL'}",
        f"DISPOSITION: {result}",
        "",
        f"RESULT: {result}",
    ]
    if result == RESULT_READY:
        lines.extend(
            [
                "READY_FOR_TAG means verification evidence is complete.",
                "It is not authorization to create a tag or publish.",
            ]
        )
    if blockers:
        lines.append("BLOCKERS:")
        lines.extend(f"- {blocker}" for blocker in blockers)
    if failures:
        lines.append("FAILURES:")
        lines.extend(f"- {failure}" for failure in failures)
    if result == RESULT_BLOCKED:
        lines.append("BLOCKED is a valid verification outcome, not a verification malfunction.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--aggregate", type=Path, default=None)
    parser.add_argument(
        "--verify-result",
        default="",
        help="GitHub needs.verify.result; a non-success job is itself a failure",
    )
    args = parser.parse_args()
    if args.aggregate is not None:
        payloads, load_problems = load_aggregate_payloads(args.aggregate)
        items = [classify_payload(payload) for _, payload in payloads]
        result, blockers, verification, failures = aggregate_classifications(
            items, verify_result=args.verify_result, load_problems=load_problems
        )
        sys.stdout.write(format_aggregate(result, blockers, verification, failures))
        return 0 if result == RESULT_READY else 1
    if args.evidence_dir is None:
        parser.error("provide --evidence-dir or --aggregate")
    classification = classify_evidence_dir(args.evidence_dir)
    sys.stdout.write(format_classification(classification))
    return 0 if classification.kind != CLASS_VERIFICATION else 1


if __name__ == "__main__":
    raise SystemExit(main())
