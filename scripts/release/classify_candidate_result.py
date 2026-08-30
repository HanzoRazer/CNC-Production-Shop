#!/usr/bin/env python3
"""Classify release-candidate evidence without collapsing eligibility into verification failure.

Usage:
    python scripts/release/classify_candidate_result.py --evidence-dir dist-release-candidate
    python scripts/release/classify_candidate_result.py --aggregate artifacts

Exit 0 when verification completed (READY_FOR_TAG or eligibility-only BLOCKED).
Exit 1 when verification failed or required evidence is missing.

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

from scripts.release.model import RESULT_BLOCKED, RESULT_READY  # noqa: E402

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


def is_eligibility_blocker(item: str) -> bool:
    """Return True for the governed existing-tag eligibility blocker."""
    text = item.strip()
    return text.startswith("canonical tag ") and text.endswith(" already exists")


def verification_passed(payload: dict[str, object]) -> bool:
    return all(str(payload.get(field) or "") == "PASS" for field in VERIFICATION_FIELDS)


def classify_payload(payload: dict[str, object]) -> CandidateClassification:
    """Classify one evidence payload."""
    blockers = tuple(
        str(item) for item in (payload.get("blockers") or []) if str(item).strip()
    )
    python_version = str(payload.get("python_version") or "")
    version = str(payload.get("version") or "")
    commit_sha = str(payload.get("commit_sha") or "")
    tag_eligibility = str(payload.get("tag_eligibility") or "FAIL")
    result = str(payload.get("result") or RESULT_BLOCKED)
    verified = verification_passed(payload)
    eligibility_only = bool(blockers) and all(is_eligibility_blocker(item) for item in blockers)

    if verified and result == RESULT_READY and not blockers:
        kind = CLASS_READY
        verification = "PASS"
    elif verified and eligibility_only:
        kind = CLASS_ELIGIBILITY
        verification = "PASS"
        result = RESULT_BLOCKED
    else:
        kind = CLASS_VERIFICATION
        verification = "PASS" if verified else "FAIL"
        result = RESULT_BLOCKED
        if not blockers:
            blockers = ("verification evidence incomplete or failed",)

    return CandidateClassification(
        kind=kind,
        result=result,
        verification=verification,
        tag_eligibility=tag_eligibility,
        blockers=blockers,
        python_version=python_version,
        version=version,
        commit_sha=commit_sha,
    )


def load_evidence_payloads(root: Path) -> list[tuple[Path, dict[str, object]]]:
    """Load ``release_evidence_*.json`` files under ``root``."""
    found: list[tuple[Path, dict[str, object]]] = []
    for path in sorted(root.rglob("release_evidence_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
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
    if item.result != RESULT_READY and item.blockers:
        lines.append("BLOCKERS:")
        for blocker in item.blockers:
            lines.append(f"- {blocker}")
    return "\n".join(lines) + "\n"


def classify_evidence_dir(evidence_dir: Path) -> CandidateClassification:
    payloads = load_evidence_payloads(evidence_dir)
    if len(payloads) != 1:
        return CandidateClassification(
            kind=CLASS_VERIFICATION,
            result=RESULT_BLOCKED,
            verification="FAIL",
            tag_eligibility="FAIL",
            blockers=("release evidence JSON missing or ambiguous",),
            python_version="",
            version="",
            commit_sha="",
        )
    return classify_payload(payloads[0][1])


def aggregate_classifications(
    items: list[CandidateClassification],
    *,
    verify_result: str,
) -> tuple[str, list[str], str]:
    """Return (result, blockers, verification) for the matrix."""
    by_python = {item.python_version: item for item in items}
    missing = [label for label in REQUIRED_PYTHON_LEGS if label not in by_python]
    blockers: list[str] = []
    if missing:
        blockers.append(
            "missing release evidence for Python " + ", ".join(missing)
        )
    verification_failures = [
        item
        for item in items
        if item.kind == CLASS_VERIFICATION
    ]
    for item in verification_failures:
        label = item.python_version or "unknown"
        if item.blockers:
            blockers.extend(f"Python {label}: {blocker}" for blocker in item.blockers)
        else:
            blockers.append(f"Python {label}: verification failed")

    if missing or verification_failures:
        if verify_result and verify_result != "success" and not items:
            blockers.append(
                f"one or more Python 3.11/3.12 verification legs failed ({verify_result})"
            )
        unique: list[str] = []
        for item in blockers:
            if item not in unique:
                unique.append(item)
        return RESULT_BLOCKED, unique, "FAIL"

    eligibility = [item for item in items if item.kind == CLASS_ELIGIBILITY]
    if eligibility:
        unique = []
        for item in eligibility:
            for blocker in item.blockers:
                if blocker not in unique:
                    unique.append(blocker)
        return RESULT_BLOCKED, unique, "PASS"

    if all(item.kind == CLASS_READY for item in items) and len(items) >= len(REQUIRED_PYTHON_LEGS):
        return RESULT_READY, [], "PASS"

    return RESULT_BLOCKED, ["matrix evidence incomplete"], "FAIL"


def format_aggregate(result: str, blockers: list[str], verification: str) -> str:
    lines = [
        f"VERIFICATION: {verification}",
        f"TAG ELIGIBILITY: {'FAIL' if result != RESULT_READY else 'PASS'}",
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
    elif blockers:
        lines.append("BLOCKERS:")
        for blocker in blockers:
            lines.append(f"- {blocker}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--aggregate", type=Path, default=None)
    parser.add_argument(
        "--verify-result",
        default="",
        help="GitHub needs.verify.result, used only when evidence is absent",
    )
    args = parser.parse_args()
    if args.aggregate is not None:
        payloads = load_evidence_payloads(args.aggregate)
        items = [classify_payload(payload) for _, payload in payloads]
        result, blockers, verification = aggregate_classifications(
            items, verify_result=args.verify_result
        )
        sys.stdout.write(format_aggregate(result, blockers, verification))
        return 0 if result == RESULT_READY else 1
    if args.evidence_dir is None:
        parser.error("provide --evidence-dir or --aggregate")
    classification = classify_evidence_dir(args.evidence_dir)
    sys.stdout.write(format_classification(classification))
    return 0 if classification.kind != CLASS_VERIFICATION else 1


if __name__ == "__main__":
    raise SystemExit(main())
