"""Tests for bid summary generator.

Dev Order: CNC-BID-CORE-2

Tests verify:
1. Generator preserves BidV1 values
2. Generator does not mutate input
3. Generator does not recalculate pricing
4. Risk factors include dollar contributions
"""

import pytest

from business.bids import (
    BidAssumptionV1,
    BidCostBasisV1,
    BidLineItemV1,
    BidPricingV1,
    BidV1,
    generate_bid_summary,
)


@pytest.fixture
def sample_bid() -> BidV1:
    """Create a sample BidV1 for testing."""
    return BidV1(
        bid_id="BID-TEST-001",
        project_name="Test Project",
        customer_name="Test Customer",
        revision="Draft 1",
        status="draft",
        created_at="2026-06-08T12:00:00Z",
        updated_at="2026-06-08T12:00:00Z",
        assumptions=[
            BidAssumptionV1(
                field="labor_rate",
                value=25.0,
                source="Test",
                confidence="reviewed",
                note="Test assumption",
            ),
        ],
        line_items=[
            BidLineItemV1(
                name="Test Item",
                category="labor",
                quantity=2.0,
                unit="hours",
                unit_cost=25.0,
                total_cost=50.0,
                note="Test item",
            ),
        ],
        cost_basis=BidCostBasisV1(
            direct_material_cost=0.0,
            direct_labor_cost=0.0,
            machine_time_cost=100.0,
            tooling_cost=0.0,
            setup_cost=50.0,
            finishing_cost=100.0,
            finishing_material_cost=50.0,
            engineering_cost=0.0,
        ),
        pricing=BidPricingV1(
            tool_wear_pct=5.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=10.0,
            engineering_recovery_pct=15.0,
            target_margin_pct=30.0,
            risked_cost=420.0,
            quote_price=600.0,
            quantity=10,
            price_per_unit=60.0,
        ),
        notes=["Test note"],
    )


class TestGenerateBidSummary:
    """Tests for generate_bid_summary function."""

    def test_preserves_bid_id(self, sample_bid):
        """Summary preserves bid_id from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.bid_id == sample_bid.bid_id

    def test_preserves_project_name(self, sample_bid):
        """Summary preserves project_name from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.project_name == sample_bid.project_name

    def test_preserves_customer_name(self, sample_bid):
        """Summary preserves customer_name from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.customer_name == sample_bid.customer_name

    def test_preserves_canonical_quote_price(self, sample_bid):
        """Summary preserves canonical quote price from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.canonical_quote_price == sample_bid.pricing.quote_price

    def test_preserves_canonical_price_per_unit(self, sample_bid):
        """Summary preserves canonical price per unit from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.canonical_price_per_unit == sample_bid.pricing.price_per_unit

    def test_rounded_prices_are_none(self, sample_bid):
        """Generator sets rounded prices to None (manual entry only)."""
        summary = generate_bid_summary(sample_bid)
        assert summary.rounded_quote_price is None
        assert summary.rounded_price_per_unit is None

    def test_preserves_base_manufacturing_cost(self, sample_bid):
        """Summary preserves base manufacturing cost from source."""
        summary = generate_bid_summary(sample_bid)
        assert (
            summary.base_manufacturing_cost
            == sample_bid.cost_basis.base_manufacturing_cost
        )

    def test_preserves_risked_cost(self, sample_bid):
        """Summary preserves risked cost from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.risked_cost == sample_bid.pricing.risked_cost

    def test_preserves_target_margin_pct(self, sample_bid):
        """Summary preserves target margin percentage from source."""
        summary = generate_bid_summary(sample_bid)
        assert summary.target_margin_pct == sample_bid.pricing.target_margin_pct

    def test_carries_forward_assumptions(self, sample_bid):
        """Summary carries forward all assumptions from source."""
        summary = generate_bid_summary(sample_bid)
        assert len(summary.assumptions) == len(sample_bid.assumptions)
        assert summary.assumptions[0].field == sample_bid.assumptions[0].field
        assert summary.assumptions[0].value == sample_bid.assumptions[0].value

    def test_carries_forward_line_items(self, sample_bid):
        """Summary carries forward all line items from source."""
        summary = generate_bid_summary(sample_bid)
        assert len(summary.line_items) == len(sample_bid.line_items)
        assert summary.line_items[0].name == sample_bid.line_items[0].name
        assert summary.line_items[0].total_cost == sample_bid.line_items[0].total_cost

    def test_does_not_mutate_input_bid(self, sample_bid):
        """Generator does not mutate the input bid."""
        original_bid_id = sample_bid.bid_id
        original_notes = list(sample_bid.notes)

        _ = generate_bid_summary(sample_bid)

        assert sample_bid.bid_id == original_bid_id
        assert sample_bid.notes == original_notes

    def test_copies_notes_not_references(self, sample_bid):
        """Summary notes are a copy, not a reference."""
        summary = generate_bid_summary(sample_bid)
        summary.notes.append("New note")
        assert "New note" not in sample_bid.notes


class TestRiskFactorExtraction:
    """Tests for risk factor extraction with dollar contributions."""

    def test_extracts_all_risk_factors(self, sample_bid):
        """Summary extracts all four risk factors."""
        summary = generate_bid_summary(sample_bid)
        assert len(summary.risk_factors) == 4

    def test_risk_factor_has_contribution(self, sample_bid):
        """Each risk factor includes dollar contribution."""
        summary = generate_bid_summary(sample_bid)
        for rf in summary.risk_factors:
            assert rf.contribution > 0

    def test_tool_wear_contribution(self, sample_bid):
        """Tool wear contribution is base_cost × percentage / 100."""
        summary = generate_bid_summary(sample_bid)
        tool_wear = next(rf for rf in summary.risk_factors if rf.name == "tool_wear")

        base_cost = sample_bid.cost_basis.base_manufacturing_cost
        expected = round(base_cost * sample_bid.pricing.tool_wear_pct / 100, 2)

        assert tool_wear.contribution == expected

    def test_zero_percentage_excluded(self):
        """Risk factors with 0% are not included."""
        bid = BidV1(
            bid_id="BID-ZERO",
            project_name="Test",
            customer_name="Test",
            revision="1",
            status="draft",
            created_at="2026-06-08T12:00:00Z",
            updated_at="2026-06-08T12:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=BidCostBasisV1(
                direct_material_cost=0,
                direct_labor_cost=0,
                machine_time_cost=100,
                tooling_cost=0,
                setup_cost=0,
                finishing_cost=0,
                finishing_material_cost=0,
                engineering_cost=0,
            ),
            pricing=BidPricingV1(
                tool_wear_pct=0.0,  # Zero
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=0.0,  # Zero
                engineering_recovery_pct=0.0,  # Zero
                target_margin_pct=30.0,
                risked_cost=110.0,
                quote_price=157.14,
                quantity=1,
                price_per_unit=157.14,
            ),
            notes=[],
        )

        summary = generate_bid_summary(bid)

        # Only manufacturing_contingency should be present
        assert len(summary.risk_factors) == 1
        assert summary.risk_factors[0].name == "manufacturing_contingency"


class TestEcoLoomPrototypeSummary:
    """Tests for Eco-Loom prototype bid summary generation."""

    @pytest.fixture
    def eco_loom_bid(self) -> BidV1:
        """Create Eco-Loom prototype BidV1."""
        return BidV1(
            bid_id="BID-ECOLOOM-2026-001",
            project_name="Eco-Loom Scrubber Handle Prototype",
            customer_name="ECO-LOOM",
            revision="Draft 1",
            status="draft",
            created_at="2026-06-08T12:00:00Z",
            updated_at="2026-06-08T12:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=BidCostBasisV1(
                direct_material_cost=0.0,
                direct_labor_cost=0.0,
                machine_time_cost=55.08,
                tooling_cost=0.0,
                setup_cost=50.0,
                finishing_cost=150.0,
                finishing_material_cost=60.0,
                engineering_cost=0.0,
            ),
            pricing=BidPricingV1(
                tool_wear_pct=5.0,
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=10.0,
                engineering_recovery_pct=15.0,
                target_margin_pct=30.0,
                risked_cost=441.11,
                quote_price=630.16,
                quantity=10,
                price_per_unit=63.02,
            ),
            notes=[
                "Recommended customer-facing rounded budgetary estimate: $650 total / $65 per unit"
            ],
        )

    def test_eco_loom_canonical_price(self, eco_loom_bid):
        """Eco-Loom summary has correct canonical price."""
        summary = generate_bid_summary(eco_loom_bid)
        assert summary.canonical_quote_price == 630.16
        assert summary.canonical_price_per_unit == 63.02

    def test_eco_loom_rounded_not_canonical(self, eco_loom_bid):
        """Rounded prices are None in generated summary (not parsed from notes)."""
        summary = generate_bid_summary(eco_loom_bid)
        assert summary.rounded_quote_price is None
        assert summary.rounded_price_per_unit is None
        # But notes still contain the recommendation
        assert any("$650" in note for note in summary.notes)

    def test_eco_loom_risk_contributions(self, eco_loom_bid):
        """Eco-Loom risk contributions are correct."""
        summary = generate_bid_summary(eco_loom_bid)

        # Base cost is 315.08
        risk_map = {rf.name: rf for rf in summary.risk_factors}

        assert risk_map["tool_wear"].contribution == 15.75
        assert risk_map["manufacturing_contingency"].contribution == 31.51
        assert risk_map["business_overhead"].contribution == 31.51
        assert risk_map["engineering_recovery"].contribution == 47.26
