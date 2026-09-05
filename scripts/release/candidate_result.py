"""Narrow candidate-outcome helpers for release-candidate automation.

Separates eligibility blockers from verification failures. Does not create
tags, publish, or mutate source.
"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.release.model import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_NOT_EVALUATED,
    ELIGIBILITY_PASS,
    RESULT_BLOCKED,
    RESULT_FAILED,
    RESULT_READY,
    SUPPORTED_PYTHON_VERSIONS,
    VERIFICATION_FAIL,
    VERIFICATION_PASS,
    ReleasePolicyError,
)

EXIT_OK = 0
EXIT_FAILED = 2
EXIT_INVOCATION = 3

_ELIGIBILITY_RANK = {
    ELIGIBILITY_PASS: 0,
    ELIGIBILITY_NOT_EVALUATED: 1,
    ELIGIBILITY_BLOCKED: 2,
}


class ReleaseInvocationError(ReleasePolicyError):
    """Wrong release identity or malformed invocation. CLI exit 3."""


def derive_candidate_disposition(
    failures: Sequence[str],
    blockers: Sequence[str],
) -> str:
    """failures present -> FAILED; else blockers present -> BLOCKED; else READY."""
    if failures:
        return RESULT_FAILED
    if blockers:
        return RESULT_BLOCKED
    return RESULT_READY


def derive_eligibility_status(*, evaluated: bool, blockers: Sequence[str]) -> str:
    """Report eligibility only when it was independently meaningful."""
    if blockers:
        return ELIGIBILITY_BLOCKED
    if not evaluated:
        return ELIGIBILITY_NOT_EVALUATED
    return ELIGIBILITY_PASS


def derive_verification_status(failures: Sequence[str]) -> str:
    return VERIFICATION_FAIL if failures else VERIFICATION_PASS


def exit_code_for_disposition(disposition: str) -> int:
    if disposition in {RESULT_READY, RESULT_BLOCKED}:
        return EXIT_OK
    if disposition == RESULT_FAILED:
        return EXIT_FAILED
    return EXIT_INVOCATION


def serialize_candidate_result(
    *,
    verification_status: str,
    eligibility_status: str,
    disposition: str,
    blockers: Sequence[str],
    failures: Sequence[str],
) -> dict[str, object]:
    """Machine-readable candidate result. ``result`` is a disposition alias."""
    unique_blockers = _unique(blockers)
    unique_failures = _unique(failures)
    derived = derive_candidate_disposition(unique_failures, unique_blockers)
    if derived != disposition:
        raise ReleasePolicyError(
            f"disposition {disposition!r} does not match failures/blockers ({derived!r})"
        )
    return {
        "verification_status": verification_status,
        "eligibility_status": eligibility_status,
        "disposition": disposition,
        "result": disposition,
        "blockers": unique_blockers,
        "failures": unique_failures,
    }


def _unique(items: Sequence[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _worst(values: Sequence[str], rank: dict[str, int], default: str) -> str:
    if not values:
        return default
    return max(values, key=lambda item: rank.get(item, -1))


def aggregate_candidate_results(
    payloads: Sequence[dict[str, object]],
    *,
    verify_job_result: str,
) -> dict[str, object]:
    """Combine matrix legs. FAILED wins over BLOCKED over READY_FOR_TAG."""
    if not payloads:
        return serialize_candidate_result(
            verification_status=VERIFICATION_FAIL,
            eligibility_status=ELIGIBILITY_NOT_EVALUATED,
            disposition=RESULT_FAILED,
            blockers=[],
            failures=["one or more Python 3.11/3.12 legs did not produce a candidate result"],
        ) | {"legs": []}

    blockers: list[str] = []
    failures: list[str] = []
    legs: list[dict[str, object]] = []
    dispositions: list[str] = []
    eligibilities: list[str] = []
    for payload in payloads:
        disposition = str(payload.get("disposition") or payload.get("result") or "")
        eligibility = str(payload.get("eligibility_status") or ELIGIBILITY_NOT_EVALUATED)
        raw_blockers = payload.get("blockers") or []
        raw_failures = payload.get("failures") or []
        if isinstance(raw_blockers, list):
            blockers.extend(str(item) for item in raw_blockers)
        if isinstance(raw_failures, list):
            failures.extend(str(item) for item in raw_failures)
        if disposition:
            dispositions.append(disposition)
        if eligibility:
            eligibilities.append(eligibility)
        legs.append(
            {
                "python_version": payload.get("python_version", ""),
                "verification_status": payload.get("verification_status", ""),
                "eligibility_status": eligibility,
                "disposition": disposition,
            }
        )

    seen_legs = {str(leg.get("python_version") or "") for leg in legs}
    for label in SUPPORTED_PYTHON_VERSIONS:
        if label not in seen_legs:
            failures.append(f"no candidate result for Python {label}")

    if verify_job_result != "success" and RESULT_FAILED not in dispositions:
        failures.append("one or more Python 3.11/3.12 verification legs did not complete")

    disposition = derive_candidate_disposition(failures, blockers)
    eligibility = derive_eligibility_status(
        evaluated=any(item != ELIGIBILITY_NOT_EVALUATED for item in eligibilities),
        blockers=blockers,
    )
    if eligibilities and not blockers:
        eligibility = _worst(eligibilities, _ELIGIBILITY_RANK, eligibility)

    result = serialize_candidate_result(
        verification_status=derive_verification_status(failures),
        eligibility_status=eligibility,
        disposition=disposition,
        blockers=blockers,
        failures=failures,
    )
    result["legs"] = legs
    return result


def format_workflow_summary(combined: dict[str, object]) -> str:
    """Operator-facing GitHub step summary. Never an ambiguous green."""
    disposition = str(combined.get("disposition") or combined.get("result") or RESULT_BLOCKED)
    verification = str(combined.get("verification_status") or VERIFICATION_FAIL)
    eligibility = str(combined.get("eligibility_status") or ELIGIBILITY_NOT_EVALUATED)
    lines = ["RELEASE CANDIDATE VERIFICATION", ""]
    legs = combined.get("legs") or []
    if isinstance(legs, list):
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            python = str(leg.get("python_version") or "")
            status = str(leg.get("verification_status") or "")
            if python:
                lines.append(f"Python {python}:")
                lines.append(status or "UNKNOWN")
                lines.append("")
    lines.extend(
        [
            f"Verification: {verification}",
            f"Eligibility: {eligibility}",
            f"Disposition: {disposition}",
            f"RESULT: {disposition}",
            "",
            "Blockers:",
        ]
    )
    blockers = combined.get("blockers") or []
    if isinstance(blockers, list) and blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "Failures:"])
    failures = combined.get("failures") or []
    if isinstance(failures, list) and failures:
        for item in failures:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    if disposition == RESULT_READY:
        lines.append(
            "READY_FOR_TAG means verification evidence is complete. "
            "It is not authorization to create a tag or publish."
        )
    elif disposition == RESULT_BLOCKED:
        lines.append("BLOCKED is a valid verification outcome, not a verification malfunction.")
    else:
        lines.append("FAILED means verification or evidence generation did not succeed.")
    return "\n".join(lines) + "\n"
