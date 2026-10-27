"""Exact thin-skin category crosswalk and target-margin boundaries."""

from __future__ import annotations

import math

import pytest

from business.bids.calculator import calculate_bid_price
from business.bids.models import MachineCostingV1
from business.calculators.machine_cost_basis import as_money
from business.estimates.models_v2 import (
    EquipmentOccupancyCostingV1,
    EstimateCalculationMetaV2,
    EstimateProvenanceV2,
    OperationCostResultV2,
    RiskBasisDetailV2,
    ThinSkinBuildEstimateV2,
    ThinSkinCostSummaryV2,
    ThinSkinTimeSummaryV2,
)
from business.workflows.estimate_to_bid_v2 import build_bid_from_thin_skin_estimate
from business.workflows.models import PACKET_MANUFACTURING_REF

CATEGORIES = (
    "core_material_cost",
    "skin_material_cost",
    "adhesive_and_lamination_consumables",
    "neck_and_fretboard_cost",
    "hardware_cost",
    "electronics_cost",
    "other_consumables_cost",
    "material_scrap_allowance",
    "lamination_labor_cost",
    "direct_build_labor_cost",
    "assembly_labor_cost",
    "machine_time_cost",
    "equipment_occupancy_cost",
    "setup_and_inspection_cost",
    "finishing_labor_cost",
    "finish_material_cost",
    "process_rework_and_yield_reserve",
)
MATERIAL = CATEGORIES[:8]
LABOR = (
    "lamination_labor_cost",
    "direct_build_labor_cost",
    "assembly_labor_cost",
)


def _estimate(
    costs: dict[str, float], *, operation_equipment: float | None = None
) -> ThinSkinBuildEstimateV2:
    equipment_cost = costs["equipment_occupancy_cost"]
    machine_cost = costs["machine_time_cost"]
    summary = ThinSkinCostSummaryV2(
        **costs,
        total_direct_manufacturing_cost=as_money(sum(costs.values())),
    )
    machine = MachineCostingV1(
        machine_id="MACHINE-SENTINEL-V1",
        machine_profile_ref="fixtures/machines/sentinel.json",
        cost_basis_id="MACHINE-COST-BASIS-SENTINEL-V1",
        cost_basis_ref="fixtures/machines/cost_basis/sentinel.json",
        cost_basis_role="internal_technical_cost",
        runtime_minutes=60.0,
        machine_hour_rate=machine_cost,
        derived_machine_time_cost=machine_cost,
        derivation="machine_hour_rate * runtime_minutes / 60",
        provenance_status="draft",
    )
    equipment = ()
    if equipment_cost:
        equipment = (
            EquipmentOccupancyCostingV1(
                equipment_id="EQUIPMENT-PRESS-V1",
                equipment_profile_ref="fixtures/equipment/press.json",
                cost_basis_id="EQUIPMENT-COST-BASIS-PRESS-V1",
                cost_basis_ref="fixtures/equipment/cost_basis/press.json",
                cost_basis_role="internal_technical_cost",
                occupancy_minutes=120.0,
                equipment_hour_rate=10.0,
                derived_occupancy_cost=equipment_cost,
                derivation="equipment_hour_rate * occupancy_minutes / 60",
                provenance_status="draft",
            ),
        )
    detail_equipment = equipment_cost if operation_equipment is None else operation_equipment
    return ThinSkinBuildEstimateV2(
        estimate_id="THIN-SKIN-GUITAR-BUILD-ESTIMATE-SENTINEL",
        product_id="PRODUCT-SENTINEL-V1",
        product_ref="fixtures/products/sentinel.json",
        variant_id="VARIANT-SENTINEL",
        variant_description="Synthetic crosswalk",
        estimate_input_id="THIN-SKIN-ESTIMATE-INPUT-SENTINEL-V1",
        estimate_input_ref="fixtures/estimates/guitar/sentinel.json",
        status="reviewed",
        quantity=1,
        currency="USD",
        cost_summary=summary,
        time_summary=ThinSkinTimeSummaryV2(
            total_labor_minutes=10,
            total_machine_runtime_minutes=5,
            total_equipment_occupancy_minutes=20,
            total_elapsed_wait_minutes=30,
            total_rework_minutes=0,
            lamination_labor_minutes=1,
            direct_build_labor_minutes=2,
            finishing_labor_minutes=3,
            assembly_labor_minutes=4,
            setup_and_inspection_minutes=0,
        ),
        risk_basis=RiskBasisDetailV2(
            material_scrap_rate=0.05,
            material_scrap_base=1,
            process_reserve_rate=0.1,
            process_reserve_material_base=1,
            process_reserve_machine_base=1,
            process_reserve_equipment_base=1,
            process_reserve_labor_base=1,
            process_reserve_base=4,
            compounding="no_compounding",
        ),
        operation_results=(
            OperationCostResultV2(
                operation_id="OP-1",
                wbs_code="1000",
                labor_category="direct_build_labor",
                attendance="attended",
                labor_minutes=1,
                machine_runtime_minutes=5,
                equipment_occupancy_minutes=20,
                elapsed_wait_minutes=30,
                rework_minutes=0,
                equipment_id="EQUIPMENT-PRESS-V1",
                labor_cost=1,
                machine_time_cost=machine_cost,
                equipment_occupancy_cost=detail_equipment,
                operation_cost=as_money(1 + machine_cost + detail_equipment),
            ),
        ),
        machine_costing=machine,
        equipment_costing=equipment,
        calculation=EstimateCalculationMetaV2(
            calculator_id="thin_skin_build_estimate_v2",
            rounding_policy="currency_half_up_2dp",
            effective_date="2026-10-26",
        ),
        provenance=EstimateProvenanceV2(source="calculated", confidence="draft"),
        notes=("estimate note",),
    )


def _sentinels() -> dict[str, float]:
    # Whole dollars stay exact under cent rounding, including the zero category.
    values = [float(index) for index in range(1, 18)]
    values[6] = 0.0
    return dict(zip(CATEGORIES, values, strict=True))


def _map(costs: dict[str, float], margin: float = 30.0, **kwargs: float):
    return build_bid_from_thin_skin_estimate(
        _estimate(costs, **kwargs),
        bid_id="BID-SENTINEL",
        project_name="Sentinel",
        customer_name="INTERNAL-DEMO",
        revision="Draft",
        created_at="2026-10-26T16:00:00Z",
        target_margin_pct=margin,
        manufacturing_ref=PACKET_MANUFACTURING_REF,
        internal_notes=("private sentinel",),
    )


def test_each_source_category_maps_once_and_zero_categories_remain() -> None:
    costs = _sentinels()
    result = _map(costs, operation_equipment=costs["equipment_occupancy_cost"] - 0.01)
    categories = [line.source_category for line in result.lines]
    assert categories == list(CATEGORIES)
    assert len(set(categories)) == 17
    assert "total_direct_manufacturing_cost" not in categories
    for line in result.lines:
        assert line.source_amount == costs[line.source_category]
        assert line.mapped_amount == line.source_amount
        assert line.source_amount == next(
            item.total_cost
            for item in result.bid.line_items
            if item.category == line.source_category
        )
    basis = result.bid.cost_basis
    assert basis.direct_material_cost == as_money(sum(costs[name] for name in MATERIAL))
    assert basis.direct_labor_cost == as_money(sum(costs[name] for name in LABOR))
    assert basis.machine_time_cost == costs["machine_time_cost"]
    assert basis.equipment_occupancy_cost == costs["equipment_occupancy_cost"]
    assert basis.setup_cost == costs["setup_and_inspection_cost"]
    assert basis.finishing_cost == costs["finishing_labor_cost"]
    assert basis.finishing_material_cost == costs["finish_material_cost"]
    assert basis.process_rework_and_yield_reserve == costs["process_rework_and_yield_reserve"]
    assert basis.tooling_cost == 0
    assert basis.engineering_cost == 0
    assert basis.base_manufacturing_cost == as_money(sum(costs.values()))
    assert result.difference == 0
    assert result.detail.equipment_detail_difference == 0.01
    assert result.mapped_total == basis.base_manufacturing_cost
    assert result.audit_total == result.mapped_total
    assert result.bid.pricing.risked_cost == basis.base_manufacturing_cost
    assert result.bid.pricing.tool_wear_pct == 0
    assert "private sentinel" in result.bid.notes
    assert result.bid.status == "draft"


def test_margin_boundaries_use_target_margin_not_markup() -> None:
    costs = dict.fromkeys(CATEGORIES, 0.0)
    costs["core_material_cost"] = 1000.0
    priced = _map(costs, 30.0)
    assert priced.bid.pricing.risked_cost == 1000.0
    assert priced.bid.pricing.quote_price == 1428.57
    assert priced.bid.pricing.quote_price != 1300
    assert priced.bid.pricing.price_per_unit == priced.bid.pricing.quote_price
    assert calculate_bid_price(1000, 30) == 1428.57
    zero = _map(costs, 0.0)
    assert zero.bid.pricing.quote_price == 1000.0


@pytest.mark.parametrize("margin", [-0.01, 100, 100.1, math.nan, math.inf, True])
def test_margin_outside_the_open_unit_interval_is_refused(margin: float) -> None:
    costs = dict.fromkeys(CATEGORIES, 0.0)
    costs["core_material_cost"] = 10.0
    with pytest.raises(ValueError):
        _map(costs, margin)
