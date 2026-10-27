"""Pure adapter from a calculated thin-skin estimate to BidV2.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-002

The mapping copies calculated category amounts. It does not recalculate them,
and it does not turn equipment occupancy, elapsed wait, scrap, or the process
reserve into another cost.
"""

from __future__ import annotations

import math

from business.bids.calculator import (
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
)
from business.bids.models import BidAssumptionV1, BidLineItemV1, BidPricingV1
from business.bids.models_v2 import BidCostBasisV2, BidV2
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.models_v2 import ThinSkinBuildEstimateV2
from business.workflows.models import (
    MAPPING_VERSION_V2,
    CategoryMappingLineV1,
    DetailReconciliationV2,
    EstimateToBidResultV2,
)

# Source category, bid cost-basis field, audit-line name.
_SOURCE_MAP: tuple[tuple[str, str, str], ...] = (
    ("core_material_cost", "direct_material_cost", "Core material"),
    ("skin_material_cost", "direct_material_cost", "Skin material"),
    (
        "adhesive_and_lamination_consumables",
        "direct_material_cost",
        "Adhesive and lamination consumables",
    ),
    ("neck_and_fretboard_cost", "direct_material_cost", "Neck and fretboard"),
    ("hardware_cost", "direct_material_cost", "Hardware"),
    ("electronics_cost", "direct_material_cost", "Electronics"),
    ("other_consumables_cost", "direct_material_cost", "Other consumables"),
    ("material_scrap_allowance", "direct_material_cost", "Material scrap allowance"),
    ("lamination_labor_cost", "direct_labor_cost", "Lamination labor"),
    ("direct_build_labor_cost", "direct_labor_cost", "Direct build labor"),
    ("assembly_labor_cost", "direct_labor_cost", "Assembly labor"),
    ("machine_time_cost", "machine_time_cost", "Machine time"),
    ("equipment_occupancy_cost", "equipment_occupancy_cost", "Equipment occupancy"),
    ("setup_and_inspection_cost", "setup_cost", "Setup and inspection"),
    ("finishing_labor_cost", "finishing_cost", "Finishing labor"),
    ("finish_material_cost", "finishing_material_cost", "Finish material"),
    (
        "process_rework_and_yield_reserve",
        "process_rework_and_yield_reserve",
        "Process rework and yield reserve",
    ),
)

_MAPPED_FIELD_ORDER = (
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

_BID_NOTES = (
    "Direct-cost-based preliminary pricing. This draft excludes unallocated "
    "overhead, warranty, fulfillment, and NRE.",
    "Equipment occupancy is its own base amount. It is not CNC time, labor, "
    "tooling, or overhead. Elapsed wait is not labor.",
    "Finish material is separate from other consumables. Scrap allowance and "
    "the process rework and yield reserve are each included once.",
    "Tooling and engineering are not introduced by this mapping and stay at zero. "
    "Tool wear remains inside the technical machine rate.",
    "Additional bid-level tool wear, manufacturing contingency, business "
    "overhead, and engineering recovery percentages are zero.",
    "Not a price approval and not a manufacturing release.",
)


def _line_note(source_category: str, bid_field: str) -> str:
    if source_category == "setup_and_inspection_cost":
        return (
            "Source category setup_and_inspection_cost maps to setup_cost. "
            "Labelled setup and inspection."
        )
    if source_category == "equipment_occupancy_cost":
        return (
            "Source category equipment_occupancy_cost maps to equipment_occupancy_cost. "
            "Occupancy is not CNC time and not labor."
        )
    if source_category == "process_rework_and_yield_reserve":
        return (
            "Source category process_rework_and_yield_reserve maps to "
            "process_rework_and_yield_reserve. Included once. Not a bid percentage."
        )
    if source_category == "finish_material_cost":
        return (
            "Source category finish_material_cost maps to finishing_material_cost. "
            "Not folded into consumables."
        )
    if source_category == "material_scrap_allowance":
        return (
            "Source category material_scrap_allowance maps to direct_material_cost. "
            "Included once. Not applied again as a pricing percentage."
        )
    return f"Source category {source_category} maps to {bid_field}."


def build_bid_from_thin_skin_estimate(
    estimate: ThinSkinBuildEstimateV2,
    *,
    bid_id: str,
    project_name: str,
    customer_name: str,
    revision: str,
    created_at: str,
    target_margin_pct: float,
    manufacturing_ref: str,
    internal_notes: tuple[str, ...] = (),
) -> EstimateToBidResultV2:
    """Group thin-skin categories into BidV2 and price them with the canonical functions."""
    if isinstance(target_margin_pct, bool) or not isinstance(target_margin_pct, (int, float)):
        raise ValueError("target_margin_pct must be a finite number")
    if not math.isfinite(float(target_margin_pct)):
        raise ValueError("target_margin_pct must be finite")
    if not 0 <= float(target_margin_pct) < 100:
        raise ValueError("target_margin_pct must be >= 0 and < 100")
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

    if estimate.machine_costing is None:
        raise ValueError("thin-skin estimate is missing machine costing")
    if not money_equal(
        estimate.machine_costing.derived_machine_time_cost,
        summary.machine_time_cost,
    ):
        raise ValueError("machine costing derived cost does not equal machine_time_cost")
    if not money_equal(grouped["machine_time_cost"], summary.machine_time_cost):
        raise ValueError("bid machine_time_cost does not equal the copied machine costing")

    equipment_record_total = as_money(
        sum(item.derived_occupancy_cost for item in estimate.equipment_costing)
    )
    if not money_equal(equipment_record_total, summary.equipment_occupancy_cost):
        raise ValueError("equipment costing does not equal equipment_occupancy_cost")
    if not money_equal(grouped["equipment_occupancy_cost"], summary.equipment_occupancy_cost):
        raise ValueError("bid equipment occupancy does not equal the estimate")

    operation_equipment = as_money(
        sum(item.equipment_occupancy_cost for item in estimate.operation_results)
    )
    operation_machine = as_money(sum(item.machine_time_cost for item in estimate.operation_results))
    detail = DetailReconciliationV2(
        equipment_record_total=equipment_record_total,
        equipment_operation_detail_total=operation_equipment,
        equipment_detail_difference=as_money(equipment_record_total - operation_equipment),
        machine_record_total=as_money(estimate.machine_costing.derived_machine_time_cost),
        machine_operation_detail_total=operation_machine,
        machine_detail_difference=as_money(
            estimate.machine_costing.derived_machine_time_cost - operation_machine
        ),
    )

    mapped_total = as_money(sum(grouped[field] for field in _MAPPED_FIELD_ORDER))
    audit_total = as_money(sum(line.total_cost for line in audit_lines))
    estimate_total = as_money(summary.total_direct_manufacturing_cost)
    if not money_equal(mapped_total, estimate_total) or not money_equal(audit_total, mapped_total):
        raise ValueError("mapped categories do not equal total_direct_manufacturing_cost")

    cost_basis = BidCostBasisV2(
        direct_material_cost=grouped["direct_material_cost"],
        direct_labor_cost=grouped["direct_labor_cost"],
        machine_time_cost=grouped["machine_time_cost"],
        tooling_cost=0.0,
        setup_cost=grouped["setup_cost"],
        finishing_cost=grouped["finishing_cost"],
        finishing_material_cost=grouped["finishing_material_cost"],
        engineering_cost=0.0,
        equipment_occupancy_cost=grouped["equipment_occupancy_cost"],
        process_rework_and_yield_reserve=grouped["process_rework_and_yield_reserve"],
    )
    if not money_equal(cost_basis.base_manufacturing_cost, estimate_total):
        raise ValueError("bid base manufacturing cost does not equal the estimate total")

    risked_cost = calculate_risked_cost(cost_basis.base_manufacturing_cost, 0.0, 0.0, 0.0, 0.0)
    quote_price = calculate_bid_price(risked_cost, float(target_margin_pct))
    price_per_unit = calculate_price_per_unit(quote_price, 1)
    if not money_equal(price_per_unit, quote_price):
        raise ValueError("price_per_unit must equal quote_price at quantity 1")

    notes = list(_BID_NOTES)
    for note in internal_notes:
        if note not in notes:
            notes.append(note)

    bid = BidV2(
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
                source="cnc_job_quote_workflow_v2",
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
                source="cnc_job_quote_workflow_v2",
                confidence="draft",
                note=f"Fixed at zero for mapping version {MAPPING_VERSION_V2}.",
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
        equipment_costing=list(estimate.equipment_costing),
    )
    return EstimateToBidResultV2(
        bid=bid,
        lines=tuple(lines),
        mapped_amounts=tuple((field, grouped[field]) for field in _MAPPED_FIELD_ORDER),
        estimate_total=estimate_total,
        mapped_total=mapped_total,
        audit_total=audit_total,
        difference=0.0,
        detail=detail,
    )
