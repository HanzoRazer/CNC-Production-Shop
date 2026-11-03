"""Typed records for a caller-asserted price review.

Dev Order: CNC-JOB-QUOTE-PRICE-REVIEW-001

Importing this module does not read the filesystem. A review record is not an
authenticated approval, a permission to send a proposal, or a manufacturing release.
"""

from __future__ import annotations

from dataclasses import dataclass

AUTHORITY = "caller_asserted_price_review_only"
IDENTITY_ASSURANCE = "caller_asserted"
COST_ACKNOWLEDGMENT = "direct_manufacturing_cost_only"
VERIFICATION_CONTRACT = "job_quote_verification_v1"
VERIFICATION_AUTHORITY = "verification_only"
DECISIONS = frozenset({"approve_price", "request_changes", "reject"})
RECORD_TYPE = "cnc_job_quote_price_review"
RECORD_VERSION = "1.0.0"


@dataclass(frozen=True)
class ReviewedSubject:
    """The captured draft subject a human decision names."""

    packet_version: str
    manifest_sha256: str
    job_id: str
    estimate_id: str
    bid_id: str
    proposal_id: str
    revision: str
    currency: str
    quantity: int
    quote_price: float
    economic_status: str


@dataclass(frozen=True)
class PriceReviewRecord:
    """Immutable internal review. It does not hash itself or the Markdown summary."""

    review_id: str
    reviewed_at: str
    reviewer_ref: str
    reviewer_role: str
    decision: str
    reason: str
    internal_notes: tuple[str, ...]
    subject: ReviewedSubject
    proposal_sha256: str
    review_request_sha256: str
    verification_sha256: str
    authority: str = AUTHORITY
    reviewer_identity_assurance: str = IDENTITY_ASSURANCE
    cost_basis_acknowledgment: str = COST_ACKNOWLEDGMENT
    verification_contract: str = VERIFICATION_CONTRACT
    verification_authority: str = VERIFICATION_AUTHORITY
    record_type: str = RECORD_TYPE
    record_version: str = RECORD_VERSION

    def __post_init__(self) -> None:
        if self.record_type != RECORD_TYPE or self.record_version != RECORD_VERSION:
            raise ValueError("price review record identity is fixed")
        if self.authority != AUTHORITY:
            raise ValueError("price review authority is caller-asserted only")
        if self.reviewer_identity_assurance != IDENTITY_ASSURANCE:
            raise ValueError("price review identity assurance is caller-asserted")
        if self.cost_basis_acknowledgment != COST_ACKNOWLEDGMENT:
            raise ValueError("price review cost acknowledgment is fixed")
        if self.verification_contract != VERIFICATION_CONTRACT:
            raise ValueError("price review verification contract is fixed")
        if self.verification_authority != VERIFICATION_AUTHORITY:
            raise ValueError("price review verification authority is fixed")
        if self.decision not in DECISIONS:
            raise ValueError("price review decision is not supported")
        if self.subject.economic_status != "draft":
            raise ValueError("price review subject stays draft")
        if self.subject.currency != "USD" or self.subject.quantity != 1:
            raise ValueError("price review subject is quantity 1 USD")
        if self.subject.packet_version not in {"1.0.0", "2.0.0"}:
            raise ValueError("price review subject packet version is not supported")


@dataclass(frozen=True)
class RecordedPriceReview:
    """Publication result. The decision is the caller's stated decision."""

    review_id: str
    decision: str
    quote_price: float
    manifest_sha256: str
    output_dir: str


class PriceReviewRefusalError(Exception):
    """The review was not recorded. The CLI exits 2."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PriceReviewFailureError(Exception):
    """The review bundle could not be published. The CLI exits 1."""
