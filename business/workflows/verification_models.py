"""Verification result records for a saved draft quote packet.

Dev Order: CNC-JOB-QUOTE-VERIFY-001

A valid result means the captured packet matches supported deterministic
generation. It is not a price approval, a customer commitment, or a
manufacturing release.
"""

from __future__ import annotations

from dataclasses import dataclass

RECORD_TYPE = "cnc_job_quote_verification"
RECORD_VERSION = "1.0.0"
AUTHORITY = "verification_only"
CHECK_NAMES = ("inventory", "schemas", "hashes", "source_closure", "replay")
CHECK_STATUSES = frozenset({"pass", "fail", "not_run"})
ANCHOR_STATUSES = frozenset({"matched", "mismatch", "not_supplied", "not_checked"})
DIAGNOSTIC_CODES = (
    "PACKET_NOT_FOUND",
    "UNSAFE_MEMBER",
    "UNSUPPORTED_CONTRACT",
    "SCHEMA_INVALID",
    "INVENTORY_MISMATCH",
    "DUPLICATE_ENTRY",
    "HASH_MISMATCH",
    "SOURCE_CLOSURE_MISMATCH",
    "REPLAY_MISMATCH",
    "ANCHOR_MISMATCH",
    "PACKET_CHANGED_DURING_READ",
)


@dataclass(frozen=True)
class VerificationCheck:
    """One fixed-order verification phase."""

    name: str
    status: str


@dataclass(frozen=True)
class VerificationDiagnostic:
    """A stable code and an optional packet-relative member path."""

    code: str
    member: str | None


@dataclass(frozen=True)
class JobQuoteVerification:
    """Internal evidence that a captured packet is consistent, or why it is not."""

    result: str
    manifest_sha256: str | None
    expected_manifest_sha256: str | None
    anchor_status: str
    packet_version: str | None
    economic_status: str | None
    job_id: str | None
    estimate_id: str | None
    bid_id: str | None
    proposal_id: str | None
    checks: tuple[VerificationCheck, ...]
    errors: tuple[VerificationDiagnostic, ...]
    record_type: str = RECORD_TYPE
    record_version: str = RECORD_VERSION
    authority: str = AUTHORITY

    def __post_init__(self) -> None:
        if self.record_type != RECORD_TYPE or self.record_version != RECORD_VERSION:
            raise ValueError("verification record identity is fixed")
        if self.authority != AUTHORITY:
            raise ValueError("verification authority is verification_only")
        if self.result not in {"valid", "invalid"}:
            raise ValueError("verification result must be valid or invalid")
        if self.anchor_status not in ANCHOR_STATUSES:
            raise ValueError("verification anchor_status is not supported")
        if tuple(check.name for check in self.checks) != CHECK_NAMES:
            raise ValueError("verification checks must stay in fixed order")
        for check in self.checks:
            if check.status not in CHECK_STATUSES:
                raise ValueError("verification check status is not supported")
        for error in self.errors:
            if error.code not in DIAGNOSTIC_CODES:
                raise ValueError("verification diagnostic code is not supported")
        statuses = [check.status for check in self.checks]
        if self.result == "valid":
            _require_valid(self, statuses)
        else:
            _require_invalid(self, statuses)
        _require_anchor(self)


class PacketRejectedError(Exception):
    """The packet is not a supported consistent draft. The CLI exits 2."""

    def __init__(self, verification: JobQuoteVerification) -> None:
        self.verification = verification
        super().__init__(verification.errors[0].code)


class VerificationOperationalError(Exception):
    """Unreadable input or temporary storage failed. The CLI exits 1."""


def checks_for(failed_phase: str | None) -> tuple[VerificationCheck, ...]:
    """Pass phases before the first failure. ``None`` passes every phase.

    An empty string leaves every phase ``not_run``.
    """
    if failed_phase is None:
        return tuple(VerificationCheck(name, "pass") for name in CHECK_NAMES)
    if failed_phase == "":
        return tuple(VerificationCheck(name, "not_run") for name in CHECK_NAMES)
    if failed_phase not in CHECK_NAMES:
        raise ValueError(f"unknown verification phase: {failed_phase}")
    failed_at = CHECK_NAMES.index(failed_phase)
    return tuple(
        VerificationCheck(
            name,
            "pass" if index < failed_at else "fail" if index == failed_at else "not_run",
        )
        for index, name in enumerate(CHECK_NAMES)
    )


def verification_payload(result: JobQuoteVerification) -> dict[str, object]:
    """JSON-ready result. Callers serialize it with the stable JSON writer."""
    return {
        "record_type": result.record_type,
        "record_version": result.record_version,
        "authority": result.authority,
        "result": result.result,
        "manifest_sha256": result.manifest_sha256,
        "expected_manifest_sha256": result.expected_manifest_sha256,
        "anchor_status": result.anchor_status,
        "packet_version": result.packet_version,
        "economic_status": result.economic_status,
        "job_id": result.job_id,
        "estimate_id": result.estimate_id,
        "bid_id": result.bid_id,
        "proposal_id": result.proposal_id,
        "checks": [{"name": check.name, "status": check.status} for check in result.checks],
        "errors": [{"code": error.code, "member": error.member} for error in result.errors],
    }


def format_verification_text(result: JobQuoteVerification) -> str:
    """Human summary. It contains no absolute paths and no packet contents."""
    lines = [
        f"result: {result.result}",
        f"authority: {result.authority}",
        f"packet_version: {_or_null(result.packet_version)}",
        f"economic_status: {_or_null(result.economic_status)}",
        f"anchor_status: {result.anchor_status}",
        f"manifest_sha256: {_or_null(result.manifest_sha256)}",
        f"job_id: {_or_null(result.job_id)}",
        f"estimate_id: {_or_null(result.estimate_id)}",
        f"bid_id: {_or_null(result.bid_id)}",
        f"proposal_id: {_or_null(result.proposal_id)}",
        "checks: " + " ".join(f"{check.name}={check.status}" for check in result.checks),
    ]
    for error in result.errors:
        member = error.member if error.member is not None else "-"
        lines.append(f"error: {error.code} {member}")
    return "\n".join(lines)


def _or_null(value: str | None) -> str:
    return value if value is not None else "null"


def _require_valid(result: JobQuoteVerification, statuses: list[str]) -> None:
    if result.errors or any(status != "pass" for status in statuses):
        raise ValueError("valid verification requires passing checks and no errors")
    if result.anchor_status not in {"matched", "not_supplied"}:
        raise ValueError("valid verification requires a matched or absent anchor")
    if result.economic_status != "draft":
        raise ValueError("valid verification stays draft")
    if result.packet_version not in {"1.0.0", "2.0.0"}:
        raise ValueError("valid verification requires a supported packet version")
    if result.manifest_sha256 is None:
        raise ValueError("valid verification requires a manifest digest")
    if result.expected_manifest_sha256 not in {None, result.manifest_sha256}:
        raise ValueError("valid verification anchor does not match the manifest")
    for ident in (result.job_id, result.estimate_id, result.bid_id, result.proposal_id):
        if not ident:
            raise ValueError("valid verification requires admitted ids")


def _require_invalid(result: JobQuoteVerification, statuses: list[str]) -> None:
    if not result.errors:
        raise ValueError("invalid verification requires a diagnostic")
    if all(status == "not_run" for status in statuses):
        return
    seen_fail = False
    for status in statuses:
        if status == "fail":
            if seen_fail:
                raise ValueError("only the first failed check is recorded")
            seen_fail = True
        elif seen_fail:
            if status != "not_run":
                raise ValueError("checks after a failure are not_run")
        elif status != "pass":
            raise ValueError("checks before a failure passed")
    if not seen_fail:
        raise ValueError("invalid verification has no failed check")


def _require_anchor(result: JobQuoteVerification) -> None:
    expected = result.expected_manifest_sha256
    digest = result.manifest_sha256
    if result.anchor_status == "not_supplied" and expected is not None:
        raise ValueError("not_supplied anchor includes a digest")
    if result.anchor_status == "matched" and (expected is None or expected != digest):
        raise ValueError("matched anchor does not equal the manifest digest")
    if result.anchor_status == "mismatch":
        if expected is None or digest is None or expected == digest:
            raise ValueError("anchor mismatch is not established")
        if "ANCHOR_MISMATCH" not in {error.code for error in result.errors}:
            raise ValueError("anchor mismatch requires its diagnostic")
    if result.anchor_status == "not_checked" and result.result == "valid":
        raise ValueError("valid verification cannot leave the anchor unchecked")
