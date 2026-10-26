"""Typed records for the job quote workflow.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-001
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from business.bids.models import BidV1

WORKFLOW_VERSION = "1.0.0"
MAPPING_VERSION = "1.0.0"
POLICY_ID = "target_margin"
POLICY_VERSION = "1.0.0"
RECORD_VERSION = "1.0.0"
REQUEST_RECORD_TYPE = "cnc_job_quote_request"
MANIFEST_RECORD_TYPE = "cnc_job_quote_manifest"
ESTIMATE_INPUT_CONTRACT = "guitar_estimate_input_v1"
COST_BASIS_DISCLOSURE = "direct_manufacturing_cost_only"
PACKET_MANUFACTURING_REF = "internal/estimate.json"
SOURCE_SNAPSHOT_ROOT = "internal/sources"
DRAFT_STATUS = "draft"
DRAFT_FOR_REVIEW_NOTICE = (
    "DRAFT FOR REVIEW. This proposal is an unapproved draft for human review. "
    "It is not a price approval, a customer commitment, or a manufacturing release."
)
DEFAULT_PACKAGING_PROMISE = "Packaging for safe transport"


class JobQuoteRefusalError(Exception):
    """Invalid invocation or input. The CLI exits 2 and writes no packet."""


class JobQuoteFailureError(Exception):
    """Output I/O or an unexpected workflow failure. The CLI exits 1."""


@dataclass(frozen=True)
class PricingPolicyV1:
    """Caller-supplied target-margin policy. Additional percentages are not accepted."""

    policy_id: str
    policy_version: str
    target_margin_pct: float


@dataclass(frozen=True)
class JobQuoteRequestV1:
    """Validated operator request. Identifiers are not filesystem paths."""

    job_id: str
    estimate_id: str
    bid_id: str
    proposal_id: str
    project_name: str
    customer_name: str
    revision: str
    created_at: str
    effective_date: str
    estimate_input_contract: str
    estimate_input_ref: str
    quantity: int
    currency: str
    pricing_policy: PricingPolicyV1
    customer_deliverables: tuple[str, ...]
    customer_exclusions: tuple[str, ...]
    internal_notes: tuple[str, ...]


@dataclass(frozen=True)
class SourceSnapshot:
    """One source file captured before calculation."""

    role: str
    record_id: str
    original_ref: str
    raw_bytes: bytes
    sha256: str

    @property
    def snapshot_ref(self) -> str:
        return f"{SOURCE_SNAPSHOT_ROOT}/{self.original_ref}"


@dataclass(frozen=True)
class LoadedJobQuote:
    """Immutable request plus the source bytes it names."""

    request: JobQuoteRequestV1
    job_ref: str
    sources: tuple[SourceSnapshot, ...]


@dataclass(frozen=True)
class CategoryMappingLineV1:
    """One source cost category and the bid field it contributes to."""

    source_category: str
    source_amount: float
    bid_field: str
    mapped_amount: float


@dataclass(frozen=True)
class EstimateToBidResult:
    """Bid constructed from an estimate, plus the mapping used to build it."""

    bid: BidV1
    lines: tuple[CategoryMappingLineV1, ...]
    mapped_amounts: tuple[tuple[str, float], ...]
    estimate_total: float
    mapped_total: float
    audit_total: float
    difference: float


@dataclass(frozen=True)
class JobQuotePacket:
    """Validated packet bytes, relative to the output directory."""

    files: dict[str, bytes]
    job_id: str
    direct_manufacturing_cost: float
    quote_price: float


@dataclass(frozen=True)
class JobQuoteResult:
    """A published draft packet."""

    job_id: str
    status: str
    direct_manufacturing_cost: float
    quote_price: float
    output_dir: Path
    customer_proposal_json: Path
    customer_proposal_markdown: Path
