"""Tests for proposal fixtures and schema validation.

Dev Order: CNC-BID-CORE-3

Tests verify:
1. Schema is valid JSON Schema
2. Fixtures validate against schema
3. Schema rejects invalid data
4. Proposal does not contain internal bid details
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "proposals"
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "schemas"
    / "proposals"
    / "proposal_v1.schema.json"
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestProposalSchema:
    """Tests for proposal schema validity."""

    def test_schema_is_valid_json_schema(self):
        """Schema is valid JSON Schema draft 2020-12."""
        schema = load_json(SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_has_required_fields(self):
        """Schema requires essential proposal fields."""
        schema = load_json(SCHEMA_PATH)
        required = schema.get("required", [])

        assert "proposal_id" in required
        assert "source_bid_id" in required
        assert "project_name" in required
        assert "customer_name" in required
        assert "revision" in required
        assert "status" in required
        assert "created_at" in required
        assert "pricing" in required
        assert "sections" in required
        assert "assumptions" in required
        assert "exclusions" in required
        assert "terms" in required
        assert "next_steps" in required
        assert "notes" in required


class TestEcoLoomProposalFixture:
    """Tests for Eco-Loom prototype proposal fixture."""

    @pytest.fixture
    def fixture(self):
        """Load the Eco-Loom proposal fixture."""
        return load_json(FIXTURES_DIR / "eco_loom_prototype_proposal_v1.json")

    @pytest.fixture
    def schema(self):
        """Load the proposal schema."""
        return load_json(SCHEMA_PATH)

    def test_fixture_validates_against_schema(self, fixture, schema):
        """Fixture validates against proposal schema."""
        jsonschema.validate(fixture, schema)

    def test_fixture_uses_rounded_pricing(self, fixture):
        """Fixture uses rounded pricing for customer display."""
        assert fixture["pricing"]["total_price"] == 650.00
        assert fixture["pricing"]["price_per_unit"] == 65.00

    def test_fixture_does_not_contain_target_margin_pct(self, fixture):
        """Fixture does not expose target_margin_pct."""
        fixture_str = json.dumps(fixture)
        assert "target_margin_pct" not in fixture_str
        assert '"margin"' not in fixture_str.lower()

    def test_fixture_does_not_contain_risk_factors(self, fixture):
        """Fixture does not expose risk_factors."""
        fixture_str = json.dumps(fixture)
        assert "risk_factors" not in fixture_str
        assert "tool_wear" not in fixture_str
        assert "contingency" not in fixture_str.lower()

    def test_fixture_does_not_contain_risked_cost(self, fixture):
        """Fixture does not expose risked_cost."""
        fixture_str = json.dumps(fixture)
        assert "risked_cost" not in fixture_str
        assert "441.11" not in fixture_str

    def test_fixture_has_sections(self, fixture):
        """Fixture has proposal sections."""
        assert len(fixture["sections"]) >= 5

        section_titles = {s["title"] for s in fixture["sections"]}
        assert "Executive Summary" in section_titles
        assert "Project Scope" in section_titles
        assert "Pricing Summary" in section_titles

    def test_fixture_has_assumptions(self, fixture):
        """Fixture has customer-visible assumptions."""
        assert len(fixture["assumptions"]) > 0
        for assumption in fixture["assumptions"]:
            assert "statement" in assumption

    def test_fixture_has_terms(self, fixture):
        """Fixture has terms."""
        assert len(fixture["terms"]) > 0
        for term in fixture["terms"]:
            assert "title" in term
            assert "statement" in term

    def test_fixture_has_superseded_note(self, fixture):
        """Fixture notes that prototype assumptions are superseded."""
        notes_str = " ".join(fixture["notes"])
        assert "superseded" in notes_str.lower()


class TestSchemaRejectsInvalidData:
    """Tests for schema validation of invalid data."""

    @pytest.fixture
    def schema(self):
        """Load the proposal schema."""
        return load_json(SCHEMA_PATH)

    @pytest.fixture
    def valid_proposal(self):
        """Create a minimal valid proposal."""
        return {
            "proposal_id": "PROP-TEST-001",
            "source_bid_id": "BID-TEST-001",
            "project_name": "Test",
            "customer_name": "Test",
            "revision": "1",
            "status": "draft",
            "created_at": "2026-06-09T12:00:00Z",
            "pricing": {
                "total_price": 100.0,
                "price_per_unit": 10.0,
                "quantity": 10,
            },
            "sections": [],
            "assumptions": [],
            "exclusions": [],
            "terms": [],
            "next_steps": [],
            "notes": [],
        }

    def test_rejects_invalid_status(self, schema, valid_proposal):
        """Invalid status value is rejected."""
        valid_proposal["status"] = "pending"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_proposal, schema)

    def test_rejects_unknown_field(self, schema, valid_proposal):
        """Unknown field is rejected by additionalProperties: false."""
        valid_proposal["target_margin_pct"] = 30.0

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_proposal, schema)

    def test_rejects_negative_total_price(self, schema, valid_proposal):
        """Negative total_price is rejected."""
        valid_proposal["pricing"]["total_price"] = -100.0

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_proposal, schema)

    def test_rejects_quantity_zero(self, schema, valid_proposal):
        """Quantity of zero is rejected."""
        valid_proposal["pricing"]["quantity"] = 0

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_proposal, schema)

    def test_rejects_risk_factors_field(self, schema, valid_proposal):
        """risk_factors field is rejected (not allowed in proposals)."""
        valid_proposal["risk_factors"] = []

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_proposal, schema)


class TestValidatorCLI:
    """Tests for proposal validator CLI."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_proposals.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout
