"""Bid record models.

Dev Order: CNC-BID-CORE-1

These models represent internal bid calculation records, not customer-facing proposals.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class BidStatus(StrEnum):
    """Bid lifecycle status."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    SENT = "sent"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BidAssumptionV1:
    """A single assumption underlying the bid calculation."""

    field: str
    value: str | float | int | bool | None
    source: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class BidLineItemV1:
    """A single line item in the bid."""

    name: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    note: str = ""


@dataclass(frozen=True)
class BidCostBasisV1:
    """Direct cost breakdown for the bid."""

    direct_material_cost: float
    direct_labor_cost: float
    machine_time_cost: float
    tooling_cost: float
    setup_cost: float
    finishing_cost: float
    finishing_material_cost: float
    engineering_cost: float

    @property
    def base_manufacturing_cost(self) -> float:
        """Total base manufacturing cost before risk factors."""
        return (
            self.direct_material_cost
            + self.direct_labor_cost
            + self.machine_time_cost
            + self.tooling_cost
            + self.setup_cost
            + self.finishing_cost
            + self.finishing_material_cost
            + self.engineering_cost
        )


@dataclass(frozen=True)
class BidPricingV1:
    """Pricing calculation with risk factors and margin."""

    tool_wear_pct: float
    manufacturing_contingency_pct: float
    business_overhead_pct: float
    engineering_recovery_pct: float
    target_margin_pct: float
    risked_cost: float
    quote_price: float
    quantity: int
    price_per_unit: float


@dataclass(frozen=True)
class MachineCostingV1:
    """Opt-in auditable link from a bid to a governed machine cost basis.

    When present on BidV1, cost_basis.machine_time_cost must equal
    derived_machine_time_cost. The machine_hour_rate is an internal technical
    cost basis, not a commercial billing rate. Construction belongs in
    business.bids.machine_costing.build_machine_costing — this model stores
    the derivation record only and performs no lookup.
    """

    machine_id: str
    machine_profile_ref: str
    cost_basis_id: str
    cost_basis_ref: str
    cost_basis_role: str
    runtime_minutes: float
    machine_hour_rate: float
    derived_machine_time_cost: float
    derivation: str
    provenance_status: str


@dataclass
class BidV1:
    """Complete internal bid calculation record."""

    bid_id: str
    project_name: str
    customer_name: str
    revision: str
    status: str
    created_at: str
    updated_at: str
    assumptions: list[BidAssumptionV1]
    line_items: list[BidLineItemV1]
    cost_basis: BidCostBasisV1
    pricing: BidPricingV1
    notes: list[str] = field(default_factory=list)
    project_ref: str | None = None
    manufacturing_ref: str | None = None
    scenario_ref: str | None = None
    machine_costing: MachineCostingV1 | None = None
