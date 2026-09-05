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
and renders it. Payloads written before the blockers/failures split are still
understood: for those, eligibility is recovered from the blocker prose.

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
    VERIFICATION_FAIL,
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

REQUIRED_PYTHON_LEGS = ("3.11", "3.12")


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


def is_eligibility_blocker(item: str) -> bool:
    """Return True for the governed existing-tag eligibility blocker.

    Only used for evidence written before ``failures`` existed as its own
    channel. Current payloads state the distinction outright.
    """
    text = item.strip()
    return text.startswith("canonical tag ") and text.endswith(" already exists")


def verification_passed(payload: dict[str, object]) -> bool:
    return all(str(payload.get(field) or "") == "PASS" for field in VERIFICATION_FIELDS)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _split_legacy_channels(payload: dict[str, object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Recover (blockers, failures) from a payload that had only ``blockers``."""
    recorded = _strings(payload.get("blockers"))
    if verification_passed(payload):
        eligibility = tuple(item for item in recorded if is_eligibility_blocker(item))
        residual = tuple(item for item in recorded if not is_eligibility_blocker(item))
        return eligibility, residual
    return (), recorded or ("verification evidence incomplete or failed",)


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

    disposition = derive_candidate_disposition(failures, blockers)
    verification = derive_verification_status(failures)
    if not semantic and not verification_passed(payload):
        verification = VERIFICATION_FAIL
    eligibility_status = derive_eligibility_status(evaluated=evaluated, blockers=blockers)
    return CandidateClassification(
        kind=_KIND_FOR_DISPOSITION[disposition],
        result=disposition,
        verification=verification,
        tag_eligibility="FAIL" if eligibility_status != "PASS" else "PASS",
        blockers=blockers,
        python_version=str(payload.get("python_version") or ""),
        version=str(payload.get("version") or ""),
        commit_sha=str(payload.get("commit_sha") or ""),
        failures=failures,
    )


def load_evidence_payloads(root: Path) -> list[tuple[Path, dict[str, object]]]:
    """Load ``release_evidence_*.json`` files under ``root``."""
    found: list[tuple[Path, dict[str, object]]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("release_evidence_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            found.append((path, payload))
    return found


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


def aggregate_classifications(
    items: list[CandidateClassification],
    *,
    verify_result: str,
) -> tuple[str, list[str], str, list[str]]:
    """Return (result, blockers, verification, failures) for the matrix."""
    combined = aggregate_candidate_results(
        [_as_payload(item) for item in items],
        verify_job_result=verify_result,
    )
    blockers = combined.get("blockers")
    failures = combined.get("failures")
    return (
        str(combined.get("disposition") or RESULT_FAILED),
        list(blockers) if isinstance(blockers, list) else [],
        str(combined.get("verification_status") or VERIFICATION_FAIL),
        list(failures) if isinstance(failures, list) else [],
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
        payloads = load_evidence_payloads(args.aggregate)
        items = [classify_payload(payload) for _, payload in payloads]
        result, blockers, verification, failures = aggregate_classifications(
            items, verify_result=args.verify_result
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
