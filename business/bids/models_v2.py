"""BidV2 records for thin-skin quotes.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-002

BidV2 is a separate contract from BidV1. It is not a subclass and it is not
serialized as a V1 bid. Equipment occupancy and the process reserve are their
own base-cost amounts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from business.bids.models import (
    BidAssumptionV1,
    BidLineItemV1,
    BidPricingV1,
    MachineCostingV1,
)
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.models_v2 import EquipmentOccupancyCostingV1

BID_V2_RECORD_TYPE = "cnc_bid"
BID_V2_RECORD_VERSION = "2.0.0"

_COST_FIELDS = (
    "direct_material_cost",
    "direct_labor_cost",
    "machine_time_cost",
    "tooling_cost",
    "setup_cost",
    "finishing_cost",
    "finishing_material_cost",
    "engineering_cost",
    "equipment_occupancy_cost",
    "process_rework_and_yield_reserve",
)


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite nonnegative number")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return amount


@dataclass(frozen=True)
class BidCostBasisV2:
    """Ten-field direct cost basis. The base is computed, not stored."""

    direct_material_cost: float
    direct_labor_cost: float
    machine_time_cost: float
    tooling_cost: float
    setup_cost: float
    finishing_cost: float
    finishing_material_cost: float
    engineering_cost: float
    equipment_occupancy_cost: float
    process_rework_and_yield_reserve: float

    def __post_init__(self) -> None:
        for name in _COST_FIELDS:
            _finite_nonnegative(getattr(self, name), name)

    @property
    def base_manufacturing_cost(self) -> float:
        """Cent-rounded sum of the ten cost-basis amounts."""
        return as_money(sum(getattr(self, name) for name in _COST_FIELDS))


@dataclass
class BidV2:
    """Internal thin-skin bid. Draft only, with explicit equipment evidence."""

    bid_id: str
    project_name: str
    customer_name: str
    revision: str
    status: str
    created_at: str
    updated_at: str
    assumptions: list[BidAssumptionV1]
    line_items: list[BidLineItemV1]
    cost_basis: BidCostBasisV2
    pricing: BidPricingV1
    equipment_costing: list[EquipmentOccupancyCostingV1]
    notes: list[str] = field(default_factory=list)
    project_ref: str | None = None
    manufacturing_ref: str | None = None
    scenario_ref: str | None = None
    machine_costing: MachineCostingV1 | None = None
    record_type: str = BID_V2_RECORD_TYPE
    record_version: str = BID_V2_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.record_type != BID_V2_RECORD_TYPE or self.record_version != BID_V2_RECORD_VERSION:
            raise ValueError("BidV2 record_type and record_version are fixed")
        if self.status != "draft":
            raise ValueError("BidV2 status must stay draft")
        pricing = self.pricing
        if pricing.quantity != 1:
            raise ValueError("BidV2 quantity must be 1")
        for name in (
            "tool_wear_pct",
            "manufacturing_contingency_pct",
            "business_overhead_pct",
            "engineering_recovery_pct",
        ):
            if getattr(pricing, name) != 0:
                raise ValueError(f"BidV2 {name} must be 0")
        if isinstance(pricing.target_margin_pct, bool) or not math.isfinite(
            float(pricing.target_margin_pct)
        ):
            raise ValueError("BidV2 target_margin_pct must be finite")
        if not 0 <= float(pricing.target_margin_pct) < 100:
            raise ValueError("BidV2 target_margin_pct must be >= 0 and < 100")
        if self.machine_costing is not None and not money_equal(
            self.machine_costing.derived_machine_time_cost,
            self.cost_basis.machine_time_cost,
        ):
            raise ValueError("machine costing does not equal machine_time_cost")
        equipment_total = as_money(
            sum(item.derived_occupancy_cost for item in self.equipment_costing)
        )
        if not money_equal(equipment_total, self.cost_basis.equipment_occupancy_cost):
            raise ValueError("equipment costing does not equal equipment_occupancy_cost")
