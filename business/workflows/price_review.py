"""Record one caller-asserted price decision against a verified draft packet.

Dev Order: CNC-JOB-QUOTE-PRICE-REVIEW-001

The command verifies the packet once with the digest in the request, compares
the stated subject with that capture, and publishes a new internal bundle.
It does not authenticate the reviewer or change the quote packet.
"""

from __future__ import annotations

import errno
import hashlib
import math
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from business.calculators.machine_cost_basis import as_money, money_equal
from business.workflows.loading import parse_json_object, validate_instance
from business.workflows.models import JobQuoteRefusalError
from business.workflows.price_review_models import (
    COST_ACKNOWLEDGMENT,
    PriceReviewFailureError,
    PriceReviewRecord,
    PriceReviewRefusalError,
    RecordedPriceReview,
    ReviewedSubject,
)
from business.workflows.price_review_reporting import (
    bundle_files,
    publish_review_bundle,
    review_payload,
)
from business.workflows.reporting import dumps_json
from business.workflows.verification import ensure_captured_unchanged, require_verified_packet
from business.workflows.verification_models import (
    PacketRejectedError,
    verification_payload,
)

_REQUEST_SCHEMA = "workflows/job_quote_price_review_request_v1.schema.json"
_RESULT_SCHEMA = "workflows/job_quote_price_review_v1.schema.json"
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ZERO_FACTORS = (
    "tool_wear_pct",
    "manufacturing_contingency_pct",
    "business_overhead_pct",
    "engineering_recovery_pct",
)


def record_price_review(
    *,
    packet_dir: str,
    request_path: str,
    output_dir: str,
) -> RecordedPriceReview:
    """Verify one retained subject and publish a new internal review bundle.

    Relative paths resolve against the current working directory. The manifest
    digest comes from the request. This function does not compute a substitute.
    """
    request_bytes = _read_request(request_path)
    request = _admit_request(request_bytes)
    destination = _resolve_output(packet_dir, output_dir)
    try:
        verified = require_verified_packet(
            packet_dir,
            str(request["expected_manifest_sha256"]),
        )
    except PacketRejectedError as exc:
        diagnostic = exc.verification.errors[0].code if exc.verification.errors else "INVALID"
        raise PriceReviewRefusalError(f"VERIFICATION_REJECTED {diagnostic}") from None
    captured = verified.captured
    subject = _matched_subject(request, captured.files, verified.verification)
    _require_chronology(str(request["reviewed_at"]), captured.files)
    verification_bytes = dumps_json(verification_payload(verified.verification))
    proposal_bytes = captured.files["customer/proposal.json"]
    record = PriceReviewRecord(
        review_id=str(request["review_id"]),
        reviewed_at=str(request["reviewed_at"]),
        reviewer_ref=str(request["reviewer_ref"]),
        reviewer_role=str(request["reviewer_role"]),
        decision=str(request["decision"]),
        reason=str(request["reason"]),
        internal_notes=tuple(str(note) for note in request["internal_notes"]),
        subject=subject,
        proposal_sha256=hashlib.sha256(proposal_bytes).hexdigest(),
        review_request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        verification_sha256=hashlib.sha256(verification_bytes).hexdigest(),
    )
    _require_bound_hashes(record, captured.files, proposal_bytes)
    try:
        validate_instance(review_payload(record), _RESULT_SCHEMA, label="price review")
    except JobQuoteRefusalError:
        raise PriceReviewFailureError("price review result failed its contract") from None
    try:
        ensure_captured_unchanged(verified)
    except PacketRejectedError:
        raise PriceReviewRefusalError("PACKET_CHANGED") from None
    files = bundle_files(
        request_bytes=request_bytes,
        verification_bytes=verification_bytes,
        record=record,
    )
    publish_review_bundle(destination, files)
    return RecordedPriceReview(
        review_id=record.review_id,
        decision=record.decision,
        quote_price=subject.quote_price,
        manifest_sha256=subject.manifest_sha256,
        output_dir=destination.as_posix(),
    )


def _read_request(request_path: str) -> bytes:
    if not request_path or request_path.strip() != request_path:
        raise PriceReviewRefusalError("REQUEST_INVALID")
    path = Path(request_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise PriceReviewRefusalError("REQUEST_INVALID") from None
    except OSError:
        raise PriceReviewFailureError("price review request could not be read") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PriceReviewRefusalError("REQUEST_UNSAFE")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise PriceReviewRefusalError("REQUEST_INVALID") from None
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise PriceReviewRefusalError("REQUEST_UNSAFE") from None
        raise PriceReviewFailureError("price review request could not be read") from None
    try:
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()
    except OSError:
        raise PriceReviewFailureError("price review request could not be read") from None


def _admit_request(raw: bytes) -> dict[str, Any]:
    try:
        payload = parse_json_object(raw, label="price review request")
        validate_instance(payload, _REQUEST_SCHEMA, label="price review request")
    except JobQuoteRefusalError:
        raise PriceReviewRefusalError("REQUEST_INVALID") from None
    price = payload["reviewed_subject"]["quote_price"]
    if not _cent_valued(price):
        raise PriceReviewRefusalError("REQUEST_INVALID")
    reviewed_at = str(payload["reviewed_at"])
    if _parse_utc(reviewed_at) is None:
        raise PriceReviewRefusalError("REQUEST_INVALID")
    return payload


def _resolve_output(packet_dir: str, output_dir: str) -> Path:
    if (
        not output_dir
        or output_dir.strip() != output_dir
        or "://" in output_dir
        or "\\" in output_dir
    ):
        raise PriceReviewRefusalError("OUTPUT_REFUSED")
    candidate = Path(output_dir)
    if ".." in candidate.parts:
        raise PriceReviewRefusalError("OUTPUT_REFUSED")
    lexical = candidate if candidate.is_absolute() else Path.cwd() / candidate
    if ".." in lexical.parts:
        raise PriceReviewRefusalError("OUTPUT_REFUSED")
    parts = lexical.parts[1:] if lexical.is_absolute() else candidate.parts
    current = Path(lexical.anchor) if lexical.is_absolute() else Path.cwd()
    for index, part in enumerate(parts):
        if part in {"", ".", ".."}:
            raise PriceReviewRefusalError("OUTPUT_REFUSED")
        current = current / part
        try:
            if current.is_symlink():
                raise PriceReviewRefusalError("OUTPUT_REFUSED")
        except OSError:
            raise PriceReviewFailureError("review output could not be inspected") from None
        if index < len(parts) - 1 and current.exists() and not current.is_dir():
            raise PriceReviewRefusalError("OUTPUT_REFUSED")
    if current.exists():
        raise PriceReviewRefusalError("OUTPUT_EXISTS")
    packet = Path(packet_dir)
    if not packet.is_absolute():
        packet = Path.cwd() / packet
    try:
        resolved_output = current.resolve()
        resolved_packet = packet.resolve()
    except OSError:
        raise PriceReviewFailureError("review output could not be inspected") from None
    if _overlaps(resolved_output, resolved_packet):
        raise PriceReviewRefusalError("OUTPUT_REFUSED")
    return resolved_output


def _matched_subject(
    request: dict[str, Any],
    files: dict[str, bytes],
    verification: Any,
) -> ReviewedSubject:
    stated = request["reviewed_subject"]
    manifest = _object(files["manifest.json"], "manifest")
    proposal = _object(files["customer/proposal.json"], "proposal")
    bid = _object(files["internal/bid.json"], "bid")
    _require_text(stated, manifest, "job_id", verification.job_id)
    _require_text(stated, manifest, "estimate_id", verification.estimate_id)
    _require_text(stated, manifest, "bid_id", verification.bid_id)
    _require_text(stated, manifest, "proposal_id", verification.proposal_id)
    if proposal.get("proposal_id") != stated["proposal_id"]:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH proposal_id")
    if bid.get("bid_id") != stated["bid_id"] or proposal.get("source_bid_id") != stated["bid_id"]:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH bid_id")
    if proposal.get("revision") != stated["revision"]:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH revision")
    pricing = proposal.get("pricing")
    bid_pricing = bid.get("pricing")
    if not isinstance(pricing, dict) or not isinstance(bid_pricing, dict):
        raise PriceReviewRefusalError("SUBJECT_MISMATCH quote_price")
    if pricing.get("currency") != "USD" or stated["currency"] != "USD":
        raise PriceReviewRefusalError("SUBJECT_MISMATCH currency")
    quantity = stated["quantity"]
    if pricing.get("quantity") != 1 or quantity != 1 or type(quantity) is not int:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH quantity")
    stated_price = stated["quote_price"]
    if (
        not money_equal(stated_price, pricing.get("total_price"))
        or not money_equal(stated_price, pricing.get("price_per_unit"))
        or not money_equal(stated_price, bid_pricing.get("quote_price"))
    ):
        raise PriceReviewRefusalError("SUBJECT_MISMATCH quote_price")
    if (
        verification.economic_status != "draft"
        or manifest.get("status") != "draft"
        or proposal.get("status") != "draft"
        or bid.get("status") != "draft"
    ):
        raise PriceReviewRefusalError("SUBJECT_MISMATCH economic_status")
    _require_direct_cost_only(manifest, bid_pricing)
    if verification.manifest_sha256 != request["expected_manifest_sha256"]:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH manifest_sha256")
    if verification.packet_version not in {"1.0.0", "2.0.0"}:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH packet_version")
    return ReviewedSubject(
        packet_version=str(verification.packet_version),
        manifest_sha256=str(verification.manifest_sha256),
        job_id=str(stated["job_id"]),
        estimate_id=str(stated["estimate_id"]),
        bid_id=str(stated["bid_id"]),
        proposal_id=str(stated["proposal_id"]),
        revision=str(stated["revision"]),
        currency="USD",
        quantity=1,
        quote_price=as_money(pricing["total_price"]),
        economic_status="draft",
    )


def _require_direct_cost_only(manifest: dict[str, Any], bid_pricing: dict[str, Any]) -> None:
    disclosure = manifest.get("cost_basis_disclosure")
    if not isinstance(disclosure, dict):
        raise PriceReviewRefusalError("SUBJECT_MISMATCH cost_basis")
    if disclosure.get("basis") != COST_ACKNOWLEDGMENT:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH cost_basis")
    for name in _ZERO_FACTORS:
        if disclosure.get(name) != 0 or not _is_zero(bid_pricing.get(name)):
            raise PriceReviewRefusalError("SUBJECT_MISMATCH cost_basis")


def _require_chronology(reviewed_at: str, files: dict[str, bytes]) -> None:
    job = _object(files["internal/job_request.json"], "job request")
    created = _parse_utc(str(job.get("created_at")))
    reviewed = _parse_utc(reviewed_at)
    if created is None or reviewed is None or reviewed < created:
        raise PriceReviewRefusalError("REVIEWED_AT_BEFORE_CREATION")


def _require_bound_hashes(
    record: PriceReviewRecord,
    files: dict[str, bytes],
    proposal_bytes: bytes,
) -> None:
    manifest = _object(files["manifest.json"], "manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise PriceReviewRefusalError("SUBJECT_MISMATCH proposal_sha256")
    entry = next(
        (
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("path") == "customer/proposal.json"
        ),
        None,
    )
    if not isinstance(entry, dict) or entry.get("sha256") != record.proposal_sha256:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH proposal_sha256")
    if hashlib.sha256(proposal_bytes).hexdigest() != record.proposal_sha256:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH proposal_sha256")


def _require_text(
    stated: dict[str, Any],
    manifest: dict[str, Any],
    field: str,
    admitted: str | None,
) -> None:
    if stated.get(field) != manifest.get(field) or stated.get(field) != admitted:
        raise PriceReviewRefusalError(f"SUBJECT_MISMATCH {field}")


def _object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return parse_json_object(raw, label=label)
    except JobQuoteRefusalError:
        raise PriceReviewRefusalError("SUBJECT_MISMATCH") from None


def _cent_valued(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        amount = float(value)
    except OverflowError:
        return False
    if not math.isfinite(amount) or amount < 0:
        return False
    cents = amount * 100
    if not math.isfinite(cents):
        return False
    return abs(cents - round(cents)) <= 1e-6


def _is_zero(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return float(value) == 0.0


def _parse_utc(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, _UTC_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def _overlaps(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
    except ValueError:
        return False
    return True
