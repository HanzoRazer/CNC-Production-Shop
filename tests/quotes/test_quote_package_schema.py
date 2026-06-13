"""Tests for quote package and revision schemas.

Dev Order: CNC-QUOTE-PACKAGE-1

Tests verify:
1. Schemas are valid JSON Schema
2. Schemas enforce required fields
3. Schemas reject invalid data
"""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "quotes"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestQuotePackageSchema:
    """Verify quote package schema structure."""

    @pytest.fixture
    def schema(self):
        """Load quote package schema."""
        return load_json(SCHEMA_DIR / "quote_package_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "package_id" in required
        assert "project_name" in required
        assert "customer_name" in required
        assert "created_at" in required
        assert "status" in required
        assert "revisions" in required
        assert "notes" in required

    def test_schema_disallows_additional_properties(self, schema):
        """Schema rejects unknown fields."""
        assert schema["additionalProperties"] is False

    def test_valid_package_validates(self, schema):
        """Valid package data validates."""
        valid = {
            "package_id": "QP-TEST-2026-001",
            "project_name": "Test Project",
            "customer_name": "Test Customer",
            "project_ref": None,
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "revisions": [],
            "notes": [],
        }
        jsonschema.validate(valid, schema)

    def test_rejects_invalid_status(self, schema):
        """Schema rejects invalid package status."""
        invalid = {
            "package_id": "QP-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "pending",  # Invalid
            "revisions": [],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_invalid_package_id_format(self, schema):
        """Schema rejects invalid package ID pattern."""
        invalid = {
            "package_id": "invalid-id",  # Invalid pattern
            "project_name": "Test",
            "customer_name": "Test",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "revisions": [],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_unknown_field(self, schema):
        """Schema rejects unknown fields."""
        invalid = {
            "package_id": "QP-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "revisions": [],
            "notes": [],
            "unknown_field": "value",  # Unknown
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestQuoteRevisionSchema:
    """Verify quote revision schema structure."""

    @pytest.fixture
    def schema(self):
        """Load quote revision schema."""
        return load_json(SCHEMA_DIR / "quote_revision_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "revision_id" in required
        assert "package_ref" in required
        assert "revision_letter" in required
        assert "created_at" in required
        assert "status" in required
        assert "options" in required
        assert "notes" in required

    def test_schema_disallows_additional_properties(self, schema):
        """Schema rejects unknown fields."""
        assert schema["additionalProperties"] is False

    def test_valid_revision_validates(self, schema):
        """Valid revision data validates."""
        valid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "projects/test/package.json",
            "revision_letter": "A",
            "revision_reason": None,
            "supersedes": None,
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "workbook_ref": None,
            "options": [
                {
                    "option_id": "OPT-TEST-100",
                    "label": "100 units",
                    "quantity": 100,
                    "status": "active",
                    "bid_ref": "fixtures/bids/test.json",
                    "bid_summary_ref": "fixtures/bids/test_summary.json",
                    "proposal_ref": "fixtures/proposals/test.json",
                    "markdown_ref": None,
                    "notes": [],
                }
            ],
            "notes": [],
        }
        jsonschema.validate(valid, schema)

    def test_rejects_invalid_status(self, schema):
        """Schema rejects invalid revision status."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "A",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "pending",  # Invalid
            "options": [
                {
                    "option_id": "OPT-1",
                    "label": "100",
                    "quantity": 100,
                    "status": "active",
                    "bid_ref": "test.json",
                    "bid_summary_ref": "test.json",
                    "proposal_ref": "test.json",
                    "notes": [],
                }
            ],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_invalid_option_status(self, schema):
        """Schema rejects invalid option status."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "A",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "options": [
                {
                    "option_id": "OPT-1",
                    "label": "100",
                    "quantity": 100,
                    "status": "pending",  # Invalid
                    "bid_ref": "test.json",
                    "bid_summary_ref": "test.json",
                    "proposal_ref": "test.json",
                    "notes": [],
                }
            ],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_quantity_zero(self, schema):
        """Schema rejects quantity of zero."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "A",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "options": [
                {
                    "option_id": "OPT-1",
                    "label": "0",
                    "quantity": 0,  # Invalid
                    "status": "active",
                    "bid_ref": "test.json",
                    "bid_summary_ref": "test.json",
                    "proposal_ref": "test.json",
                    "notes": [],
                }
            ],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_invalid_revision_letter(self, schema):
        """Schema rejects multi-character revision letter."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "AA",  # Invalid - must be single letter
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "options": [
                {
                    "option_id": "OPT-1",
                    "label": "100",
                    "quantity": 100,
                    "status": "active",
                    "bid_ref": "test.json",
                    "bid_summary_ref": "test.json",
                    "proposal_ref": "test.json",
                    "notes": [],
                }
            ],
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_empty_options(self, schema):
        """Schema requires at least one option."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "A",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "options": [],  # Invalid - minItems: 1
            "notes": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_unknown_field(self, schema):
        """Schema rejects unknown fields."""
        invalid = {
            "revision_id": "QR-TEST-2026-001-A",
            "package_ref": "test.json",
            "revision_letter": "A",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "draft",
            "options": [
                {
                    "option_id": "OPT-1",
                    "label": "100",
                    "quantity": 100,
                    "status": "active",
                    "bid_ref": "test.json",
                    "bid_summary_ref": "test.json",
                    "proposal_ref": "test.json",
                    "notes": [],
                }
            ],
            "notes": [],
            "unknown_field": "value",  # Unknown
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
