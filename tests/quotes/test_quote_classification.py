"""Tests for quote classification schema and Eco-Loom clarification.

Dev Order: ECO-LOOM-QUOTE-CORRECTION-1

Tests verify:
1. Quote classification schema is valid
2. Eco-Loom clarification artifact validates
3. Schema rejects invalid data
4. Clarification content is correct
5. Referenced artifacts exist
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "quotes"
ROOT_DIR = Path(__file__).parent.parent.parent


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestQuoteClassificationSchema:
    """Verify quote classification schema structure."""

    @pytest.fixture
    def schema(self):
        """Load classification schema."""
        return load_json(SCHEMA_DIR / "quote_classification_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "classification_id" in required
        assert "project_name" in required
        assert "customer_name" in required
        assert "document_type" in required
        assert "status" in required
        assert "pricing_status" in required
        assert "formal_quote_requirements" in required

    def test_schema_disallows_additional_properties(self, schema):
        """Schema rejects unknown fields."""
        assert schema["additionalProperties"] is False

    def test_rejects_unknown_document_type(self, schema):
        """Schema rejects unknown document_type."""
        invalid = {
            "classification_id": "QC-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "document_type": "UNKNOWN_TYPE",  # Invalid
            "status": "active",
            "created_at": "2026-06-01T12:00:00Z",
            "applies_to": [],
            "clarification_summary": "Test",
            "pricing_status": "budgetary_estimate",
            "formal_quote_requirements": [],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_unknown_pricing_status(self, schema):
        """Schema rejects unknown pricing_status."""
        invalid = {
            "classification_id": "QC-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "document_type": "BUDGETARY_PRODUCTION_ESTIMATE",
            "status": "active",
            "created_at": "2026-06-01T12:00:00Z",
            "applies_to": [],
            "clarification_summary": "Test",
            "pricing_status": "unknown_status",  # Invalid
            "formal_quote_requirements": [],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_unknown_field(self, schema):
        """Schema rejects unknown fields."""
        invalid = {
            "classification_id": "QC-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "document_type": "BUDGETARY_PRODUCTION_ESTIMATE",
            "status": "active",
            "created_at": "2026-06-01T12:00:00Z",
            "applies_to": [],
            "clarification_summary": "Test",
            "pricing_status": "budgetary_estimate",
            "formal_quote_requirements": [],
            "notes": [],
            "unknown_field": "value",  # Unknown
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestEcoLoomClarificationValidates:
    """Verify Eco-Loom clarification artifact validates."""

    @pytest.fixture
    def clarification(self):
        """Load Eco-Loom clarification."""
        return load_json(PROJECT_DIR / "eco_loom_quote_clarification_2026_06_v1.json")

    @pytest.fixture
    def schema(self):
        """Load classification schema."""
        return load_json(SCHEMA_DIR / "quote_classification_v1.schema.json")

    def test_clarification_validates(self, clarification, schema):
        """Clarification validates against schema."""
        jsonschema.validate(clarification, schema)

    def test_classification_id_format(self, clarification):
        """Classification ID follows expected format."""
        assert clarification["classification_id"] == "QC-ECOLOOM-2026-001"

    def test_document_type_is_budgetary_estimate(self, clarification):
        """Document type is BUDGETARY_PRODUCTION_ESTIMATE."""
        assert clarification["document_type"] == "BUDGETARY_PRODUCTION_ESTIMATE"

    def test_pricing_status_is_budgetary(self, clarification):
        """Pricing status is budgetary_estimate."""
        assert clarification["pricing_status"] == "budgetary_estimate"

    def test_status_is_active(self, clarification):
        """Status is active."""
        assert clarification["status"] == "active"


class TestClarificationContent:
    """Verify clarification content is correct."""

    @pytest.fixture
    def clarification(self):
        """Load Eco-Loom clarification."""
        return load_json(PROJECT_DIR / "eco_loom_quote_clarification_2026_06_v1.json")

    def test_clarification_says_direct_cost_not_formal_quote(self, clarification):
        """Clarification states direct cost is not formal quote price."""
        summary = clarification["clarification_summary"].lower()
        notes = " ".join(clarification["notes"]).lower()
        combined = summary + " " + notes

        assert "direct" in combined
        assert "not" in combined or "should not" in combined
        assert "formal" in combined or "quote price" in combined

    def test_formal_quote_requirements_include_finish(self, clarification):
        """Formal quote requirements include finish specification."""
        requirements = [r.lower() for r in clarification["formal_quote_requirements"]]
        assert any("finish" in r for r in requirements)

    def test_formal_quote_requirements_include_packaging(self, clarification):
        """Formal quote requirements include packaging."""
        requirements = [r.lower() for r in clarification["formal_quote_requirements"]]
        assert any("packaging" in r for r in requirements)

    def test_formal_quote_requirements_include_delivery(self, clarification):
        """Formal quote requirements include delivery schedule."""
        requirements = [r.lower() for r in clarification["formal_quote_requirements"]]
        assert any("delivery" in r for r in requirements)

    def test_formal_quote_requirements_include_shipping(self, clarification):
        """Formal quote requirements include shipping responsibility."""
        requirements = [r.lower() for r in clarification["formal_quote_requirements"]]
        assert any("shipping" in r for r in requirements)

    def test_formal_quote_requirements_include_inspection(self, clarification):
        """Formal quote requirements include inspection."""
        requirements = [r.lower() for r in clarification["formal_quote_requirements"]]
        assert any("inspection" in r or "quality" in r for r in requirements)


class TestReferencedArtifactsExist:
    """Verify repo-local referenced artifacts exist."""

    @pytest.fixture
    def clarification(self):
        """Load Eco-Loom clarification."""
        return load_json(PROJECT_DIR / "eco_loom_quote_clarification_2026_06_v1.json")

    def test_quote_package_exists(self, clarification):
        """Quote package reference exists."""
        ref = "projects/eco_loom/eco_loom_production_quote_package_v1.json"
        assert ref in clarification["applies_to"]
        assert (ROOT_DIR / ref).exists()

    def test_quote_revision_exists(self, clarification):
        """Quote revision reference exists."""
        ref = "projects/eco_loom/eco_loom_production_quote_revision_a_v1.json"
        assert ref in clarification["applies_to"]
        assert (ROOT_DIR / ref).exists()

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_proposal_exists(self, clarification, tier):
        """Proposal reference exists."""
        ref = f"fixtures/proposals/eco_loom_production_proposal_{tier}_v1.json"
        assert ref in clarification["applies_to"]
        assert (ROOT_DIR / ref).exists()

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_markdown_exists(self, clarification, tier):
        """Markdown export reference exists."""
        ref = f"exports/proposals/PROP-ECOLOOM-PROD-{tier}-2026-001.md"
        assert ref in clarification["applies_to"]
        assert (ROOT_DIR / ref).exists()


class TestMarkdownDoesNotMisrepresentPricing:
    """Verify markdown files do not present direct costs as quoted prices."""

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_markdown_does_not_show_direct_cost_as_price(self, tier):
        """Markdown does not show direct manufacturing cost as total price."""
        direct_costs = {100: 432, 250: 1029, 500: 2058}
        direct_cost = direct_costs[tier]

        path = ROOT_DIR / f"exports/proposals/PROP-ECOLOOM-PROD-{tier}-2026-001.md"
        content = path.read_text()

        assert f"${direct_cost}" not in content
        assert f"${direct_cost}.00" not in content

    @pytest.mark.parametrize("tier", [100, 250, 500])
    def test_markdown_shows_budgetary_prices(self, tier):
        """Markdown shows budgetary estimate prices (rounded)."""
        budgetary_prices = {100: "$875", 250: "$2,100", 500: "$4,150"}
        price = budgetary_prices[tier]

        path = ROOT_DIR / f"exports/proposals/PROP-ECOLOOM-PROD-{tier}-2026-001.md"
        content = path.read_text()

        assert price in content or f"{price}.00" in content


class TestValidatorCLI:
    """Verify validator CLI works correctly."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_quote_classifications.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "RESULT: PASS" in result.stdout
