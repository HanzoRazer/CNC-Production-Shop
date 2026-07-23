"""Bid calculation, record models, and summary generation.

Dev Order: CNC-BID-CORE-1, CNC-BID-CORE-2, CNC-MACHINE-COST-WIRING-1

Public construction surface for opt-in machine costing (intentional):
    MachineCostingV1, build_machine_costing, derive_machine_time_cost

These helpers are the supported way to attach a governed technical machine-cost
derivation to BidV1. They are not commercial pricing APIs.
"""

from business.bids.calculator import (
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
)
from business.bids.generator import generate_bid_summary
from business.bids.machine_costing import (
    build_machine_costing,
    derive_machine_time_cost,
)
from business.bids.models import (
    BidAssumptionV1,
    BidCostBasisV1,
    BidLineItemV1,
    BidPricingV1,
    BidStatus,
    BidV1,
    MachineCostingV1,
)
from business.bids.summary import (
    BidSummaryAssumptionV1,
    BidSummaryLineItemV1,
    BidSummaryRiskV1,
    BidSummaryV1,
)

__all__ = [
    "BidAssumptionV1",
    "BidCostBasisV1",
    "BidLineItemV1",
    "BidPricingV1",
    "BidStatus",
    "BidSummaryAssumptionV1",
    "BidSummaryLineItemV1",
    "BidSummaryRiskV1",
    "BidSummaryV1",
    "BidV1",
    "MachineCostingV1",
    "build_machine_costing",
    "calculate_bid_price",
    "calculate_price_per_unit",
    "calculate_risked_cost",
    "derive_machine_time_cost",
    "generate_bid_summary",
]
