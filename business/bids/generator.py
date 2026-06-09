"""Bid summary generator.

Dev Order: CNC-BID-CORE-2

Generates internal bid summaries from BidV1 records.
Does not produce customer-facing proposals.
"""

from business.bids.models import BidV1
from business.bids.summary import (
    BidSummaryAssumptionV1,
    BidSummaryLineItemV1,
    BidSummaryRiskV1,
    BidSummaryV1,
)


def generate_bid_summary(bid: BidV1) -> BidSummaryV1:
    """Generate an internal bid summary from a BidV1 record.

    Args:
        bid: The source BidV1 record

    Returns:
        BidSummaryV1 with organized summary data

    Notes:
        - Does not mutate input bid
        - Does not recalculate pricing
        - Preserves canonical pricing from BidV1
        - Sets rounded prices to None (manual entry in fixture if needed)
        - Does not parse notes for money values
    """
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

    risk_factors = _extract_risk_factors(bid, base_cost)

    assumptions = [
        BidSummaryAssumptionV1(
            field=a.field,
            value=a.value,
            source=a.source,
            confidence=a.confidence,
            note=a.note,
        )
        for a in bid.assumptions
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
        risk_factors=risk_factors,
        assumptions=assumptions,
        notes=list(bid.notes),
        rounded_quote_price=None,
        rounded_price_per_unit=None,
    )


def _extract_risk_factors(bid: BidV1, base_cost: float) -> list[BidSummaryRiskV1]:
    """Extract risk factors with dollar contributions.

    Args:
        bid: Source BidV1
        base_cost: Base manufacturing cost for contribution calculation

    Returns:
        List of risk factors with name, percentage, and contribution
    """
    factors = []

    if bid.pricing.tool_wear_pct > 0:
        factors.append(
            BidSummaryRiskV1(
                name="tool_wear",
                percentage=bid.pricing.tool_wear_pct,
                contribution=round(base_cost * bid.pricing.tool_wear_pct / 100, 2),
            )
        )

    if bid.pricing.manufacturing_contingency_pct > 0:
        factors.append(
            BidSummaryRiskV1(
                name="manufacturing_contingency",
                percentage=bid.pricing.manufacturing_contingency_pct,
                contribution=round(
                    base_cost * bid.pricing.manufacturing_contingency_pct / 100, 2
                ),
            )
        )

    if bid.pricing.business_overhead_pct > 0:
        factors.append(
            BidSummaryRiskV1(
                name="business_overhead",
                percentage=bid.pricing.business_overhead_pct,
                contribution=round(
                    base_cost * bid.pricing.business_overhead_pct / 100, 2
                ),
            )
        )

    if bid.pricing.engineering_recovery_pct > 0:
        factors.append(
            BidSummaryRiskV1(
                name="engineering_recovery",
                percentage=bid.pricing.engineering_recovery_pct,
                contribution=round(
                    base_cost * bid.pricing.engineering_recovery_pct / 100, 2
                ),
            )
        )

    return factors
