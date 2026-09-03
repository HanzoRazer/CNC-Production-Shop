#!/usr/bin/env python3
"""Classify release-candidate evidence without collapsing eligibility into verification failure.

Usage:
    python scripts/release/classify_candidate_result.py --evidence-dir dist-release-candidate
    python scripts/release/classify_candidate_result.py --aggregate artifacts

``--evidence-dir`` (verify job):
    Exit 0 when verification completed (READY_FOR_TAG or eligibility-only BLOCKED).
    Exit 1 when verification failed or required evidence is missing.

``--aggregate`` (summarize job):
    Exit 0 only for READY_FOR_TAG.
    Exit 1 for eligibility-only BLOCKED, verification failure, or missing evidence.

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

from scripts.release.model import (  # noqa: E402
    RESULT_BLOCKED,
    RESULT_READY,
    SUPPORTED_PYTHON_VERSIONS,
)
from scripts.release.tag_eligibility import (  # noqa: E402
    ELIGIBILITY_BLOCKER_KINDS,
    eligibility_blocker_kind,
    is_existing_canonical_tag_blocker,
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


def is_eligibility_blocker(item: str, *, version: str = "", canonical_tag: str = "") -> bool:
    """Return True for a catalogued existing-tag eligibility blocker."""
    return is_existing_canonical_tag_blocker(item, version=version, canonical_tag=canonical_tag)


def verification_passed(payload: dict[str, object]) -> bool:
    return all(str(payload.get(field) or "") == "PASS" for field in VERIFICATION_FIELDS)


def classify_payload(payload: dict[str, object]) -> CandidateClassification:
    """Classify one evidence payload."""
    raw_blockers = payload.get("blockers")
    if isinstance(raw_blockers, list):
        blockers = tuple(str(item) for item in raw_blockers if str(item).strip())
    elif raw_blockers in (None, ""):
        blockers = ()
    else:
        blockers = (str(raw_blockers),) if str(raw_blockers).strip() else ()
    python_version = str(payload.get("python_version") or "")
    version = str(payload.get("version") or "")
    commit_sha = str(payload.get("commit_sha") or "")
    canonical_tag = str(payload.get("canonical_tag") or "")
    tag_eligibility = str(payload.get("tag_eligibility") or "FAIL")
    result = str(payload.get("result") or RESULT_BLOCKED)
    verified = verification_passed(payload)
    kinds = [
        eligibility_blocker_kind(item, version=version, canonical_tag=canonical_tag)
        for item in blockers
    ]
    eligibility_only = (
        bool(blockers)
        and all(kind in ELIGIBILITY_BLOCKER_KINDS for kind in kinds)
        and tag_eligibility == "FAIL"
        and verified
    )

    if verified and result == RESULT_READY and not blockers and tag_eligibility == "PASS":
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
    """Load ``release_evidence_*.json`` files under ``root``.

    Any unreadable or non-object file fails closed as an empty result so the
    caller treats the directory as missing or ambiguous.
    """
    found: list[tuple[Path, dict[str, object]]] = []
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
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def load_aggregate_payloads(
    root: Path,
) -> tuple[list[tuple[Path, dict[str, object]]], list[str]]:
    """Load evidence from the workflow download-artifact layout.

    Expected:

    ``<root>/release-candidate-3.11/release_evidence_*.json``
    ``<root>/release-candidate-3.12/release_evidence_*.json``

    Exactly one object per required Python version. Extra, unreadable, or
    non-object evidence files are reported as problems (fail closed).
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


def _unique(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


def aggregate_classifications(
    items: list[CandidateClassification],
    *,
    verify_result: str,
    load_problems: list[str] | None = None,
) -> tuple[str, list[str], str]:
    """Return (result, blockers, verification) for the matrix."""
    blockers: list[str] = list(load_problems or [])
    seen: dict[str, CandidateClassification] = {}
    duplicates: list[str] = []
    for item in items:
        label = item.python_version
        if not label:
            blockers.append("release evidence missing python_version")
            continue
        if label in seen:
            if label not in duplicates:
                duplicates.append(label)
            continue
        seen[label] = item
    if duplicates:
        blockers.append("duplicate release evidence for Python " + ", ".join(duplicates))

    missing = [label for label in REQUIRED_PYTHON_LEGS if label not in seen]
    if missing:
        blockers.append("missing release evidence for Python " + ", ".join(missing))

    unexpected = sorted(label for label in seen if label not in REQUIRED_PYTHON_LEGS)
    if unexpected:
        blockers.append("unexpected Python legs: " + ", ".join(unexpected))

    versions = {item.version for item in items if item.version}
    shas = {item.commit_sha for item in items if item.commit_sha}
    if len(versions) > 1:
        blockers.append("matrix legs disagree on version: " + ", ".join(sorted(versions)))
    if len(shas) > 1:
        blockers.append("matrix legs disagree on commit")

    verification_failures = [item for item in items if item.kind == CLASS_VERIFICATION]
    for item in verification_failures:
        label = item.python_version or "unknown"
        if item.blockers:
            blockers.extend(f"Python {label}: {blocker}" for blocker in item.blockers)
        else:
            blockers.append(f"Python {label}: verification failed")

    kinds = {item.kind for item in items}
    eligibility_disagreement = CLASS_READY in kinds and CLASS_ELIGIBILITY in kinds
    if eligibility_disagreement:
        blockers.append("matrix legs disagree on tag eligibility")

    structural_failure = bool(
        load_problems
        or missing
        or duplicates
        or unexpected
        or len(versions) > 1
        or len(shas) > 1
        or eligibility_disagreement
        or any(not item.python_version for item in items)
    )

    if structural_failure or verification_failures:
        if verify_result and verify_result != "success" and not items:
            blockers.append(
                f"one or more Python 3.11/3.12 verification legs failed ({verify_result})"
            )
        return RESULT_BLOCKED, _unique(blockers), "FAIL"

    eligibility = [item for item in items if item.kind == CLASS_ELIGIBILITY]
    if eligibility:
        unique: list[str] = []
        for item in eligibility:
            for blocker in item.blockers:
                if blocker not in unique:
                    unique.append(blocker)
        return RESULT_BLOCKED, unique, "PASS"

    if all(item.kind == CLASS_READY for item in items) and len(items) >= len(REQUIRED_PYTHON_LEGS):
        return RESULT_READY, [], "PASS"

    return RESULT_BLOCKED, _unique(blockers or ["matrix evidence incomplete"]), "FAIL"


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
        payloads, load_problems = load_aggregate_payloads(args.aggregate)
        items = [classify_payload(payload) for _, payload in payloads]
        result, blockers, verification = aggregate_classifications(
            items, verify_result=args.verify_result, load_problems=load_problems
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
