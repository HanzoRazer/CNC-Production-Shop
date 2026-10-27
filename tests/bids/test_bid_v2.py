"""BidV2 contract: computed base, independent fields, and summary copy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from business.bids.calculator import calculate_bid_price
from business.bids.generator_v2 import generate_bid_summary_v2
from business.bids.models import BidAssumptionV1, BidLineItemV1, BidPricingV1, BidV1
from business.bids.models_v2 import BID_V2_RECORD_VERSION, BidCostBasisV2, BidV2
from business.estimates.models_v2 import EquipmentOccupancyCostingV1
from business.workflows.loading import validate_instance
from business.workflows.models import JobQuoteRefusalError
from business.workflows.reporting_v2 import bid_payload_v2

ROOT = Path(__file__).resolve().parents[2]
BID_V2_SCHEMA = "bids/bid_v2.schema.json"
BID_V1_SCHEMA = "bids/bid_v1.schema.json"


def _basis(**overrides: float) -> BidCostBasisV2:
    values = {
        "direct_material_cost": 10.0,
        "direct_labor_cost": 20.0,
        "machine_time_cost": 30.0,
        "tooling_cost": 0.0,
        "setup_cost": 4.0,
        "finishing_cost": 5.0,
        "finishing_material_cost": 6.0,
        "engineering_cost": 0.0,
        "equipment_occupancy_cost": 7.0,
        "process_rework_and_yield_reserve": 8.0,
    }
    values.update(overrides)
    return BidCostBasisV2(**values)


def _equipment(cost: float = 7.0) -> EquipmentOccupancyCostingV1:
    return EquipmentOccupancyCostingV1(
        equipment_id="EQUIPMENT-VACUUM-PRESS-V1",
        equipment_profile_ref="fixtures/equipment/vacuum_press_v1.json",
        cost_basis_id="EQUIPMENT-COST-BASIS-VACUUM-PRESS-V1",
        cost_basis_ref="fixtures/equipment/cost_basis/vacuum_press_cost_basis_v1.json",
        cost_basis_role="internal_technical_cost",
        occupancy_minutes=60.0,
        equipment_hour_rate=cost,
        derived_occupancy_cost=cost,
        derivation="equipment_hour_rate * occupancy_minutes / 60",
        provenance_status="draft",
    )


def _bid(**pricing: float) -> BidV2:
    basis = _basis()
    margin = pricing.get("target_margin_pct", 30.0)
    quote = calculate_bid_price(basis.base_manufacturing_cost, margin)
    return BidV2(
        bid_id="BID-V2-SCHEMA",
        project_name="INTERNAL-DEMO",
        customer_name="INTERNAL-DEMO",
        revision="Draft 1",
        status="draft",
        created_at="2026-10-26T16:00:00Z",
        updated_at="2026-10-26T16:00:00Z",
        assumptions=[
            BidAssumptionV1(
                field="pricing_basis",
                value="direct_manufacturing_cost_only",
                source="test",
                confidence="draft",
            )
        ],
        line_items=[
            BidLineItemV1(
                name="Core material",
                category="core_material_cost",
                quantity=1,
                unit="job",
                unit_cost=10.0,
                total_cost=10.0,
            )
        ],
        cost_basis=basis,
        pricing=BidPricingV1(
            tool_wear_pct=0.0,
            manufacturing_contingency_pct=0.0,
            business_overhead_pct=0.0,
            engineering_recovery_pct=0.0,
            target_margin_pct=margin,
            risked_cost=basis.base_manufacturing_cost,
            quote_price=quote,
            quantity=1,
            price_per_unit=quote,
        ),
        notes=["internal only"],
        equipment_costing=[_equipment()],
    )


def test_bid_v2_is_not_a_v1_bid() -> None:
    assert not issubclass(BidV2, BidV1)


def test_base_is_the_cent_rounded_sum_of_ten_fields() -> None:
    basis = _basis()
    assert basis.base_manufacturing_cost == 90.0
    payload = bid_payload_v2(_bid())
    assert "base_manufacturing_cost" not in BidCostBasisV2.__dataclass_fields__
    assert payload["cost_basis"]["base_manufacturing_cost"] == 90.0
    assert payload["cost_basis"]["equipment_occupancy_cost"] == 7.0
    assert payload["cost_basis"]["machine_time_cost"] == 30.0
    assert payload["record_type"] == "cnc_bid"
    assert payload["record_version"] == BID_V2_RECORD_VERSION
    validate_instance(payload, BID_V2_SCHEMA, label="bid")


def test_v1_schema_rejects_v2_fields() -> None:
    payload = bid_payload_v2(_bid())
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(payload, BID_V1_SCHEMA, label="bid")


def test_schema_rejects_extra_fields_nonzero_factors_and_approved_status() -> None:
    payload = bid_payload_v2(_bid())
    extra = dict(payload)
    extra["customer_price_approved"] = True
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(extra, BID_V2_SCHEMA, label="bid")
    priced = json.loads(json.dumps(payload))
    priced["pricing"]["tool_wear_pct"] = 5
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(priced, BID_V2_SCHEMA, label="bid")
    approved = json.loads(json.dumps(payload))
    approved["status"] = "approved"
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(approved, BID_V2_SCHEMA, label="bid")
    missing_base = json.loads(json.dumps(payload))
    del missing_base["cost_basis"]["base_manufacturing_cost"]
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(missing_base, BID_V2_SCHEMA, label="bid")


def test_model_rejects_non_draft_and_equipment_that_does_not_reconcile() -> None:
    with pytest.raises(ValueError, match="draft"):
        BidV2(
            bid_id="BID-V2-SCHEMA",
            project_name="INTERNAL-DEMO",
            customer_name="INTERNAL-DEMO",
            revision="Draft 1",
            status="approved",
            created_at="2026-10-26T16:00:00Z",
            updated_at="2026-10-26T16:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=_basis(equipment_occupancy_cost=0.0),
            pricing=BidPricingV1(0, 0, 0, 0, 0, 83.0, 83.0, 1, 83.0),
            equipment_costing=[],
        )
    with pytest.raises(ValueError, match="equipment costing"):
        BidV2(
            bid_id="BID-V2-SCHEMA",
            project_name="INTERNAL-DEMO",
            customer_name="INTERNAL-DEMO",
            revision="Draft 1",
            status="draft",
            created_at="2026-10-26T16:00:00Z",
            updated_at="2026-10-26T16:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=_basis(),
            pricing=BidPricingV1(0, 0, 0, 0, 30, 90.0, 128.57, 1, 128.57),
            equipment_costing=[_equipment(1.0)],
        )


def test_summary_copies_prices_and_does_not_reprice(monkeypatch: pytest.MonkeyPatch) -> None:
    bid = _bid()
    before = (
        bid.pricing.quote_price,
        bid.pricing.price_per_unit,
        bid.pricing.risked_cost,
        bid.cost_basis.base_manufacturing_cost,
    )

    def boom(*_args: object, **_kwargs: object) -> float:
        raise AssertionError("summary generation must not reprice")

    monkeypatch.setattr("business.bids.calculator.calculate_bid_price", boom)
    summary = generate_bid_summary_v2(bid)
    assert summary.canonical_quote_price == before[0]
    assert summary.canonical_price_per_unit == before[1]
    assert summary.risked_cost == before[2]
    assert summary.base_manufacturing_cost == before[3]
    assert summary.risk_factors == []
    assert summary.line_items[0].category == "core_material_cost"
    assert summary.notes == ["internal only"]
    validate_instance(
        json.loads(
            json.dumps(
                {
                    "bid_id": summary.bid_id,
                    "project_name": summary.project_name,
                    "customer_name": summary.customer_name,
                    "revision": summary.revision,
                    "status": summary.status,
                    "quantity": summary.quantity,
                    "canonical_quote_price": summary.canonical_quote_price,
                    "canonical_price_per_unit": summary.canonical_price_per_unit,
                    "base_manufacturing_cost": summary.base_manufacturing_cost,
                    "risked_cost": summary.risked_cost,
                    "target_margin_pct": summary.target_margin_pct,
                    "line_items": [
                        {
                            "name": item.name,
                            "category": item.category,
                            "quantity": item.quantity,
                            "unit": item.unit,
                            "unit_cost": item.unit_cost,
                            "total_cost": item.total_cost,
                            "note": item.note,
                        }
                        for item in summary.line_items
                    ],
                    "risk_factors": [],
                    "assumptions": [
                        {
                            "field": item.field,
                            "value": item.value,
                            "source": item.source,
                            "confidence": item.confidence,
                            "note": item.note,
                        }
                        for item in summary.assumptions
                    ],
                    "notes": summary.notes,
                }
            )
        ),
        "bids/bid_summary_v1.schema.json",
        label="summary",
    )
    assert (ROOT / "schemas" / "bids" / "bid_v1.schema.json").is_file()
