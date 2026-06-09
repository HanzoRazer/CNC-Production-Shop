"""Tests for bid summary fixtures and schema validation.

Dev Order: CNC-BID-CORE-2

Tests verify:
1. Schema is valid JSON Schema
2. Fixtures validate against schema
3. Schema rejects invalid data
4. Validator CLI works
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "bids"
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "schemas"
    / "bids"
    / "bid_summary_v1.schema.json"
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestBidSummarySchema:
    """Tests for bid summary schema validity."""

    def test_schema_is_valid_json_schema(self):
        """Schema is valid JSON Schema draft 2020-12."""
        schema = load_json(SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_has_required_fields(self):
        """Schema requires essential summary fields."""
        schema = load_json(SCHEMA_PATH)
        required = schema.get("required", [])

        assert "bid_id" in required
        assert "project_name" in required
        assert "customer_name" in required
        assert "revision" in required
        assert "status" in required
        assert "quantity" in required
        assert "canonical_quote_price" in required
        assert "canonical_price_per_unit" in required
        assert "base_manufacturing_cost" in required
        assert "risked_cost" in required
        assert "target_margin_pct" in required
        assert "line_items" in required
        assert "risk_factors" in required
        assert "assumptions" in required
        assert "notes" in required


class TestEcoLoomSummaryFixture:
    """Tests for Eco-Loom prototype bid summary fixture."""

    @pytest.fixture
    def fixture(self):
        """Load the Eco-Loom summary fixture."""
        return load_json(FIXTURES_DIR / "eco_loom_prototype_bid_summary_v1.json")

    @pytest.fixture
    def schema(self):
        """Load the bid summary schema."""
        return load_json(SCHEMA_PATH)

    def test_fixture_validates_against_schema(self, fixture, schema):
        """Fixture validates against bid summary schema."""
        jsonschema.validate(fixture, schema)

    def test_fixture_has_canonical_pricing(self, fixture):
        """Fixture has correct canonical pricing."""
        assert fixture["canonical_quote_price"] == 630.16
        assert fixture["canonical_price_per_unit"] == 63.02

    def test_fixture_has_rounded_pricing(self, fixture):
        """Fixture has manually set rounded pricing."""
        assert fixture["rounded_quote_price"] == 650.00
        assert fixture["rounded_price_per_unit"] == 65.00

    def test_rounded_not_equal_canonical(self, fixture):
        """Rounded pricing is distinct from canonical."""
        assert fixture["rounded_quote_price"] != fixture["canonical_quote_price"]
        assert fixture["rounded_price_per_unit"] != fixture["canonical_price_per_unit"]

    def test_fixture_has_risk_factors(self, fixture):
        """Fixture has four risk factors with contributions."""
        assert len(fixture["risk_factors"]) == 4

        for rf in fixture["risk_factors"]:
            assert "name" in rf
            assert "percentage" in rf
            assert "contribution" in rf
            assert rf["contribution"] > 0

    def test_fixture_risk_contributions_sum(self, fixture):
        """Risk contributions sum to risked_cost - base_manufacturing_cost."""
        total_contribution = sum(rf["contribution"] for rf in fixture["risk_factors"])
        expected_risk = fixture["risked_cost"] - fixture["base_manufacturing_cost"]

        # Allow small rounding difference
        assert abs(total_contribution - expected_risk) < 0.05

    def test_fixture_has_assumptions(self, fixture):
        """Fixture has assumptions with required fields."""
        assert len(fixture["assumptions"]) > 0

        for assumption in fixture["assumptions"]:
            assert "field" in assumption
            assert "value" in assumption
            assert "source" in assumption
            assert "confidence" in assumption


class TestSchemaRejectsInvalidData:
    """Tests for schema validation of invalid data."""

    @pytest.fixture
    def schema(self):
        """Load the bid summary schema."""
        return load_json(SCHEMA_PATH)

    @pytest.fixture
    def valid_summary(self):
        """Create a minimal valid summary."""
        return {
            "bid_id": "test",
            "project_name": "test",
            "customer_name": "test",
            "revision": "1",
            "status": "draft",
            "quantity": 1,
            "canonical_quote_price": 100.0,
            "canonical_price_per_unit": 100.0,
            "base_manufacturing_cost": 70.0,
            "risked_cost": 77.0,
            "target_margin_pct": 30.0,
            "line_items": [],
            "risk_factors": [],
            "assumptions": [],
            "notes": [],
        }

    def test_rejects_invalid_status(self, schema, valid_summary):
        """Invalid status value is rejected."""
        valid_summary["status"] = "pending"  # Invalid

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_summary, schema)

    def test_rejects_unknown_field(self, schema, valid_summary):
        """Unknown field is rejected by additionalProperties: false."""
        valid_summary["secret_field"] = "should fail"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_summary, schema)

    def test_rejects_margin_100(self, schema, valid_summary):
        """Target margin of 100% is rejected."""
        valid_summary["target_margin_pct"] = 100.0

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_summary, schema)

    def test_rejects_quantity_zero(self, schema, valid_summary):
        """Quantity of zero is rejected."""
        valid_summary["quantity"] = 0

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_summary, schema)

    def test_allows_null_rounded_prices(self, schema, valid_summary):
        """Null rounded prices are valid."""
        valid_summary["rounded_quote_price"] = None
        valid_summary["rounded_price_per_unit"] = None

        # Should not raise
        jsonschema.validate(valid_summary, schema)


class TestValidatorCLI:
    """Tests for bid summary validator CLI."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_bid_summaries.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout
