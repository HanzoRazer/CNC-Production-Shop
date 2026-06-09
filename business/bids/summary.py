"""Bid summary models.

Dev Order: CNC-BID-CORE-2

These models represent internal bid summaries for review,
not customer-facing proposals.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BidSummaryLineItemV1:
    """Line item in bid summary (copied from BidV1)."""

    name: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    note: str = ""


@dataclass(frozen=True)
class BidSummaryRiskV1:
    """Risk factor with percentage and dollar contribution."""

    name: str
    percentage: float
    contribution: float
    note: str = ""


@dataclass(frozen=True)
class BidSummaryAssumptionV1:
    """Assumption in bid summary (copied from BidV1)."""

    field: str
    value: str | float | int | bool | None
    source: str
    confidence: str
    note: str = ""


@dataclass
class BidSummaryV1:
    """Internal bid summary for review."""

    bid_id: str
    project_name: str
    customer_name: str
    revision: str
    status: str
    quantity: int
    canonical_quote_price: float
    canonical_price_per_unit: float
    base_manufacturing_cost: float
    risked_cost: float
    target_margin_pct: float
    line_items: list[BidSummaryLineItemV1]
    risk_factors: list[BidSummaryRiskV1]
    assumptions: list[BidSummaryAssumptionV1]
    notes: list[str] = field(default_factory=list)
    rounded_quote_price: float | None = None
    rounded_price_per_unit: float | None = None
