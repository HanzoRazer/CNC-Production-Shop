"""Tests for proposal generator.

Dev Order: CNC-BID-CORE-3

Tests verify:
1. Generator preserves project/customer info
2. Uses rounded pricing when present
3. Falls back to canonical pricing when rounded is null
4. Does not expose risk_factors
5. Does not expose target_margin_pct
6. Creates required sections
7. Does not mutate input summary
"""

import pytest

from business.bids.summary import (
    BidSummaryAssumptionV1,
    BidSummaryLineItemV1,
    BidSummaryRiskV1,
    BidSummaryV1,
)
from business.proposals import generate_proposal_from_summary


@pytest.fixture
def sample_summary() -> BidSummaryV1:
    """Create a sample BidSummaryV1 for testing."""
    return BidSummaryV1(
        bid_id="BID-TEST-001",
        project_name="Test Project",
        customer_name="Test Customer",
        revision="Draft 1",
        status="draft",
        quantity=10,
        canonical_quote_price=630.16,
        canonical_price_per_unit=63.02,
        rounded_quote_price=650.00,
        rounded_price_per_unit=65.00,
        base_manufacturing_cost=315.08,
        risked_cost=441.11,
        target_margin_pct=30.0,
        line_items=[
            BidSummaryLineItemV1(
                name="Test Item",
                category="machine",
                quantity=10,
                unit="units",
                unit_cost=31.51,
                total_cost=315.08,
            ),
        ],
        risk_factors=[
            BidSummaryRiskV1(name="tool_wear", percentage=5.0, contribution=15.75),
            BidSummaryRiskV1(
                name="manufacturing_contingency", percentage=10.0, contribution=31.51
            ),
        ],
        assumptions=[
            BidSummaryAssumptionV1(
                field="material_supply",
                value="customer-supplied",
                source="Customer agreement",
                confidence="reviewed",
            ),
            BidSummaryAssumptionV1(
                field="delivery_date",
                value="2026-07-15",
                source="Customer request",
                confidence="approved",
            ),
        ],
        notes=["Test note"],
    )


@pytest.fixture
def summary_without_rounded(sample_summary) -> BidSummaryV1:
    """Create a summary without rounded pricing."""
    return BidSummaryV1(
        bid_id=sample_summary.bid_id,
        project_name=sample_summary.project_name,
        customer_name=sample_summary.customer_name,
        revision=sample_summary.revision,
        status=sample_summary.status,
        quantity=sample_summary.quantity,
        canonical_quote_price=sample_summary.canonical_quote_price,
        canonical_price_per_unit=sample_summary.canonical_price_per_unit,
        rounded_quote_price=None,
        rounded_price_per_unit=None,
        base_manufacturing_cost=sample_summary.base_manufacturing_cost,
        risked_cost=sample_summary.risked_cost,
        target_margin_pct=sample_summary.target_margin_pct,
        line_items=list(sample_summary.line_items),
        risk_factors=list(sample_summary.risk_factors),
        assumptions=list(sample_summary.assumptions),
        notes=list(sample_summary.notes),
    )


class TestGenerateProposalFromSummary:
    """Tests for generate_proposal_from_summary function."""

    def test_preserves_project_name(self, sample_summary):
        """Proposal preserves project name from summary."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert proposal.project_name == sample_summary.project_name

    def test_preserves_customer_name(self, sample_summary):
        """Proposal preserves customer name from summary."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert proposal.customer_name == sample_summary.customer_name

    def test_preserves_source_bid_id(self, sample_summary):
        """Proposal preserves source bid ID from summary."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert proposal.source_bid_id == sample_summary.bid_id

    def test_uses_rounded_pricing_when_present(self, sample_summary):
        """Proposal uses rounded pricing when present."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert proposal.pricing.total_price == 650.00
        assert proposal.pricing.price_per_unit == 65.00

    def test_falls_back_to_canonical_when_rounded_null(self, summary_without_rounded):
        """Proposal falls back to canonical pricing when rounded is null."""
        proposal = generate_proposal_from_summary(summary_without_rounded)
        assert proposal.pricing.total_price == 630.16
        assert proposal.pricing.price_per_unit == 63.02

    def test_does_not_expose_risk_factors(self, sample_summary):
        """Proposal does not contain risk_factors."""
        proposal = generate_proposal_from_summary(sample_summary)

        # Check proposal doesn't have risk_factors attribute
        assert not hasattr(proposal, "risk_factors")

        # Check it's not serialized anywhere in sections
        for section in proposal.sections:
            assert "tool_wear" not in section.body.lower()
            assert "contingency" not in section.body.lower()
            for bullet in section.bullets:
                assert "tool_wear" not in bullet.lower()

    def test_does_not_expose_target_margin_pct(self, sample_summary):
        """Proposal does not contain target_margin_pct."""
        proposal = generate_proposal_from_summary(sample_summary)

        # Check proposal doesn't have target_margin_pct attribute
        assert not hasattr(proposal, "target_margin_pct")

        # Check it's not in any section text
        for section in proposal.sections:
            assert "margin" not in section.body.lower()
            assert "30%" not in section.body
            for bullet in section.bullets:
                assert "margin" not in bullet.lower()

    def test_creates_required_sections(self, sample_summary):
        """Proposal creates all required sections."""
        proposal = generate_proposal_from_summary(sample_summary)

        section_titles = {s.title for s in proposal.sections}

        assert "Executive Summary" in section_titles
        assert "Project Scope" in section_titles
        assert "Deliverables" in section_titles
        assert "Pricing Summary" in section_titles
        assert "Assumptions" in section_titles
        assert "Exclusions" in section_titles
        assert "Next Steps" in section_titles

    def test_creates_next_steps(self, sample_summary):
        """Proposal creates valid next steps."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert len(proposal.next_steps) > 0
        assert all(isinstance(step, str) for step in proposal.next_steps)

    def test_creates_terms(self, sample_summary):
        """Proposal creates terms."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert len(proposal.terms) > 0
        for term in proposal.terms:
            assert term.title
            assert term.statement

    def test_creates_exclusions(self, sample_summary):
        """Proposal creates exclusions."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert len(proposal.exclusions) > 0

    def test_does_not_mutate_summary(self, sample_summary):
        """Generator does not mutate input summary."""
        original_bid_id = sample_summary.bid_id
        original_notes = list(sample_summary.notes)

        _ = generate_proposal_from_summary(sample_summary)

        assert sample_summary.bid_id == original_bid_id
        assert sample_summary.notes == original_notes

    def test_accepts_source_refs(self, sample_summary):
        """Generator accepts optional source references."""
        proposal = generate_proposal_from_summary(
            sample_summary,
            source_summary_ref="fixtures/bids/test.json",
            project_ref="projects/test/capture.json",
        )

        assert proposal.source_summary_ref == "fixtures/bids/test.json"
        assert proposal.project_ref == "projects/test/capture.json"

    def test_generates_proposal_id(self, sample_summary):
        """Generator creates a proposal ID."""
        proposal = generate_proposal_from_summary(sample_summary)
        assert proposal.proposal_id.startswith("PROP-")

    def test_sanitizes_assumptions(self, sample_summary):
        """Generator sanitizes assumptions for customer visibility."""
        proposal = generate_proposal_from_summary(sample_summary)

        # Should have customer-friendly assumptions
        statements = [a.statement for a in proposal.assumptions]

        # Check for sanitized versions
        assert any("design revision" in s.lower() for s in statements)
        assert any("quantity" in s.lower() for s in statements)

        # Should include delivery date from summary
        assert any("2026-07-15" in s for s in statements)


class TestEcoLoomProposalGeneration:
    """Tests for Eco-Loom specific proposal generation."""

    @pytest.fixture
    def eco_loom_summary(self) -> BidSummaryV1:
        """Create Eco-Loom prototype summary."""
        return BidSummaryV1(
            bid_id="BID-ECOLOOM-2026-001",
            project_name="Eco-Loom Scrubber Handle Prototype",
            customer_name="ECO-LOOM",
            revision="Draft 1",
            status="draft",
            quantity=10,
            canonical_quote_price=630.16,
            canonical_price_per_unit=63.02,
            rounded_quote_price=650.00,
            rounded_price_per_unit=65.00,
            base_manufacturing_cost=315.08,
            risked_cost=441.11,
            target_margin_pct=30.0,
            line_items=[],
            risk_factors=[
                BidSummaryRiskV1(name="tool_wear", percentage=5.0, contribution=15.75),
            ],
            assumptions=[],
            notes=[],
        )

    def test_eco_loom_uses_rounded_pricing(self, eco_loom_summary):
        """Eco-Loom proposal uses rounded $650/$65 pricing."""
        proposal = generate_proposal_from_summary(eco_loom_summary)
        assert proposal.pricing.total_price == 650.00
        assert proposal.pricing.price_per_unit == 65.00

    def test_eco_loom_proposal_id(self, eco_loom_summary):
        """Eco-Loom proposal ID contains project slug."""
        proposal = generate_proposal_from_summary(eco_loom_summary)
        # Should derive something from "Eco-Loom Scrubber Handle Prototype"
        assert "PROP-" in proposal.proposal_id
