"""Deterministic internal price-review bundle.

Dev Order: CNC-JOB-QUOTE-PRICE-REVIEW-001

The bundle is not a customer deliverable and not a quote packet. Publishing
reuses the exclusive packet publisher without changing that publisher.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError
from business.workflows.price_review_models import (
    PriceReviewFailureError,
    PriceReviewRecord,
    PriceReviewRefusalError,
    ReviewedSubject,
)
from business.workflows.reporting import dumps_json, publish_packet


def review_payload(record: PriceReviewRecord) -> dict[str, object]:
    """JSON-ready review. It does not include a digest of itself or of review.md."""
    subject = record.subject
    return {
        "record_type": record.record_type,
        "record_version": record.record_version,
        "review_id": record.review_id,
        "reviewed_at": record.reviewed_at,
        "reviewer_ref": record.reviewer_ref,
        "reviewer_role": record.reviewer_role,
        "decision": record.decision,
        "reason": record.reason,
        "internal_notes": list(record.internal_notes),
        "authority": record.authority,
        "reviewer_identity_assurance": record.reviewer_identity_assurance,
        "cost_basis_acknowledgment": record.cost_basis_acknowledgment,
        "subject": _subject_payload(subject),
        "proposal_sha256": record.proposal_sha256,
        "review_request_sha256": record.review_request_sha256,
        "verification_sha256": record.verification_sha256,
        "verification_contract": record.verification_contract,
        "verification_authority": record.verification_authority,
    }


def render_review_markdown(record: PriceReviewRecord) -> str:
    """Internal summary. It states the asserted-identity limitation."""
    subject = record.subject
    lines = [
        "# Internal price review",
        "",
        "This bundle records a caller-asserted human price decision.",
        "It does not authenticate the reviewer, the role, or any approval authority.",
        "The decision approve_price does not authorize sending the proposal",
        "and does not release manufacturing.",
        "No consumer may treat this unsigned record as an authenticated approval,",
        "a customer-send permission, or a manufacturing-release token.",
        "",
        f"Review ID: {_literal_markdown(record.review_id)}",
        f"Reviewed at: {_literal_markdown(record.reviewed_at)}",
        f"Decision: {_literal_markdown(record.decision)}",
        f"Reviewer ref: {_literal_markdown(record.reviewer_ref)}",
        f"Reviewer role: {_literal_markdown(record.reviewer_role)}",
        f"Reviewer identity assurance: {_literal_markdown(record.reviewer_identity_assurance)}",
        f"Authority: {_literal_markdown(record.authority)}",
        f"Cost basis acknowledgment: {_literal_markdown(record.cost_basis_acknowledgment)}",
        "",
        "## Subject",
        "",
        f"Packet version: {_literal_markdown(subject.packet_version)}",
        f"Economic status: {_literal_markdown(subject.economic_status)}",
        f"Manifest SHA-256: {_literal_markdown(subject.manifest_sha256)}",
        f"Job ID: {_literal_markdown(subject.job_id)}",
        f"Estimate ID: {_literal_markdown(subject.estimate_id)}",
        f"Bid ID: {_literal_markdown(subject.bid_id)}",
        f"Proposal ID: {_literal_markdown(subject.proposal_id)}",
        f"Revision: {_literal_markdown(subject.revision)}",
        f"Currency: {_literal_markdown(subject.currency)}",
        f"Quantity: {subject.quantity}",
        f"Quote price: {subject.quote_price:.2f}",
        "",
        "The quoted amount was compared with the captured proposal and bid.",
        "This record does not reprice the packet and does not repeat internal cost detail.",
        "The direct-manufacturing-cost-only disclosure was acknowledged.",
        "That disclosure does not make the cost basis commercially complete.",
        "",
        "## Digests",
        "",
        f"Proposal SHA-256: {_literal_markdown(record.proposal_sha256)}",
        f"Review request SHA-256: {_literal_markdown(record.review_request_sha256)}",
        f"Verification SHA-256: {_literal_markdown(record.verification_sha256)}",
        f"Verification contract: {_literal_markdown(record.verification_contract)}",
        f"Verification authority: {_literal_markdown(record.verification_authority)}",
        "",
        "## Rationale",
        "",
        _literal_markdown(record.reason),
        "",
        "## Internal notes",
        "",
    ]
    if record.internal_notes:
        lines.extend(f"- {_literal_markdown(note)}" for note in record.internal_notes)
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def _literal_markdown(value: str) -> str:
    """Present supplied text literally, without Markdown or raw HTML structure."""
    escaped = re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", value)
    escaped = html.escape(escaped, quote=False)
    escaped = escaped.replace("\r", "&#13;").replace("\n", "&#10;").replace("\t", "&#9;")
    return re.sub(r"^ +", lambda match: "&#32;" * len(match.group()), escaped)


def bundle_files(
    *,
    request_bytes: bytes,
    verification_bytes: bytes,
    record: PriceReviewRecord,
) -> dict[str, bytes]:
    """Four internal files. review.json does not hash itself or review.md."""
    return {
        "review_request.json": request_bytes,
        "verification.json": verification_bytes,
        "review.json": dumps_json(review_payload(record)),
        "review.md": render_review_markdown(record).encode("utf-8"),
    }


def publish_review_bundle(destination: Path, files: dict[str, bytes]) -> None:
    """Publish outside the quote packet. Existing destinations survive unchanged."""
    try:
        publish_packet(destination, files)
    except JobQuoteRefusalError:
        raise PriceReviewRefusalError("OUTPUT_EXISTS") from None
    except JobQuoteFailureError:
        raise PriceReviewFailureError("review bundle could not be published") from None


def _subject_payload(subject: ReviewedSubject) -> dict[str, object]:
    return {
        "packet_version": subject.packet_version,
        "manifest_sha256": subject.manifest_sha256,
        "job_id": subject.job_id,
        "estimate_id": subject.estimate_id,
        "bid_id": subject.bid_id,
        "proposal_id": subject.proposal_id,
        "revision": subject.revision,
        "currency": subject.currency,
        "quantity": subject.quantity,
        "quote_price": subject.quote_price,
        "economic_status": subject.economic_status,
    }
