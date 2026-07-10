"""Tests for machine profile fixtures and schema validation.

Dev Order: CNC-MACHINE-PROFILE-BCM2030CA-1

Tests verify:
1. Schema is valid JSON Schema
2. BCM 2030CA fixture validates against schema
3. Governed spec values are recorded correctly and test-protected
4. Schema rejects unknown fields
5. Validator CLI exits 0
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "machines"
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "schemas"
    / "machines"
    / "machine_profile_v1.schema.json"
)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestMachineProfileSchema:
    """Tests for machine profile schema validity."""

    def test_schema_is_valid_json_schema(self):
        """Machine profile schema is valid JSON Schema draft 2020-12."""
        schema = load_json(SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)


class TestBcm2030caProfile:
    """Tests for the governed BCM 2030CA ATC machine profile fixture."""

    @pytest.fixture
    def fixture(self):
        """Load the BCM 2030CA profile fixture."""
        return load_json(FIXTURES_DIR / "bcm_2030ca_atc_v1.json")

    @pytest.fixture
    def schema(self):
        """Load the machine profile schema."""
        return load_json(SCHEMA_PATH)

    def test_bcm_profile_validates(self, fixture, schema):
        """BCM profile validates against the machine profile schema."""
        jsonschema.validate(fixture, schema)

    def test_machine_id(self, fixture):
        """Machine ID matches the governed identifier."""
        assert fixture["machine_id"] == "MACHINE-BCM2030CA-ATC-V1"

    def test_status_is_approved(self, fixture):
        """Status reflects the approved review state."""
        assert fixture["status"] == "approved"

    def test_vacuum_pump_count(self, fixture):
        """Vacuum pump count is 2."""
        assert fixture["vacuum_system"]["pump_count"] == 2

    def test_vacuum_pump_power_each(self, fixture):
        """Each vacuum pump is 5.5 kW."""
        assert fixture["vacuum_system"]["pump_power_kw_each"] == 5.5

    def test_total_vacuum_load(self, fixture):
        """Total vacuum load is 11.0 kW."""
        assert fixture["vacuum_system"]["total_power_kw"] == 11.0

    def test_vacuum_total_matches_count_times_each(self, fixture):
        """Total vacuum load equals pump count times power each."""
        vac = fixture["vacuum_system"]
        assert vac["total_power_kw"] == vac["pump_count"] * vac["pump_power_kw_each"]

    def test_spindle_power(self, fixture):
        """Spindle power is 9.0 kW."""
        assert fixture["spindle"]["power_kw"] == 9.0

    def test_max_rpm(self, fixture):
        """Max RPM is 24000."""
        assert fixture["spindle"]["max_rpm"] == 24000

    def test_atc_positions(self, fixture):
        """ATC has 8 positions."""
        assert fixture["atc"]["positions"] == 8

    def test_tool_holder(self, fixture):
        """Tool holder is ISO30."""
        assert fixture["spindle"]["tool_holder"] == "ISO30"

    def test_connected_load_estimate_total(self, fixture):
        """Connected load estimate total is 24.0 kW."""
        assert fixture["connected_load_estimate"]["total_kw"] == 24.0

    def test_controls_servo_flagged_as_estimate(self, fixture):
        """Controls/servo load is flagged as an engineering estimate, not nameplate."""
        components = fixture["connected_load_estimate"]["components"]
        controls = next(c for c in components if c["name"] == "controls_servo")
        assert controls["basis"] == "engineering_estimate"

    def test_connected_load_components_sum_to_total(self, fixture):
        """Component loads sum to the declared total connected load."""
        load = fixture["connected_load_estimate"]
        component_total = sum(
            c.get("total_kw", c.get("power_kw", 0)) for c in load["components"]
        )
        assert component_total == load["total_kw"]


class TestSchemaRejectsInvalidData:
    """Tests for schema validation of invalid data."""

    @pytest.fixture
    def schema(self):
        """Load the machine profile schema."""
        return load_json(SCHEMA_PATH)

    @pytest.fixture
    def valid_profile(self):
        """A minimal valid profile used as a base for negative tests."""
        return load_json(FIXTURES_DIR / "bcm_2030ca_atc_v1.json")

    def test_rejects_unknown_field(self, schema, valid_profile):
        """Unknown field is rejected by additionalProperties: false."""
        invalid = dict(valid_profile)
        invalid["secret_field"] = "should fail"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_invalid_status(self, schema, valid_profile):
        """Invalid status value is rejected."""
        invalid = dict(valid_profile)
        invalid["status"] = "governed"  # not in enum

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestValidatorCLI:
    """Tests for machine profile validator CLI."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_machine_profiles.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout
