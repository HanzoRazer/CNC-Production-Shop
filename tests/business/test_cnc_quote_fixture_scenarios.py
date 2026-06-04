"""Fixture-driven tests for CNC quote scenarios.

Dev Order: CNC-COST-CORE-2

These tests load JSON scenario fixtures and validate:
1. Fixtures parse as valid JSON
2. Fixtures validate against quote_scenario_v1.schema.json
3. Calculator outputs match expected outputs
4. Target-margin pricing invariant holds
5. Per-unit calculations are consistent
"""

import json
from pathlib import Path

import jsonschema
import pytest

from business.calculators import (
    SimpleJobCostInput,
    calculate_simple_job_cost,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "cnc_cost"
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "schemas" / "cnc_cost" / "quote_scenario_v1.schema.json"
)


# ---------------------------------------------------------------------------
# Fixture Loading
# ---------------------------------------------------------------------------


def load_schema():
    """Load the quote scenario JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_fixture(name: str) -> dict:
    """Load a fixture file by name."""
    path = FIXTURES_DIR / name
    with open(path) as f:
        return json.load(f)


def get_standard_fixtures() -> list[str]:
    """Return list of standard (non-sensitivity) fixture filenames."""
    return [
        "guitar_body_routing_v1.json",
        "pickguard_batch_v1.json",
        "fretboard_slotting_v1.json",
        "hardwood_panel_routing_v1.json",
    ]


# ---------------------------------------------------------------------------
# Test 1: All fixtures parse as JSON
# ---------------------------------------------------------------------------


class TestFixturesParse:
    """Verify all fixture files are valid JSON."""

    def test_standard_fixtures_parse(self):
        """Standard fixtures parse without error."""
        for name in get_standard_fixtures():
            data = load_fixture(name)
            assert "name" in data
            assert "inputs" in data
            assert "expected_outputs" in data

    def test_sensitivity_fixture_parses(self):
        """Machine burden sensitivity fixture parses without error."""
        data = load_fixture("machine_burden_sensitivity_v1.json")
        assert "scenarios" in data
        assert len(data["scenarios"]) == 2


# ---------------------------------------------------------------------------
# Test 2: All fixtures validate against schema
# ---------------------------------------------------------------------------


class TestFixturesValidateSchema:
    """Verify fixtures conform to quote_scenario_v1.schema.json."""

    @pytest.fixture
    def schema(self):
        return load_schema()

    def test_standard_fixtures_validate(self, schema):
        """Standard fixtures validate against schema."""
        for name in get_standard_fixtures():
            data = load_fixture(name)
            jsonschema.validate(data, schema)

    def test_sensitivity_scenarios_validate(self, schema):
        """Each scenario in sensitivity fixture validates against schema structure."""
        data = load_fixture("machine_burden_sensitivity_v1.json")
        for scenario in data["scenarios"]:
            # Validate inputs match schema input requirements
            inputs = scenario["inputs"]
            assert inputs["target_margin_pct"] >= 0
            assert inputs["target_margin_pct"] < 100
            assert inputs["quantity"] >= 1


# ---------------------------------------------------------------------------
# Test 3: Scenario outputs match calculator
# ---------------------------------------------------------------------------


class TestScenarioOutputsMatchCalculator:
    """Verify expected_outputs match calculate_simple_job_cost results."""

    @pytest.mark.parametrize("fixture_name", get_standard_fixtures())
    def test_standard_fixture_outputs(self, fixture_name):
        """Calculator output matches fixture expected_outputs."""
        data = load_fixture(fixture_name)
        inputs = data["inputs"]
        expected = data["expected_outputs"]
        quantity = inputs["quantity"]

        # Build SimpleJobCostInput (excludes quantity)
        job_input = SimpleJobCostInput(
            material_cost=inputs["material_cost"],
            setup_programming_cost=inputs["setup_programming_cost"],
            machine_runtime_hours=inputs["machine_runtime_hours"],
            operator_hours=inputs["operator_hours"],
            operator_wage_per_hour=inputs["operator_wage_per_hour"],
            payroll_burden_pct=inputs["payroll_burden_pct"],
            machine_burden_rate_per_hour=inputs["machine_burden_rate_per_hour"],
            electricity_cost_per_hour=inputs["electricity_cost_per_hour"],
            tooling_cost_per_hour=inputs["tooling_cost_per_hour"],
            consumables_cost=inputs["consumables_cost"],
            scrap_pct=inputs["scrap_pct"],
            contingency_pct=inputs["contingency_pct"],
            target_margin_pct=inputs["target_margin_pct"],
        )

        result = calculate_simple_job_cost(job_input)

        # Assert calculator outputs match expected
        assert result.loaded_labor_rate == pytest.approx(expected["loaded_labor_rate"], abs=0.02)
        assert result.true_runtime_rate == pytest.approx(expected["true_runtime_rate"], abs=0.02)
        assert result.labor_cost == pytest.approx(expected["labor_cost"], abs=0.02)
        assert result.runtime_cost == pytest.approx(expected["runtime_cost"], abs=0.02)
        assert result.direct_job_cost == pytest.approx(expected["direct_job_cost"], abs=0.02)
        assert result.risked_job_cost == pytest.approx(expected["risked_job_cost"], abs=0.02)
        assert result.quote_price == pytest.approx(expected["quote_price"], abs=0.02)
        assert result.gross_profit == pytest.approx(expected["gross_profit"], abs=0.02)
        assert result.effective_margin_pct == pytest.approx(
            expected["effective_margin_pct"], abs=0.01
        )

        # Assert per-unit calculations
        cost_per_unit = round(result.risked_job_cost / quantity, 2)
        price_per_unit = round(result.quote_price / quantity, 2)
        assert cost_per_unit == pytest.approx(expected["cost_per_unit"], abs=0.02)
        assert price_per_unit == pytest.approx(expected["price_per_unit"], abs=0.02)

    def test_sensitivity_fixture_outputs(self):
        """Both sensitivity scenarios match calculator."""
        data = load_fixture("machine_burden_sensitivity_v1.json")

        for scenario in data["scenarios"]:
            inputs = scenario["inputs"]
            expected = scenario["expected_outputs"]

            job_input = SimpleJobCostInput(
                material_cost=inputs["material_cost"],
                setup_programming_cost=inputs["setup_programming_cost"],
                machine_runtime_hours=inputs["machine_runtime_hours"],
                operator_hours=inputs["operator_hours"],
                operator_wage_per_hour=inputs["operator_wage_per_hour"],
                payroll_burden_pct=inputs["payroll_burden_pct"],
                machine_burden_rate_per_hour=inputs["machine_burden_rate_per_hour"],
                electricity_cost_per_hour=inputs["electricity_cost_per_hour"],
                tooling_cost_per_hour=inputs["tooling_cost_per_hour"],
                consumables_cost=inputs["consumables_cost"],
                scrap_pct=inputs["scrap_pct"],
                contingency_pct=inputs["contingency_pct"],
                target_margin_pct=inputs["target_margin_pct"],
            )

            result = calculate_simple_job_cost(job_input)

            assert result.quote_price == pytest.approx(expected["quote_price"], abs=0.02)
            assert result.true_runtime_rate == pytest.approx(
                expected["true_runtime_rate"], abs=0.02
            )


# ---------------------------------------------------------------------------
# Test 4: Target margin invariant
# ---------------------------------------------------------------------------


class TestTargetMarginInvariant:
    """Critical anti-regression: target margin is NOT markup."""

    def test_margin_not_markup(self):
        """
        cost = 1000, target_margin_pct = 30.0
        Expected: quote = 1428.57 (target margin)
        NOT: quote = 1300.00 (markup)
        """
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=1000.0,
                setup_programming_cost=0.0,
                machine_runtime_hours=0.0,
                operator_hours=0.0,
                operator_wage_per_hour=0.0,
                payroll_burden_pct=0.0,
                machine_burden_rate_per_hour=0.0,
                electricity_cost_per_hour=0.0,
                tooling_cost_per_hour=0.0,
                consumables_cost=0.0,
                scrap_pct=0.0,
                contingency_pct=0.0,
                target_margin_pct=30.0,
            )
        )

        assert result.quote_price == pytest.approx(1428.57, abs=0.01)
        assert result.quote_price != pytest.approx(1300.00, abs=0.01)
        assert result.effective_margin_pct == pytest.approx(30.0, abs=0.01)


# ---------------------------------------------------------------------------
# Test 5: Quantity / per-unit consistency
# ---------------------------------------------------------------------------


class TestQuantityConsistency:
    """Verify per-unit calculations are consistent."""

    def test_pickguard_batch_per_unit(self):
        """Batch scenario per-unit math is correct."""
        data = load_fixture("pickguard_batch_v1.json")
        inputs = data["inputs"]
        expected = data["expected_outputs"]
        quantity = inputs["quantity"]

        assert quantity == 10

        # Verify per-unit expected values
        expected_cost_per_unit = round(expected["risked_job_cost"] / quantity, 2)
        expected_price_per_unit = round(expected["quote_price"] / quantity, 2)

        assert expected["cost_per_unit"] == pytest.approx(expected_cost_per_unit, abs=0.02)
        assert expected["price_per_unit"] == pytest.approx(expected_price_per_unit, abs=0.02)

    def test_single_unit_per_unit_equals_total(self):
        """For quantity=1, per-unit equals total."""
        data = load_fixture("guitar_body_routing_v1.json")
        expected = data["expected_outputs"]

        assert data["inputs"]["quantity"] == 1
        assert expected["cost_per_unit"] == expected["risked_job_cost"]
        assert expected["price_per_unit"] == expected["quote_price"]


# ---------------------------------------------------------------------------
# Test 6: Invalid margin rejected
# ---------------------------------------------------------------------------


class TestInvalidMarginRejected:
    """Verify schema rejects invalid margin values."""

    def test_margin_100_fails_schema(self):
        """target_margin_pct = 100 should fail schema validation."""
        schema = load_schema()

        invalid_fixture = {
            "name": "invalid_margin_test",
            "description": "Should fail validation",
            "inputs": {
                "material_cost": 100.0,
                "setup_programming_cost": 0.0,
                "machine_runtime_hours": 0.0,
                "operator_hours": 0.0,
                "operator_wage_per_hour": 0.0,
                "payroll_burden_pct": 0.0,
                "machine_burden_rate_per_hour": 0.0,
                "electricity_cost_per_hour": 0.0,
                "tooling_cost_per_hour": 0.0,
                "consumables_cost": 0.0,
                "scrap_pct": 0.0,
                "contingency_pct": 0.0,
                "target_margin_pct": 100.0,
                "quantity": 1,
            },
            "expected_outputs": {
                "loaded_labor_rate": 0.0,
                "true_runtime_rate": 0.0,
                "labor_cost": 0.0,
                "runtime_cost": 0.0,
                "direct_job_cost": 100.0,
                "risked_job_cost": 100.0,
                "quote_price": 0.0,
                "gross_profit": 0.0,
                "effective_margin_pct": 0.0,
                "cost_per_unit": 100.0,
                "price_per_unit": 0.0,
            },
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_fixture, schema)


# ---------------------------------------------------------------------------
# Test 7: Machine burden sensitivity shows expected relationship
# ---------------------------------------------------------------------------


class TestMachineBurdenSensitivity:
    """Verify burden sensitivity demonstrates expected behavior."""

    def test_low_utilization_costs_more(self):
        """Low utilization should result in higher quote price."""
        data = load_fixture("machine_burden_sensitivity_v1.json")

        low_scenario = next(s for s in data["scenarios"] if s["name"] == "low_utilization")
        high_scenario = next(s for s in data["scenarios"] if s["name"] == "high_utilization")

        low_price = low_scenario["expected_outputs"]["quote_price"]
        high_price = high_scenario["expected_outputs"]["quote_price"]

        # Low utilization = higher burden = higher price
        assert low_price > high_price

        # Verify the burden rates
        assert low_scenario["inputs"]["machine_burden_rate_per_hour"] == 38.0
        assert high_scenario["inputs"]["machine_burden_rate_per_hour"] == 12.67
