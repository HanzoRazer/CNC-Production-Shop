"""Tests for Eco-Loom production bid revision.

Dev Order: ECO-LOOM-BID-REVISION-1

Tests verify:
1. Production bid fixtures validate
2. Wood board-foot calculation is correct
3. Velcro roll procurement is correct
4. Direct manufacturing costs match expected values
5. Prototype fixture remains unchanged
6. Production proposals do not expose margin/risk
7. Markdown exports exist
"""

import json
from pathlib import Path

import jsonschema
import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
EXPORTS_DIR = Path(__file__).parent.parent.parent / "exports" / "proposals"
SCHEMAS_DIR = Path(__file__).parent.parent.parent / "schemas"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestProductionBidFixturesValidate:
    """Verify production bid fixtures validate against schema."""

    @pytest.fixture
    def bid_schema(self):
        """Load bid schema."""
        return load_json(SCHEMAS_DIR / "bids" / "bid_v1.schema.json")

    @pytest.fixture
    def summary_schema(self):
        """Load bid summary schema."""
        return load_json(SCHEMAS_DIR / "bids" / "bid_summary_v1.schema.json")

    @pytest.fixture
    def proposal_schema(self):
        """Load proposal schema."""
        return load_json(SCHEMAS_DIR / "proposals" / "proposal_v1.schema.json")

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_production_bid_validates(self, bid_schema, tier):
        """Production bid fixture validates against schema."""
        fixture = load_json(
            FIXTURES_DIR / "bids" / f"eco_loom_production_bid_{tier}_v1.json"
        )
        jsonschema.validate(fixture, bid_schema)

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_production_summary_validates(self, summary_schema, tier):
        """Production bid summary validates against schema."""
        fixture = load_json(
            FIXTURES_DIR / "bids" / f"eco_loom_production_bid_summary_{tier}_v1.json"
        )
        jsonschema.validate(fixture, summary_schema)

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_production_proposal_validates(self, proposal_schema, tier):
        """Production proposal validates against schema."""
        fixture = load_json(
            FIXTURES_DIR / "proposals" / f"eco_loom_production_proposal_{tier}_v1.json"
        )
        jsonschema.validate(fixture, proposal_schema)


class TestWoodBoardFootCalculation:
    """Verify wood board-foot calculation is correct."""

    def test_board_foot_calculation(self):
        """Board feet = (L × W × H) / 144."""
        # Handle blank: 5" × 3" × 1.25"
        length = 5.0
        width = 3.0
        height = 1.25

        board_feet = (length * width * height) / 144
        assert abs(board_feet - 0.1302) < 0.001

    def test_wood_cost_per_unit_with_waste(self):
        """Wood cost per unit with 15% waste allowance."""
        board_feet = 0.1302
        price_per_bf = 17.0
        waste_pct = 15.0

        raw_cost = board_feet * price_per_bf
        with_waste = raw_cost * (1 + waste_pct / 100)

        # Expected: $2.54 per unit
        assert abs(with_waste - 2.54) < 0.01

    @pytest.mark.parametrize(
        "tier,expected_wood_cost",
        [
            (100, 254.00),
            (250, 635.00),
            (500, 1270.00),
        ],
    )
    def test_wood_cost_in_fixture(self, tier, expected_wood_cost):
        """Wood cost in fixture matches calculation."""
        fixture = load_json(
            FIXTURES_DIR / "bids" / f"eco_loom_production_bid_{tier}_v1.json"
        )
        wood_item = next(
            item for item in fixture["line_items"] if item["name"] == "Wood Material"
        )
        assert wood_item["total_cost"] == expected_wood_cost


class TestVelcroRollProcurement:
    """Verify Velcro roll procurement is correct."""

    @pytest.mark.parametrize(
        "tier,expected_rolls,expected_cost",
        [
            (100, 1, 34.00),
            (250, 1, 34.00),
            (500, 2, 68.00),
        ],
    )
    def test_velcro_rolls_in_fixture(self, tier, expected_rolls, expected_cost):
        """Velcro roll count and cost in fixture matches procurement model."""
        fixture = load_json(
            FIXTURES_DIR / "bids" / f"eco_loom_production_bid_{tier}_v1.json"
        )
        velcro_item = next(
            item for item in fixture["line_items"] if item["name"] == "Velcro Material"
        )
        assert velcro_item["quantity"] == expected_rolls
        assert velcro_item["total_cost"] == expected_cost


class TestDirectManufacturingCosts:
    """Verify direct manufacturing costs match expected values."""

    @pytest.mark.parametrize(
        "tier,expected_material,expected_machine,expected_total",
        [
            (100, 288.00, 144.00, 432.00),
            (250, 669.00, 360.00, 1029.00),
            (500, 1338.00, 720.00, 2058.00),
        ],
    )
    def test_direct_costs(self, tier, expected_material, expected_machine, expected_total):
        """Direct manufacturing costs match expected values."""
        fixture = load_json(
            FIXTURES_DIR / "bids" / f"eco_loom_production_bid_{tier}_v1.json"
        )

        cost_basis = fixture["cost_basis"]
        assert cost_basis["direct_material_cost"] == expected_material
        assert cost_basis["machine_time_cost"] == expected_machine
        assert cost_basis["base_manufacturing_cost"] == expected_total


class TestPrototypeFixtureUnchanged:
    """Verify prototype fixture remains unchanged."""

    def test_prototype_bid_exists(self):
        """Prototype bid fixture still exists."""
        path = FIXTURES_DIR / "bids" / "eco_loom_prototype_bid_v1.json"
        assert path.exists()

    def test_prototype_quantity_is_10(self):
        """Prototype bid quantity is still 10."""
        fixture = load_json(FIXTURES_DIR / "bids" / "eco_loom_prototype_bid_v1.json")
        assert fixture["pricing"]["quantity"] == 10

    def test_prototype_customer_supplied(self):
        """Prototype bid uses customer-supplied materials."""
        fixture = load_json(FIXTURES_DIR / "bids" / "eco_loom_prototype_bid_v1.json")
        material_assumption = next(
            a for a in fixture["assumptions"] if a["field"] == "material_supply"
        )
        assert material_assumption["value"] == "customer-supplied"


class TestProposalDoesNotExposeInternals:
    """Verify production proposals do not expose margin/risk."""

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_no_margin_in_proposal(self, tier):
        """Proposal does not contain target_margin_pct."""
        fixture = load_json(
            FIXTURES_DIR / "proposals" / f"eco_loom_production_proposal_{tier}_v1.json"
        )
        fixture_str = json.dumps(fixture)
        assert "target_margin" not in fixture_str.lower()
        assert "margin" not in fixture_str.lower()

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_no_risk_factors_in_proposal(self, tier):
        """Proposal does not contain risk_factors."""
        fixture = load_json(
            FIXTURES_DIR / "proposals" / f"eco_loom_production_proposal_{tier}_v1.json"
        )
        fixture_str = json.dumps(fixture)
        assert "risk_factor" not in fixture_str.lower()
        assert "tool_wear" not in fixture_str.lower()
        assert "contingency" not in fixture_str.lower()


class TestMarkdownExportsExist:
    """Verify markdown exports exist."""

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_markdown_export_exists(self, tier):
        """Markdown export file exists."""
        path = EXPORTS_DIR / f"PROP-ECOLOOM-PROD-{tier}-2026-001.md"
        assert path.exists(), f"Markdown export not found: {path}"

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_markdown_contains_pricing(self, tier):
        """Markdown export contains pricing table."""
        path = EXPORTS_DIR / f"PROP-ECOLOOM-PROD-{tier}-2026-001.md"
        content = path.read_text()
        assert "| Item | Value |" in content
        assert "Total Price" in content
