"""Customer-facing proposal models.

Dev Order: CNC-BID-CORE-3

These models represent customer-facing proposals, NOT internal bid records.
Internal margin, risk factors, and contingency details should NOT appear here.
"""

from dataclasses import dataclass, field
from enum import Enum


class ProposalStatus(str, Enum):
    """Proposal lifecycle status."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    SENT = "sent"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ProposalPricingV1:
    """Customer-facing pricing summary."""

    total_price: float
    price_per_unit: float
    quantity: int
    currency: str = "USD"
    pricing_note: str = ""


@dataclass(frozen=True)
class ProposalSectionV1:
    """A section of the proposal document."""

    title: str
    body: str
    bullets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProposalAssumptionV1:
    """A customer-visible assumption underlying the proposal."""

    statement: str
    customer_visible: bool = True


@dataclass(frozen=True)
class ProposalTermV1:
    """A term or condition of the proposal."""

    title: str
    statement: str


@dataclass
class ProposalV1:
    """Customer-facing proposal document."""

    proposal_id: str
    source_bid_id: str
    project_name: str
    customer_name: str
    revision: str
    status: str
    created_at: str
    pricing: ProposalPricingV1
    sections: list[ProposalSectionV1]
    assumptions: list[ProposalAssumptionV1]
    exclusions: list[str]
    terms: list[ProposalTermV1]
    next_steps: list[str]
    notes: list[str] = field(default_factory=list)
    source_summary_ref: str | None = None
    project_ref: str | None = None
