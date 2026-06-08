"""Tests for bid fixtures and schema validation.

Dev Order: CNC-BID-CORE-1

Tests verify:
1. Schema is valid JSON Schema
2. Fixtures validate against schema
3. Fixture values match calculator
4. Schema rejects invalid data
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from business.bids import (
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "bids"
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schemas" / "bids" / "bid_v1.schema.json"
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestBidSchema:
    """Tests for bid schema validity."""

    def test_schema_is_valid_json_schema(self):
        """Schema is valid JSON Schema draft 2020-12."""
        schema = load_json(SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_has_required_fields(self):
        """Schema requires essential bid fields."""
        schema = load_json(SCHEMA_PATH)
        required = schema.get("required", [])

        assert "bid_id" in required
        assert "project_name" in required
        assert "customer_name" in required
        assert "revision" in required
        assert "status" in required
        assert "created_at" in required
        assert "updated_at" in required
        assert "assumptions" in required
        assert "line_items" in required
        assert "cost_basis" in required
        assert "pricing" in required
        assert "notes" in required


class TestEcoLoomPrototypeBid:
    """Tests for Eco-Loom prototype bid fixture."""

    @pytest.fixture
    def fixture(self):
        """Load the Eco-Loom prototype bid fixture."""
        return load_json(FIXTURES_DIR / "eco_loom_prototype_bid_v1.json")

    @pytest.fixture
    def schema(self):
        """Load the bid schema."""
        return load_json(SCHEMA_PATH)

    def test_fixture_validates_against_schema(self, fixture, schema):
        """Fixture validates against bid schema."""
        jsonschema.validate(fixture, schema)

    def test_fixture_cost_basis_sums_correctly(self, fixture):
        """Cost basis base_manufacturing_cost matches component sum."""
        cost_basis = fixture["cost_basis"]

        expected_sum = (
            cost_basis["direct_material_cost"]
            + cost_basis["direct_labor_cost"]
            + cost_basis["machine_time_cost"]
            + cost_basis["tooling_cost"]
            + cost_basis["setup_cost"]
            + cost_basis["finishing_cost"]
            + cost_basis["finishing_material_cost"]
            + cost_basis["engineering_cost"]
        )

        assert cost_basis["base_manufacturing_cost"] == expected_sum

    def test_fixture_risked_cost_matches_calculator(self, fixture):
        """Risked cost matches calculator output."""
        cost_basis = fixture["cost_basis"]
        pricing = fixture["pricing"]

        calculated = calculate_risked_cost(
            base_cost=cost_basis["base_manufacturing_cost"],
            tool_wear_pct=pricing["tool_wear_pct"],
            manufacturing_contingency_pct=pricing["manufacturing_contingency_pct"],
            business_overhead_pct=pricing["business_overhead_pct"],
            engineering_recovery_pct=pricing["engineering_recovery_pct"],
        )

        assert pricing["risked_cost"] == calculated

    def test_fixture_quote_price_matches_calculator(self, fixture):
        """Quote price matches calculator output."""
        pricing = fixture["pricing"]

        calculated = calculate_bid_price(
            risked_cost=pricing["risked_cost"],
            target_margin_pct=pricing["target_margin_pct"],
        )

        assert pricing["quote_price"] == calculated

    def test_fixture_price_per_unit_matches_calculator(self, fixture):
        """Price per unit matches calculator output."""
        pricing = fixture["pricing"]

        calculated = calculate_price_per_unit(
            quote_price=pricing["quote_price"],
            quantity=pricing["quantity"],
        )

        assert pricing["price_per_unit"] == calculated

    def test_customer_rounded_number_not_canonical(self, fixture):
        """Customer-facing rounded number is not the canonical quote_price."""
        pricing = fixture["pricing"]
        notes = fixture["notes"]

        # Canonical quote_price is calculated value
        assert pricing["quote_price"] == 630.16

        # Rounded recommendation is only in notes, not in pricing
        has_rounded_note = any("$650" in note or "$65 per unit" in note for note in notes)
        assert has_rounded_note, "Rounded recommendation should be in notes"

        # Canonical price is NOT the rounded number
        assert pricing["quote_price"] != 650.0
        assert pricing["price_per_unit"] != 65.0


class TestSchemaRejectsInvalidData:
    """Tests for schema validation of invalid data."""

    @pytest.fixture
    def schema(self):
        """Load the bid schema."""
        return load_json(SCHEMA_PATH)

    def test_rejects_invalid_status(self, schema):
        """Invalid status value is rejected."""
        invalid = {
            "bid_id": "test",
            "project_name": "test",
            "customer_name": "test",
            "revision": "1",
            "status": "pending",  # Invalid
            "created_at": "2026-06-08T12:00:00Z",
            "updated_at": "2026-06-08T12:00:00Z",
            "assumptions": [],
            "line_items": [],
            "cost_basis": {
                "direct_material_cost": 0,
                "direct_labor_cost": 0,
                "machine_time_cost": 0,
                "tooling_cost": 0,
                "setup_cost": 0,
                "finishing_cost": 0,
                "finishing_material_cost": 0,
                "engineering_cost": 0,
                "base_manufacturing_cost": 0,
            },
            "pricing": {
                "tool_wear_pct": 0,
                "manufacturing_contingency_pct": 0,
                "business_overhead_pct": 0,
                "engineering_recovery_pct": 0,
                "target_margin_pct": 30,
                "risked_cost": 0,
                "quote_price": 0,
                "quantity": 1,
                "price_per_unit": 0,
            },
            "notes": [],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_margin_100(self, schema):
        """Target margin of 100% is rejected."""
        invalid = {
            "bid_id": "test",
            "project_name": "test",
            "customer_name": "test",
            "revision": "1",
            "status": "draft",
            "created_at": "2026-06-08T12:00:00Z",
            "updated_at": "2026-06-08T12:00:00Z",
            "assumptions": [],
            "line_items": [],
            "cost_basis": {
                "direct_material_cost": 0,
                "direct_labor_cost": 0,
                "machine_time_cost": 0,
                "tooling_cost": 0,
                "setup_cost": 0,
                "finishing_cost": 0,
                "finishing_material_cost": 0,
                "engineering_cost": 0,
                "base_manufacturing_cost": 0,
            },
            "pricing": {
                "tool_wear_pct": 0,
                "manufacturing_contingency_pct": 0,
                "business_overhead_pct": 0,
                "engineering_recovery_pct": 0,
                "target_margin_pct": 100,  # Invalid
                "risked_cost": 0,
                "quote_price": 0,
                "quantity": 1,
                "price_per_unit": 0,
            },
            "notes": [],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_unknown_field(self, schema):
        """Unknown field is rejected by additionalProperties: false."""
        invalid = {
            "bid_id": "test",
            "project_name": "test",
            "customer_name": "test",
            "revision": "1",
            "status": "draft",
            "created_at": "2026-06-08T12:00:00Z",
            "updated_at": "2026-06-08T12:00:00Z",
            "assumptions": [],
            "line_items": [],
            "cost_basis": {
                "direct_material_cost": 0,
                "direct_labor_cost": 0,
                "machine_time_cost": 0,
                "tooling_cost": 0,
                "setup_cost": 0,
                "finishing_cost": 0,
                "finishing_material_cost": 0,
                "engineering_cost": 0,
                "base_manufacturing_cost": 0,
            },
            "pricing": {
                "tool_wear_pct": 0,
                "manufacturing_contingency_pct": 0,
                "business_overhead_pct": 0,
                "engineering_recovery_pct": 0,
                "target_margin_pct": 30,
                "risked_cost": 0,
                "quote_price": 0,
                "quantity": 1,
                "price_per_unit": 0,
            },
            "notes": [],
            "secret_field": "should fail",  # Unknown field
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_quantity_zero(self, schema):
        """Quantity of zero is rejected."""
        invalid = {
            "bid_id": "test",
            "project_name": "test",
            "customer_name": "test",
            "revision": "1",
            "status": "draft",
            "created_at": "2026-06-08T12:00:00Z",
            "updated_at": "2026-06-08T12:00:00Z",
            "assumptions": [],
            "line_items": [],
            "cost_basis": {
                "direct_material_cost": 0,
                "direct_labor_cost": 0,
                "machine_time_cost": 0,
                "tooling_cost": 0,
                "setup_cost": 0,
                "finishing_cost": 0,
                "finishing_material_cost": 0,
                "engineering_cost": 0,
                "base_manufacturing_cost": 0,
            },
            "pricing": {
                "tool_wear_pct": 0,
                "manufacturing_contingency_pct": 0,
                "business_overhead_pct": 0,
                "engineering_recovery_pct": 0,
                "target_margin_pct": 30,
                "risked_cost": 0,
                "quote_price": 0,
                "quantity": 0,  # Invalid
                "price_per_unit": 0,
            },
            "notes": [],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestValidatorCLI:
    """Tests for bid validator CLI."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_bid_fixtures.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout
