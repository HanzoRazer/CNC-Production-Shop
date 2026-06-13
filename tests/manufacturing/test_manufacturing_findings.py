"""Tests for manufacturing findings schema and Eco-Loom findings.

Dev Order: ECO-LOOM-MFG-FINDINGS-1

Tests verify:
1. Manufacturing findings schema is valid
2. Eco-Loom findings artifact validates
3. Schema rejects invalid data
4. Findings content is correct
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "manufacturing"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestManufacturingFindingsSchema:
    """Verify manufacturing findings schema structure."""

    @pytest.fixture
    def schema(self):
        """Load schema."""
        return load_json(SCHEMA_DIR / "manufacturing_findings_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "document_id" in required
        assert "project_name" in required
        assert "findings" in required
        assert "assumptions" in required

    def test_schema_disallows_additional_properties(self, schema):
        """Schema rejects unknown fields."""
        assert schema["additionalProperties"] is False

    def test_rejects_unknown_severity(self, schema):
        """Schema rejects unknown severity."""
        invalid = {
            "document_id": "MFD-TEST-2026-001",
            "project_name": "Test",
            "customer_name": "Test",
            "created_at": "2026-06-01T12:00:00Z",
            "status": "active",
            "findings": [
                {
                    "finding_id": "MF-001",
                    "title": "Test",
                    "description": "Test",
                    "severity": "extreme",  # Invalid
                    "status": "open",
                    "required_verification": []
                }
            ],
            "assumptions": [],
            "notes": []
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestEcoLoomFindingsValidates:
    """Verify Eco-Loom findings artifact validates."""

    @pytest.fixture
    def findings(self):
        """Load Eco-Loom findings."""
        return load_json(PROJECT_DIR / "eco_loom_manufacturing_findings_v1.json")

    @pytest.fixture
    def schema(self):
        """Load schema."""
        return load_json(SCHEMA_DIR / "manufacturing_findings_v1.schema.json")

    def test_findings_validates(self, findings, schema):
        """Findings validates against schema."""
        jsonschema.validate(findings, schema)

    def test_document_id_format(self, findings):
        """Document ID follows expected format."""
        assert findings["document_id"] == "MFD-ECOLOOM-2026-001"

    def test_has_mf_001(self, findings):
        """Contains MF-001 engraving depth finding."""
        finding_ids = [f["finding_id"] for f in findings["findings"]]
        assert "MF-001" in finding_ids

    def test_has_ma_001(self, findings):
        """Contains MA-001 stock thickness assumption."""
        assumption_ids = [a["assumption_id"] for a in findings["assumptions"]]
        assert "MA-001" in assumption_ids

    def test_production_readiness_not_ready(self, findings):
        """Production readiness is not_ready."""
        assert findings["production_readiness"] == "not_ready"


class TestFindingsContent:
    """Verify findings content is correct."""

    @pytest.fixture
    def findings(self):
        """Load Eco-Loom findings."""
        return load_json(PROJECT_DIR / "eco_loom_manufacturing_findings_v1.json")

    def test_mf_001_is_open(self, findings):
        """MF-001 status is open."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert mf_001["status"] == "open"

    def test_mf_001_severity_medium(self, findings):
        """MF-001 severity is medium."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert mf_001["severity"] == "medium"

    def test_mf_001_quote_impact_none(self, findings):
        """MF-001 quote impact is none (budgetary estimate still valid)."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert mf_001["quote_impact"] == "none"

    def test_mf_001_production_readiness_impact(self, findings):
        """MF-001 affects production readiness."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert mf_001["production_readiness_impact"] is True

    def test_mf_001_has_verification_steps(self, findings):
        """MF-001 has required verification steps."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert len(mf_001["required_verification"]) >= 4

    def test_ma_001_is_open(self, findings):
        """MA-001 status is open."""
        ma_001 = next(a for a in findings["assumptions"] if a["assumption_id"] == "MA-001")
        assert ma_001["status"] == "open"

    def test_ma_001_has_stock_data(self, findings):
        """MA-001 has stock thickness observation data."""
        ma_001 = next(a for a in findings["assumptions"] if a["assumption_id"] == "MA-001")
        assert len(ma_001["data"]) >= 2


class TestValidatorCLI:
    """Verify validator CLI works correctly."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_manufacturing_findings.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "RESULT: PASS" in result.stdout
