"""Tests for manufacturing readiness governance framework.

Dev Order: ECO-LOOM-MFG-READINESS-1

Tests verify:
1. Manufacturing specification schema is valid
2. Resolution evidence schema is valid
3. Eco-Loom specification artifact validates
4. Investigation checklist structure
5. Resolution governance references exist
"""

import json
from pathlib import Path

import jsonschema
import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "manufacturing"
ROOT_DIR = Path(__file__).parent.parent.parent


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestManufacturingSpecificationSchema:
    """Verify manufacturing specification schema structure."""

    @pytest.fixture
    def schema(self):
        """Load schema."""
        return load_json(SCHEMA_DIR / "manufacturing_specification_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "spec_id" in required
        assert "stock_specification" in required
        assert "toolpath_specifications" in required
        assert "authoritative_source" in required

    def test_schema_disallows_additional_properties(self, schema):
        """Schema rejects unknown fields."""
        assert schema["additionalProperties"] is False


class TestResolutionEvidenceSchema:
    """Verify resolution evidence schema structure."""

    @pytest.fixture
    def schema(self):
        """Load schema."""
        return load_json(SCHEMA_DIR / "resolution_evidence_v1.schema.json")

    def test_schema_is_valid_json_schema(self, schema):
        """Schema is valid JSON Schema draft 2020-12."""
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_fields(self, schema):
        """Schema requires expected fields."""
        required = schema["required"]
        assert "evidence_id" in required
        assert "finding_ref" in required
        assert "evidence_type" in required
        assert "status" in required
        assert "summary" in required

    def test_evidence_types_include_expected(self, schema):
        """Evidence types include expected values."""
        evidence_types = schema["properties"]["evidence_type"]["enum"]
        assert "simulation_result" in evidence_types
        assert "cam_review" in evidence_types
        assert "stock_measurement" in evidence_types
        assert "first_article_inspection" in evidence_types


class TestEcoLoomSpecificationValidates:
    """Verify Eco-Loom specification artifact validates."""

    @pytest.fixture
    def spec(self):
        """Load specification."""
        return load_json(PROJECT_DIR / "eco_loom_manufacturing_spec_v1.json")

    @pytest.fixture
    def schema(self):
        """Load schema."""
        return load_json(SCHEMA_DIR / "manufacturing_specification_v1.schema.json")

    def test_spec_validates(self, spec, schema):
        """Specification validates against schema."""
        jsonschema.validate(spec, schema)

    def test_spec_id_format(self, spec):
        """Spec ID follows expected format."""
        assert spec["spec_id"] == "MS-ECOLOOM-2026-001"

    def test_spec_status_is_pending(self, spec):
        """Specification status is pending (not resolved yet)."""
        assert spec["status"] == "pending"

    def test_stock_specification_pending(self, spec):
        """Stock specification is pending."""
        assert spec["stock_specification"]["status"] == "pending"

    def test_toolpath_specifications_exist(self, spec):
        """Toolpath specifications include contour and engrave."""
        operation_names = [t["operation_name"] for t in spec["toolpath_specifications"]]
        assert any("Contour" in name for name in operation_names)
        assert any("Engrav" in name for name in operation_names)

    def test_authoritative_source_is_cad_plus_cam(self, spec):
        """Authoritative source is CAD + CAM (not NC file alone)."""
        assert spec["authoritative_source"]["source_type"] == "cad_plus_cam"


class TestInvestigationChecklist:
    """Verify investigation checklist structure."""

    @pytest.fixture
    def checklist(self):
        """Load checklist."""
        return load_json(PROJECT_DIR / "eco_loom_investigation_checklist_v1.json")

    def test_checklist_addresses_mf001(self, checklist):
        """Checklist addresses MF-001."""
        assert "MF-001" in checklist["findings_addressed"]

    def test_checklist_addresses_ma001(self, checklist):
        """Checklist addresses MA-001."""
        assert "MA-001" in checklist["findings_addressed"]

    def test_checklist_has_investigation_steps(self, checklist):
        """Checklist has multiple investigation steps."""
        assert len(checklist["investigation_steps"]) >= 8

    def test_checklist_includes_simulation(self, checklist):
        """Checklist includes simulation steps."""
        categories = [s["category"] for s in checklist["investigation_steps"]]
        assert "simulation" in categories

    def test_checklist_includes_specification(self, checklist):
        """Checklist includes specification steps."""
        categories = [s["category"] for s in checklist["investigation_steps"]]
        assert "specification" in categories

    def test_readiness_state_machine_defined(self, checklist):
        """Readiness state machine is defined."""
        states = checklist["readiness_state_machine"]
        assert "not_ready" in states
        assert "conditional_ready" in states
        assert "ready" in states


class TestResolutionGovernanceReferences:
    """Verify resolution governance references are correct."""

    @pytest.fixture
    def findings(self):
        """Load findings."""
        return load_json(PROJECT_DIR / "eco_loom_manufacturing_findings_v1.json")

    def test_findings_has_resolution_governance(self, findings):
        """Findings document has resolution_governance field."""
        assert "resolution_governance" in findings

    def test_specification_ref_exists(self, findings):
        """Specification reference points to existing file."""
        ref = findings["resolution_governance"]["specification_ref"]
        assert (ROOT_DIR / ref).exists()

    def test_checklist_ref_exists(self, findings):
        """Checklist reference points to existing file."""
        ref = findings["resolution_governance"]["checklist_ref"]
        assert (ROOT_DIR / ref).exists()

    def test_findings_status_still_open(self, findings):
        """MF-001 status is still open (not prematurely resolved)."""
        mf_001 = next(f for f in findings["findings"] if f["finding_id"] == "MF-001")
        assert mf_001["status"] == "open"

    def test_production_readiness_still_not_ready(self, findings):
        """Production readiness is still not_ready."""
        assert findings["production_readiness"] == "not_ready"
