"""Tests for machine cost-basis fixtures, schema, calculators, and resolver.

Dev Order: CNC-MACHINE-COST-BASIS-1

Tests verify:
1. Schema is valid JSON Schema
2. BCM 2030CA cost-basis fixture validates against schema
3. Governed derivations hold (electricity from load; rate assembly)
4. The cost basis is consistent with the referenced machine profile
5. Pure calculators compute the documented formulas
6. The resolver connects a machine_id to its machine_hour_rate
7. Schema rejects unknown/invalid fields
8. Validator CLI exits 0
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from business.calculators import (
    assemble_machine_hour_rate,
    derive_electricity_cost_per_hour,
    derive_machine_time_cost,
)
from business.machines import (
    MachineCostBasisNotFoundError,
    load_machine_cost_basis,
    machine_hour_rate_for,
)

ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = ROOT / "fixtures" / "machines" / "cost_basis"
PROFILES_DIR = ROOT / "fixtures" / "machines"
SCHEMA_PATH = ROOT / "schemas" / "machines" / "machine_cost_basis_v1.schema.json"

MACHINE_ID = "MACHINE-BCM2030CA-ATC-V1"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestMachineCostBasisSchema:
    """Tests for cost-basis schema validity."""

    def test_schema_is_valid_json_schema(self):
        """Cost-basis schema is valid JSON Schema draft 2020-12."""
        schema = load_json(SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)


class TestBcm2030caCostBasis:
    """Tests for the governed BCM 2030CA cost-basis fixture."""

    @pytest.fixture
    def fixture(self):
        """Load the BCM 2030CA cost-basis fixture."""
        return load_json(FIXTURES_DIR / "bcm_2030ca_atc_cost_basis_v1.json")

    @pytest.fixture
    def schema(self):
        """Load the cost-basis schema."""
        return load_json(SCHEMA_PATH)

    def test_fixture_validates(self, fixture, schema):
        """Cost-basis fixture validates against the schema."""
        jsonschema.validate(fixture, schema)

    def test_cost_basis_id(self, fixture):
        """Cost-basis ID matches the governed identifier."""
        assert fixture["cost_basis_id"] == "MACHINE-COST-BASIS-BCM2030CA-ATC-V1"

    def test_references_machine_profile(self, fixture):
        """Cost basis references the governed machine profile."""
        assert fixture["machine_id"] == MACHINE_ID

    def test_burden_provenance_is_inherited_default(self, fixture):
        """Machine burden ($19.0) is an inherited shop default at draft confidence.

        There is no owner-confirmation artifact for this machine's burden, so it
        must NOT be marked owner_confirmed.
        """
        assert fixture["machine_burden_rate_per_hour"] == 19.0
        prov = fixture["machine_burden_provenance"]
        assert prov["source"] == "inherited_shop_default"
        assert prov["confidence"] == "draft"

    def test_tooling_provenance_is_inherited_default(self, fixture):
        """Tooling ($8.0) is an inherited shop default at draft confidence."""
        assert fixture["tooling_cost_per_hour"] == 8.0
        prov = fixture["tooling_provenance"]
        assert prov["source"] == "inherited_shop_default"
        assert prov["confidence"] == "draft"

    def test_electricity_flagged_as_estimate(self, fixture):
        """Electricity derivation is flagged as an engineering estimate."""
        assert fixture["electricity"]["provenance"]["source"] == "engineering_estimate"

    def test_no_input_is_falsely_owner_confirmed(self, fixture):
        """No cost input claims owner_confirmed without a supporting artifact."""
        sources = {
            fixture["machine_burden_provenance"]["source"],
            fixture["tooling_provenance"]["source"],
            fixture["electricity"]["provenance"]["source"],
        }
        assert "owner_confirmed" not in sources

    def test_status_reflects_draft_inputs(self, fixture):
        """Record status is draft while its burden/tooling inputs are unconfirmed."""
        assert fixture["status"] == "draft"

    def test_electricity_derived_from_connected_load(self, fixture):
        """Electricity cost/hour equals connected_load * load_factor * price."""
        elec = fixture["electricity"]
        expected = derive_electricity_cost_per_hour(
            elec["connected_load_kw"],
            elec["load_factor"],
            elec["price_per_kwh"],
        )
        assert elec["electricity_cost_per_hour"] == expected

    def test_electricity_reproduces_shop_figure(self, fixture):
        """Documented assumptions reproduce the shop's $1.97/hr electricity figure."""
        assert fixture["electricity"]["electricity_cost_per_hour"] == 1.97

    def test_machine_hour_rate_assembled(self, fixture):
        """machine_hour_rate equals burden + electricity + tooling."""
        result = assemble_machine_hour_rate(
            fixture["machine_burden_rate_per_hour"],
            fixture["electricity"]["electricity_cost_per_hour"],
            fixture["tooling_cost_per_hour"],
        )
        assert fixture["machine_hour_rate"] == result.machine_hour_rate

    def test_machine_hour_rate_value(self, fixture):
        """True-cost machine-hour rate is $28.97/hr."""
        assert fixture["machine_hour_rate"] == 28.97

    def test_connected_load_matches_profile(self, fixture):
        """connected_load_kw mirrors the machine profile's total_kw."""
        profile = load_json(PROFILES_DIR / "bcm_2030ca_atc_v1.json")
        assert (
            fixture["electricity"]["connected_load_kw"]
            == profile["connected_load_estimate"]["total_kw"]
        )


class TestMachineCostBasisCalculators:
    """Tests for the pure cost-basis calculators."""

    def test_derive_electricity_cost_per_hour(self):
        """Electricity derivation follows kW * load_factor * price."""
        assert derive_electricity_cost_per_hour(24.0, 0.684, 0.12) == 1.97

    def test_derive_electricity_rejects_bad_load_factor(self):
        """Load factor outside (0, 1] is rejected."""
        with pytest.raises(ValueError):
            derive_electricity_cost_per_hour(24.0, 1.5, 0.12)
        with pytest.raises(ValueError):
            derive_electricity_cost_per_hour(24.0, 0.0, 0.12)

    def test_assemble_machine_hour_rate(self):
        """Rate assembly sums components."""
        result = assemble_machine_hour_rate(19.0, 1.97, 8.0)
        assert result.machine_hour_rate == 28.97

    def test_assemble_rejects_negative(self):
        """Negative components are rejected."""
        with pytest.raises(ValueError):
            assemble_machine_hour_rate(-1.0, 1.97, 8.0)

    def test_derive_machine_time_cost(self):
        """machine_time_cost = rate * minutes / 60."""
        assert derive_machine_time_cost(28.97, 120.0) == 57.94
        assert derive_machine_time_cost(28.97, 0.0) == 0.0

    def test_derive_machine_time_cost_rejects_negative(self):
        """Negative inputs are rejected."""
        with pytest.raises(ValueError):
            derive_machine_time_cost(-1.0, 120.0)
        with pytest.raises(ValueError):
            derive_machine_time_cost(28.97, -1.0)


class TestMachineCostBasisResolver:
    """Tests for the machine_id -> cost basis resolver."""

    def test_load_by_machine_id(self):
        """Resolver loads the governed cost basis by machine_id."""
        record = load_machine_cost_basis(MACHINE_ID)
        assert record["cost_basis_id"] == "MACHINE-COST-BASIS-BCM2030CA-ATC-V1"

    def test_machine_hour_rate_for(self):
        """Resolver returns the governed machine_hour_rate."""
        assert machine_hour_rate_for(MACHINE_ID) == 28.97

    def test_unknown_machine_id_raises(self):
        """Unknown machine_id raises a not-found error."""
        with pytest.raises(MachineCostBasisNotFoundError):
            load_machine_cost_basis("MACHINE-DOES-NOT-EXIST")


class TestSchemaRejectsInvalidData:
    """Tests for schema validation of invalid data."""

    @pytest.fixture
    def schema(self):
        """Load the cost-basis schema."""
        return load_json(SCHEMA_PATH)

    @pytest.fixture
    def valid(self):
        """A valid cost-basis record used as a base for negative tests."""
        return load_json(FIXTURES_DIR / "bcm_2030ca_atc_cost_basis_v1.json")

    def test_rejects_unknown_field(self, schema, valid):
        """Unknown field is rejected by additionalProperties: false."""
        invalid = dict(valid)
        invalid["secret_field"] = "should fail"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_bad_machine_id_pattern(self, schema, valid):
        """A machine_id not matching the pattern is rejected."""
        invalid = dict(valid)
        invalid["machine_id"] = "bcm-2030ca"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_rejects_load_factor_above_one(self, schema, valid):
        """A load_factor greater than 1 is rejected."""
        invalid = json.loads(json.dumps(valid))
        invalid["electricity"]["load_factor"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestValidatorCLI:
    """Tests for the cost-basis validator CLI."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_machine_cost_basis.py"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout
