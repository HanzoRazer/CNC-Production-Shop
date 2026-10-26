"""Category mapping and target-margin proof for the estimate-to-bid adapter."""

from __future__ import annotations

from dataclasses import replace

import pytest

from business.bids.calculator import calculate_bid_price
from business.bids.models import MachineCostingV1
from business.estimates.models import (
    EstimateCalculationMetaV1,
    EstimateProvenanceV1,
    GuitarBuildEstimateV1,
    GuitarCostSummaryV1,
    OperationCostResultV1,
)
from business.workflows.estimate_to_bid import build_bid_from_estimate
from business.workflows.models import PACKET_MANUFACTURING_REF


def _estimate(**costs: float) -> GuitarBuildEstimateV1:
    summary = GuitarCostSummaryV1(
        wood_material_cost=costs["wood"],
        hardware_cost=costs["hardware"],
        electronics_cost=costs["electronics"],
        consumables_cost=costs["consumables"],
        machine_time_cost=costs["machine"],
        direct_labor_cost=costs["labor"],
        finishing_cost=costs["finishing"],
        inspection_and_setup_cost=costs["setup"],
        scrap_allowance=costs["scrap"],
        total_direct_manufacturing_cost=costs["total"],
    )
    machine = MachineCostingV1(
        machine_id="MACHINE-SENTINEL-V1",
        machine_profile_ref="fixtures/machines/sentinel.json",
        cost_basis_id="MACHINE-COST-BASIS-SENTINEL-V1",
        cost_basis_ref="fixtures/machines/cost_basis/sentinel.json",
        cost_basis_role="internal_technical_cost",
        runtime_minutes=60.0,
        machine_hour_rate=costs["machine"],
        derived_machine_time_cost=costs["machine"],
        derivation="machine_hour_rate * runtime_minutes / 60",
        provenance_status="draft",
    )
    return GuitarBuildEstimateV1(
        estimate_id="GUITAR-BUILD-ESTIMATE-SENTINEL-V1",
        product_id="PRODUCT-SENTINEL-V1",
        product_ref="fixtures/products/sentinel.json",
        estimate_input_id="GUITAR-ESTIMATE-INPUT-SENTINEL-V1",
        estimate_input_ref="fixtures/estimates/guitar/sentinel.json",
        status="reviewed",
        quantity=1,
        currency="USD",
        cost_summary=summary,
        operation_results=(
            OperationCostResultV1(
                operation_id="OP-1",
                wbs_code="1000",
                cost_category="direct_labor",
                machine_minutes=0.0,
                labor_minutes=1.0,
                cure_or_wait_minutes=0.0,
                machine_time_cost=0.0,
                labor_cost=costs["labor"],
                category_cost=costs["labor"],
            ),
        ),
        machine_costing=machine,
        calculation=EstimateCalculationMetaV1(
            calculator_id="guitar_build_estimate_v1",
            rounding_policy="currency_half_up_2dp",
            effective_date="2026-10-25",
        ),
        provenance=EstimateProvenanceV1(source="calculated", confidence="draft", note=""),
        notes=(),
    )


def _mapped(**costs: float):
    estimate = _estimate(**costs)
    return build_bid_from_estimate(
        estimate,
        bid_id="BID-SENTINEL",
        project_name="Sentinel",
        customer_name="Sentinel Customer",
        revision="Draft",
        created_at="2026-10-25T16:00:00Z",
        target_margin_pct=30.0,
        manufacturing_ref=PACKET_MANUFACTURING_REF,
        internal_notes=("private sentinel",),
    )


def test_distinct_categories_map_once_and_do_not_double_count() -> None:
    costs = {
        "wood": 11.0,
        "hardware": 23.0,
        "electronics": 37.0,
        "consumables": 41.0,
        "scrap": 5.0,
        "labor": 53.0,
        "machine": 67.0,
        "setup": 71.0,
        "finishing": 83.0,
        "total": 391.0,
    }
    result = _mapped(**costs)
    by_source = {line.source_category: line for line in result.lines}
    assert set(by_source) == {
        "wood_material_cost",
        "hardware_cost",
        "electronics_cost",
        "consumables_cost",
        "scrap_allowance",
        "direct_labor_cost",
        "machine_time_cost",
        "inspection_and_setup_cost",
        "finishing_cost",
    }
    assert [line.source_category for line in result.lines].count("scrap_allowance") == 1
    assert by_source["scrap_allowance"].source_amount == 5.0
    assert by_source["scrap_allowance"].bid_field == "direct_material_cost"
    assert by_source["inspection_and_setup_cost"].bid_field == "setup_cost"
    setup_line = next(
        item for item in result.bid.line_items if item.category == "inspection_and_setup_cost"
    )
    assert "setup and inspection" in setup_line.note.lower()
    assert setup_line.name == "Setup and inspection"

    amounts = dict(result.mapped_amounts)
    assert amounts["direct_material_cost"] == 117.0
    assert amounts["direct_labor_cost"] == 53.0
    assert amounts["machine_time_cost"] == 67.0
    assert amounts["setup_cost"] == 71.0
    assert amounts["finishing_cost"] == 83.0
    assert amounts["tooling_cost"] == 0.0
    assert amounts["finishing_material_cost"] == 0.0
    assert amounts["engineering_cost"] == 0.0
    assert result.bid.cost_basis.tooling_cost == 0.0
    assert result.bid.cost_basis.finishing_material_cost == 0.0
    assert result.bid.cost_basis.engineering_cost == 0.0
    assert result.bid.machine_costing is not None
    assert result.bid.machine_costing.derived_machine_time_cost == 67.0
    assert result.bid.cost_basis.machine_time_cost == 67.0
    assert result.mapped_total == 391.0
    assert result.audit_total == 391.0
    assert result.difference == 0.0
    assert sum(item.total_cost for item in result.bid.line_items) == 391.0
    assert all(
        item.quantity == 1 and item.unit_cost == item.total_cost for item in result.bid.line_items
    )
    assert {item.field for item in result.bid.assumptions}.isdisjoint(
        {"material_supply", "delivery_date"}
    )
    assert result.bid.status == "draft"
    assert "private sentinel" in result.bid.notes
    assert "direct-cost-based preliminary pricing" in result.bid.notes[0].lower()


def test_target_margin_uses_canonical_pricing_not_markup() -> None:
    result = _mapped(
        wood=0.0,
        hardware=0.0,
        electronics=0.0,
        consumables=0.0,
        scrap=0.0,
        labor=1000.0,
        machine=0.0,
        setup=0.0,
        finishing=0.0,
        total=1000.0,
    )
    assert result.bid.pricing.risked_cost == 1000.0
    assert result.bid.pricing.quote_price == 1428.57
    assert result.bid.pricing.quote_price == calculate_bid_price(1000.0, 30.0)
    assert result.bid.pricing.quote_price != 1300.0
    assert result.bid.pricing.price_per_unit == 1428.57
    assert result.bid.pricing.quantity == 1
    for name in (
        "tool_wear_pct",
        "manufacturing_contingency_pct",
        "business_overhead_pct",
        "engineering_recovery_pct",
    ):
        assert getattr(result.bid.pricing, name) == 0.0


def test_zero_margin_keeps_the_risked_cost() -> None:
    estimate = _estimate(
        wood=0.0,
        hardware=0.0,
        electronics=0.0,
        consumables=0.0,
        scrap=0.0,
        labor=1000.0,
        machine=0.0,
        setup=0.0,
        finishing=0.0,
        total=1000.0,
    )
    result = build_bid_from_estimate(
        estimate,
        bid_id="BID-ZERO",
        project_name="Zero",
        customer_name="Zero Customer",
        revision="Draft",
        created_at="2026-10-25T16:00:00Z",
        target_margin_pct=0,
        manufacturing_ref=PACKET_MANUFACTURING_REF,
    )
    assert result.bid.pricing.quote_price == 1000.0
    assert result.bid.pricing.price_per_unit == 1000.0


@pytest.mark.parametrize("margin", [-0.01, 100, 100.0])
def test_margin_outside_the_open_unit_interval_is_refused(margin: float) -> None:
    estimate = _estimate(
        wood=1.0,
        hardware=0.0,
        electronics=0.0,
        consumables=0.0,
        scrap=0.0,
        labor=0.0,
        machine=0.0,
        setup=0.0,
        finishing=0.0,
        total=1.0,
    )
    with pytest.raises(ValueError):
        build_bid_from_estimate(
            estimate,
            bid_id="BID-BAD",
            project_name="Bad",
            customer_name="Bad Customer",
            revision="Draft",
            created_at="2026-10-25T16:00:00Z",
            target_margin_pct=margin,
            manufacturing_ref=PACKET_MANUFACTURING_REF,
        )


def test_machine_cost_mismatch_and_bad_total_are_refused() -> None:
    estimate = _estimate(
        wood=10.0,
        hardware=0.0,
        electronics=0.0,
        consumables=0.0,
        scrap=0.0,
        labor=0.0,
        machine=5.0,
        setup=0.0,
        finishing=0.0,
        total=15.0,
    )
    broken_machine = MachineCostingV1(
        machine_id=estimate.machine_costing.machine_id,
        machine_profile_ref=estimate.machine_costing.machine_profile_ref,
        cost_basis_id=estimate.machine_costing.cost_basis_id,
        cost_basis_ref=estimate.machine_costing.cost_basis_ref,
        cost_basis_role=estimate.machine_costing.cost_basis_role,
        runtime_minutes=60.0,
        machine_hour_rate=5.0,
        derived_machine_time_cost=99.0,
        derivation=estimate.machine_costing.derivation,
        provenance_status="draft",
    )
    mismatched = replace(estimate, machine_costing=broken_machine)
    with pytest.raises(ValueError, match="machine costing"):
        build_bid_from_estimate(
            mismatched,
            bid_id="BID-MACHINE",
            project_name="Machine",
            customer_name="Machine Customer",
            revision="Draft",
            created_at="2026-10-25T16:00:00Z",
            target_margin_pct=30,
            manufacturing_ref=PACKET_MANUFACTURING_REF,
        )

    inconsistent = _estimate(
        wood=10.0,
        hardware=0.0,
        electronics=0.0,
        consumables=0.0,
        scrap=0.0,
        labor=0.0,
        machine=5.0,
        setup=0.0,
        finishing=0.0,
        total=1.0,
    )
    with pytest.raises(ValueError, match="mapped categories"):
        build_bid_from_estimate(
            inconsistent,
            bid_id="BID-TOTAL",
            project_name="Total",
            customer_name="Total Customer",
            revision="Draft",
            created_at="2026-10-25T16:00:00Z",
            target_margin_pct=30,
            manufacturing_ref=PACKET_MANUFACTURING_REF,
        )
