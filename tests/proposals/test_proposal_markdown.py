"""Tests for proposal Markdown export.

Dev Order: CNC-BID-CORE-4

Tests verify:
1. render_proposal_markdown is a pure function
2. export_proposal_markdown writes to disk
3. Generated markdown matches committed fixture
4. Header and signature blocks are optional
5. Pricing table is formatted correctly
6. Internal fields are not exposed
"""

import json
import tempfile
from pathlib import Path

import pytest

from business.proposals.markdown import (
    export_proposal_markdown,
    render_proposal_markdown,
)
from business.proposals.models import (
    ProposalAssumptionV1,
    ProposalPricingV1,
    ProposalSectionV1,
    ProposalTermV1,
    ProposalV1,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "proposals"
EXPORTS_DIR = Path(__file__).parent.parent.parent / "exports" / "proposals"


def load_proposal_from_json(path: Path) -> ProposalV1:
    """Load a ProposalV1 from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    pricing = ProposalPricingV1(
        total_price=data["pricing"]["total_price"],
        price_per_unit=data["pricing"]["price_per_unit"],
        quantity=data["pricing"]["quantity"],
        currency=data["pricing"].get("currency", "USD"),
        pricing_note=data["pricing"].get("pricing_note", ""),
    )

    sections = [
        ProposalSectionV1(
            title=s["title"],
            body=s["body"],
            bullets=s.get("bullets", []),
        )
        for s in data["sections"]
    ]

    assumptions = [
        ProposalAssumptionV1(
            statement=a["statement"],
            customer_visible=a.get("customer_visible", True),
        )
        for a in data["assumptions"]
    ]

    terms = [
        ProposalTermV1(
            title=t["title"],
            statement=t["statement"],
        )
        for t in data["terms"]
    ]

    return ProposalV1(
        proposal_id=data["proposal_id"],
        source_bid_id=data["source_bid_id"],
        project_name=data["project_name"],
        customer_name=data["customer_name"],
        revision=data["revision"],
        status=data["status"],
        created_at=data["created_at"],
        pricing=pricing,
        sections=sections,
        assumptions=assumptions,
        exclusions=data["exclusions"],
        terms=terms,
        next_steps=data["next_steps"],
        notes=data.get("notes", []),
        source_summary_ref=data.get("source_summary_ref"),
        project_ref=data.get("project_ref"),
    )


def normalize_line_endings(text: str) -> str:
    """Normalize line endings to LF for cross-platform comparison."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture
def eco_loom_proposal() -> ProposalV1:
    """Load the Eco-Loom proposal fixture."""
    return load_proposal_from_json(
        FIXTURES_DIR / "eco_loom_prototype_proposal_v1.json"
    )


@pytest.fixture
def sample_proposal() -> ProposalV1:
    """Create a minimal sample proposal for testing."""
    return ProposalV1(
        proposal_id="PROP-TEST-001",
        source_bid_id="BID-TEST-001",
        project_name="Test Project",
        customer_name="Test Customer",
        revision="Draft 1",
        status="draft",
        created_at="2026-06-09T12:00:00Z",
        pricing=ProposalPricingV1(
            total_price=100.0,
            price_per_unit=10.0,
            quantity=10,
        ),
        sections=[
            ProposalSectionV1(
                title="Executive Summary",
                body="Test summary.",
                bullets=[],
            ),
            ProposalSectionV1(
                title="Pricing Summary",
                body="Test pricing.",
                bullets=["Total: $100"],
            ),
        ],
        assumptions=[
            ProposalAssumptionV1(statement="Test assumption"),
        ],
        exclusions=["Test exclusion"],
        terms=[
            ProposalTermV1(title="Test Term", statement="Test statement"),
        ],
        next_steps=["Step 1", "Step 2"],
        notes=["Test note"],
    )


class TestRenderProposalMarkdown:
    """Tests for render_proposal_markdown function."""

    def test_returns_string(self, sample_proposal):
        """Render returns a string."""
        result = render_proposal_markdown(sample_proposal)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_proposal_id(self, sample_proposal):
        """Rendered markdown contains proposal ID."""
        result = render_proposal_markdown(sample_proposal)
        assert "PROP-TEST-001" in result

    def test_contains_project_name(self, sample_proposal):
        """Rendered markdown contains project name."""
        result = render_proposal_markdown(sample_proposal)
        assert "Test Project" in result

    def test_contains_customer_name(self, sample_proposal):
        """Rendered markdown contains customer name."""
        result = render_proposal_markdown(sample_proposal)
        assert "Test Customer" in result

    def test_contains_created_at(self, sample_proposal):
        """Rendered markdown contains created_at date."""
        result = render_proposal_markdown(sample_proposal)
        assert "2026-06-09T12:00:00Z" in result

    def test_contains_pricing_table(self, sample_proposal):
        """Rendered markdown contains pricing table."""
        result = render_proposal_markdown(sample_proposal)
        assert "| Item | Value |" in result
        assert "$100.00" in result
        assert "$10.00" in result

    def test_contains_terms(self, sample_proposal):
        """Rendered markdown contains terms section."""
        result = render_proposal_markdown(sample_proposal)
        assert "### Test Term" in result
        assert "Test statement" in result

    def test_contains_next_steps_numbered(self, sample_proposal):
        """Rendered markdown contains numbered next steps."""
        result = render_proposal_markdown(sample_proposal)
        assert "1. Step 1" in result
        assert "2. Step 2" in result

    def test_contains_signature_block_by_default(self, sample_proposal):
        """Rendered markdown contains signature block by default."""
        result = render_proposal_markdown(sample_proposal)
        assert "## Acceptance" in result
        assert "Authorized Signature" in result

    def test_signature_block_optional(self, sample_proposal):
        """Signature block can be excluded."""
        result = render_proposal_markdown(sample_proposal, include_signature=False)
        assert "## Acceptance" not in result
        assert "Authorized Signature" not in result

    def test_header_optional(self, sample_proposal):
        """Header block can be excluded."""
        result = render_proposal_markdown(sample_proposal, include_header=False)
        assert "Texas Guitar Exchange" not in result
        # But section content should still be present
        assert "Test summary." in result

    def test_does_not_expose_margin(self, sample_proposal):
        """Rendered markdown does not contain margin."""
        result = render_proposal_markdown(sample_proposal)
        assert "margin" not in result.lower()
        assert "target_margin" not in result.lower()

    def test_does_not_expose_risk_factors(self, sample_proposal):
        """Rendered markdown does not contain risk factors."""
        result = render_proposal_markdown(sample_proposal)
        assert "risk_factor" not in result.lower()
        assert "tool_wear" not in result.lower()
        assert "contingency" not in result.lower()


class TestExportProposalMarkdown:
    """Tests for export_proposal_markdown function."""

    def test_writes_file(self, sample_proposal):
        """Export writes a file to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.md"
            result = export_proposal_markdown(sample_proposal, output_path)

            assert result == output_path
            assert output_path.exists()
            content = output_path.read_text()
            assert "PROP-TEST-001" in content

    def test_creates_parent_directories(self, sample_proposal):
        """Export creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "test.md"
            result = export_proposal_markdown(sample_proposal, output_path)

            assert result == output_path
            assert output_path.exists()

    def test_default_path_uses_proposal_id(self, sample_proposal):
        """Default output path uses proposal ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily change the default exports dir
            import business.proposals.markdown as md_module

            original_dir = md_module.DEFAULT_EXPORTS_DIR
            md_module.DEFAULT_EXPORTS_DIR = Path(tmpdir)

            try:
                result = export_proposal_markdown(sample_proposal)
                assert result.name == "PROP-TEST-001.md"
            finally:
                md_module.DEFAULT_EXPORTS_DIR = original_dir


class TestEcoLoomMarkdownFixture:
    """Tests for Eco-Loom markdown fixture regeneration."""

    def test_regenerated_matches_fixture(self, eco_loom_proposal):
        """Regenerated markdown matches committed fixture (normalized)."""
        expected_path = EXPORTS_DIR / "PROP-ECOLOOM-2026-001.md"
        assert expected_path.exists(), f"Fixture not found: {expected_path}"

        expected = normalize_line_endings(expected_path.read_text(encoding="utf-8"))
        generated = normalize_line_endings(render_proposal_markdown(eco_loom_proposal))

        assert generated == expected, (
            "Generated markdown does not match committed fixture. "
            "Regenerate with: python scripts/export_proposal.py"
        )

    def test_fixture_contains_rounded_pricing(self, eco_loom_proposal):
        """Fixture uses rounded customer pricing."""
        result = render_proposal_markdown(eco_loom_proposal)
        assert "$650.00" in result
        assert "$65.00" in result

    def test_fixture_does_not_contain_canonical_pricing(self, eco_loom_proposal):
        """Fixture does not expose canonical internal pricing."""
        result = render_proposal_markdown(eco_loom_proposal)
        assert "$630.16" not in result
        assert "$63.02" not in result
