"""Build a BidSummaryV1 from a BidV2 without repricing.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-002

The summary's open category strings carry all 17 audit lines. Scalar totals
are copied from the bid. This module does not call the pricing functions.
"""

from __future__ import annotations

from business.bids.models_v2 import BidV2
from business.bids.summary import (
    BidSummaryAssumptionV1,
    BidSummaryLineItemV1,
    BidSummaryRiskV1,
    BidSummaryV1,
)


def generate_bid_summary_v2(bid: BidV2) -> BidSummaryV1:
    """Copy BidV2 audit lines and canonical prices into the existing summary."""
    line_items = [
        BidSummaryLineItemV1(
            name=item.name,
            category=item.category,
            quantity=item.quantity,
            unit=item.unit,
            unit_cost=item.unit_cost,
            total_cost=item.total_cost,
            note=item.note,
        )
        for item in bid.line_items
    ]
    base_cost = bid.cost_basis.base_manufacturing_cost
    assumptions = [
        BidSummaryAssumptionV1(
            field=item.field,
            value=item.value,
            source=item.source,
            confidence=item.confidence,
            note=item.note,
        )
        for item in bid.assumptions
    ]
    return BidSummaryV1(
        bid_id=bid.bid_id,
        project_name=bid.project_name,
        customer_name=bid.customer_name,
        revision=bid.revision,
        status=bid.status,
        quantity=bid.pricing.quantity,
        canonical_quote_price=bid.pricing.quote_price,
        canonical_price_per_unit=bid.pricing.price_per_unit,
        base_manufacturing_cost=base_cost,
        risked_cost=bid.pricing.risked_cost,
        target_margin_pct=bid.pricing.target_margin_pct,
        line_items=line_items,
        risk_factors=_risk_factors(bid, base_cost),
        assumptions=assumptions,
        notes=list(bid.notes),
        rounded_quote_price=None,
        rounded_price_per_unit=None,
    )


def _risk_factors(bid: BidV2, base_cost: float) -> list[BidSummaryRiskV1]:
    """Copy additive factors that are actually non-zero. This workflow leaves them at zero."""
    factors: list[BidSummaryRiskV1] = []
    named = (
        ("tool_wear", bid.pricing.tool_wear_pct),
        ("manufacturing_contingency", bid.pricing.manufacturing_contingency_pct),
        ("business_overhead", bid.pricing.business_overhead_pct),
        ("engineering_recovery", bid.pricing.engineering_recovery_pct),
    )
    for name, percentage in named:
        if percentage > 0:
            factors.append(
                BidSummaryRiskV1(
                    name=name,
                    percentage=percentage,
                    contribution=round(base_cost * percentage / 100, 2),
                )
            )
    return factors
