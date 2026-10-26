"""Pure adapter from a calculated guitar estimate to BidV1.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-001

The mapping groups existing estimate categories. It does not recalculate them
and it does not invent overhead, tooling, scrap, or contingency.
"""

from __future__ import annotations

import math

from business.bids.calculator import (
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
)
from business.bids.models import (
    BidAssumptionV1,
    BidCostBasisV1,
    BidLineItemV1,
    BidPricingV1,
    BidV1,
)
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.models import GuitarBuildEstimateV1
from business.workflows.models import (
    MAPPING_VERSION,
    CategoryMappingLineV1,
    EstimateToBidResult,
)

# Source category, bid cost-basis field, audit-line name.
_SOURCE_MAP: tuple[tuple[str, str, str], ...] = (
    ("wood_material_cost", "direct_material_cost", "Wood material"),
    ("hardware_cost", "direct_material_cost", "Hardware"),
    ("electronics_cost", "direct_material_cost", "Electronics"),
    ("consumables_cost", "direct_material_cost", "Consumables"),
    ("scrap_allowance", "direct_material_cost", "Scrap allowance"),
    ("direct_labor_cost", "direct_labor_cost", "Direct labor"),
    ("machine_time_cost", "machine_time_cost", "Machine time"),
    ("inspection_and_setup_cost", "setup_cost", "Setup and inspection"),
    ("finishing_cost", "finishing_cost", "Finishing labor"),
)

_ZERO_FIELDS = ("tooling_cost", "finishing_material_cost", "engineering_cost")

_MAPPED_FIELD_ORDER = (
    "direct_material_cost",
    "direct_labor_cost",
    "machine_time_cost",
    "tooling_cost",
    "setup_cost",
    "finishing_cost",
    "finishing_material_cost",
    "engineering_cost",
)

_BID_NOTES = (
    "Direct-cost-based preliminary pricing. This draft excludes unallocated "
    "overhead, warranty, fulfillment, and NRE.",
    "Tool wear is already included in the technical machine rate. Scrap is "
    "already included in the estimate. No extra scrap, tooling percentage, "
    "or manufacturing contingency is applied.",
    "Setup cost is inspection_and_setup_cost mapped to setup_cost and labelled "
    "setup and inspection.",
    "Additional bid-level tool wear, manufacturing contingency, business "
    "overhead, and engineering recovery percentages are zero.",
    "Not a price approval and not a manufacturing release.",
)


def _line_note(source_category: str, bid_field: str) -> str:
    if source_category == "inspection_and_setup_cost":
        return (
            "Source category inspection_and_setup_cost maps to setup_cost. "
            "Labelled setup and inspection."
        )
    return f"Source category {source_category} maps to {bid_field}."


def build_bid_from_estimate(
    estimate: GuitarBuildEstimateV1,
    *,
    bid_id: str,
    project_name: str,
    customer_name: str,
    revision: str,
    created_at: str,
    target_margin_pct: float,
    manufacturing_ref: str,
    internal_notes: tuple[str, ...] = (),
) -> EstimateToBidResult:
    """Group estimate categories into BidV1 and price them with the canonical functions."""
    if isinstance(target_margin_pct, bool) or not isinstance(target_margin_pct, (int, float)):
        raise ValueError("target_margin_pct must be a finite number")
    if not math.isfinite(float(target_margin_pct)):
        raise ValueError("target_margin_pct must be finite")
    if estimate.quantity != 1:
        raise ValueError("this workflow only supports quantity 1")
    if estimate.currency != "USD":
        raise ValueError("this workflow only supports currency USD")

    summary = estimate.cost_summary
    grouped: dict[str, float] = {field: 0.0 for field in _MAPPED_FIELD_ORDER}
    lines: list[CategoryMappingLineV1] = []
    audit_lines: list[BidLineItemV1] = []
    for source_category, bid_field, label in _SOURCE_MAP:
        amount = as_money(getattr(summary, source_category))
        grouped[bid_field] = as_money(grouped[bid_field] + amount)
        lines.append(
            CategoryMappingLineV1(
                source_category=source_category,
                source_amount=amount,
                bid_field=bid_field,
                mapped_amount=amount,
            )
        )
        audit_lines.append(
            BidLineItemV1(
                name=label,
                category=source_category,
                quantity=1,
                unit="job",
                unit_cost=amount,
                total_cost=amount,
                note=_line_note(source_category, bid_field),
            )
        )
    for field in _ZERO_FIELDS:
        grouped[field] = 0.0

    if not money_equal(
        estimate.machine_costing.derived_machine_time_cost,
        summary.machine_time_cost,
    ):
        raise ValueError("machine costing derived cost does not equal machine_time_cost")
    derived_machine_cost = estimate.machine_costing.derived_machine_time_cost
    if not money_equal(grouped["machine_time_cost"], derived_machine_cost):
        raise ValueError("bid machine_time_cost does not equal the copied machine costing")

    mapped_total = as_money(sum(grouped.values()))
    audit_total = as_money(sum(line.total_cost for line in audit_lines))
    estimate_total = as_money(summary.total_direct_manufacturing_cost)
    if not money_equal(mapped_total, estimate_total) or not money_equal(audit_total, mapped_total):
        raise ValueError("mapped categories do not equal total_direct_manufacturing_cost")

    cost_basis = BidCostBasisV1(
        direct_material_cost=grouped["direct_material_cost"],
        direct_labor_cost=grouped["direct_labor_cost"],
        machine_time_cost=grouped["machine_time_cost"],
        tooling_cost=0.0,
        setup_cost=grouped["setup_cost"],
        finishing_cost=grouped["finishing_cost"],
        finishing_material_cost=0.0,
        engineering_cost=0.0,
    )
    if not money_equal(cost_basis.base_manufacturing_cost, estimate_total):
        raise ValueError("bid base manufacturing cost does not equal the estimate total")

    risked_cost = calculate_risked_cost(
        cost_basis.base_manufacturing_cost,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    quote_price = calculate_bid_price(risked_cost, float(target_margin_pct))
    price_per_unit = calculate_price_per_unit(quote_price, 1)
    if not money_equal(price_per_unit, quote_price):
        raise ValueError("price_per_unit must equal quote_price at quantity 1")

    notes = list(_BID_NOTES)
    for note in internal_notes:
        if note not in notes:
            notes.append(note)

    bid = BidV1(
        bid_id=bid_id,
        project_name=project_name,
        customer_name=customer_name,
        revision=revision,
        status="draft",
        created_at=created_at,
        updated_at=created_at,
        assumptions=[
            BidAssumptionV1(
                field="pricing_basis",
                value="direct_manufacturing_cost_only",
                source="cnc_job_quote_workflow_v1",
                confidence="draft",
                note=(
                    "Preliminary direct-cost pricing. Unallocated overhead, warranty, "
                    "fulfillment, and NRE are excluded."
                ),
            ),
            BidAssumptionV1(
                field="target_margin_pct",
                value=float(target_margin_pct),
                source="cnc_job_quote_request",
                confidence="draft",
                note="Caller-supplied target margin for this draft. Not a price approval.",
            ),
            BidAssumptionV1(
                field="pricing_percentages",
                value=(
                    "tool_wear_pct=0;manufacturing_contingency_pct=0;"
                    "business_overhead_pct=0;engineering_recovery_pct=0"
                ),
                source="cnc_job_quote_workflow_v1",
                confidence="draft",
                note=f"Fixed at zero for mapping version {MAPPING_VERSION}.",
            ),
        ],
        line_items=audit_lines,
        cost_basis=cost_basis,
        pricing=BidPricingV1(
            tool_wear_pct=0.0,
            manufacturing_contingency_pct=0.0,
            business_overhead_pct=0.0,
            engineering_recovery_pct=0.0,
            target_margin_pct=float(target_margin_pct),
            risked_cost=risked_cost,
            quote_price=quote_price,
            quantity=1,
            price_per_unit=price_per_unit,
        ),
        notes=notes,
        project_ref=None,
        manufacturing_ref=manufacturing_ref,
        scenario_ref=None,
        machine_costing=estimate.machine_costing,
    )
    return EstimateToBidResult(
        bid=bid,
        lines=tuple(lines),
        mapped_amounts=tuple((field, grouped[field]) for field in _MAPPED_FIELD_ORDER),
        estimate_total=estimate_total,
        mapped_total=mapped_total,
        audit_total=audit_total,
        difference=0.0,
    )
