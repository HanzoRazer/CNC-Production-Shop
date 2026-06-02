"""Tests for CNC Cost Calculators.

Dev Order: CNC-COST-CORE-1

Percentage Convention:
    All percentage fields use PERCENTAGE POINTS (35.0 = 35%), not decimals.
    Exception: load_factor is physical ratio (0.65 = 65% load).

Critical Anti-Regression Test:
    cost = 1000, target_margin_pct = 30.0
    quote_price = 1428.57 (target margin)
    NOT 1300.00 (markup)
"""

import pytest

from business.calculators import (
    MachineLoad,
    SimpleJobCostInput,
    calculate_electricity_cost,
    calculate_loaded_labor_rate,
    calculate_machine_burden_rate,
    calculate_simple_job_cost,
)


# ---------------------------------------------------------------------------
# Electricity Cost Tests
# ---------------------------------------------------------------------------


class TestElectricitySingleLoad:
    """Tests for single equipment load calculations."""

    def test_spindle_only(self):
        """9kW spindle at 65% load for 100 hours at $0.13/kWh."""
        result = calculate_electricity_cost(
            loads=[
                MachineLoad(
                    name="spindle",
                    kw_rating=9.0,
                    load_factor=0.65,
                    hours=100,
                )
            ],
            rate_per_kwh=0.13,
        )

        assert result.total_kwh == 585.0
        assert result.total_cost == 76.05
        assert len(result.loads) == 1
        assert result.loads[0].name == "spindle"
        assert result.loads[0].kwh == 585.0
        assert result.loads[0].cost == 76.05

    def test_full_load_factor(self):
        """Equipment running at 100% load factor."""
        result = calculate_electricity_cost(
            loads=[MachineLoad("vacuum_pump", 5.5, 1.0, 100)],
            rate_per_kwh=0.13,
        )

        assert result.total_kwh == 550.0
        assert result.total_cost == 71.5

    def test_zero_hours(self):
        """Equipment with zero runtime produces zero cost."""
        result = calculate_electricity_cost(
            loads=[MachineLoad("spindle", 9.0, 0.65, 0)],
            rate_per_kwh=0.13,
        )

        assert result.total_kwh == 0.0
        assert result.total_cost == 0.0

    def test_zero_load_factor(self):
        """Equipment at zero load factor produces zero cost."""
        result = calculate_electricity_cost(
            loads=[MachineLoad("spindle", 9.0, 0.0, 100)],
            rate_per_kwh=0.13,
        )

        assert result.total_kwh == 0.0
        assert result.total_cost == 0.0


class TestElectricityMultipleLoads:
    """Tests for multiple equipment load calculations."""

    def test_typical_cnc_setup(self):
        """Full CNC router setup: spindle, vacuum, dust collector, compressor."""
        result = calculate_electricity_cost(
            loads=[
                MachineLoad("spindle", 9.0, 0.65, 100),
                MachineLoad("vacuum_pump", 5.5, 1.0, 100),
                MachineLoad("dust_collector", 3.0, 1.0, 80),
                MachineLoad("compressor", 2.0, 0.40, 30),
            ],
            rate_per_kwh=0.13,
        )

        assert result.loads[0].kwh == 585.0   # spindle: 9 * 0.65 * 100
        assert result.loads[1].kwh == 550.0   # vacuum: 5.5 * 1.0 * 100
        assert result.loads[2].kwh == 240.0   # dust: 3 * 1.0 * 80
        assert result.loads[3].kwh == 24.0    # compressor: 2 * 0.4 * 30

        assert result.total_kwh == 1399.0
        assert result.total_cost == 181.87

    def test_all_six_equipment_categories(self):
        """Test all six standard equipment categories."""
        result = calculate_electricity_cost(
            loads=[
                MachineLoad("spindle", 9.0, 0.65, 100),
                MachineLoad("vacuum_pump", 5.5, 1.0, 100),
                MachineLoad("dust_collector", 3.0, 1.0, 80),
                MachineLoad("chiller", 1.5, 0.5, 100),
                MachineLoad("compressor", 2.0, 0.40, 30),
                MachineLoad("auxiliary", 0.5, 1.0, 100),
            ],
            rate_per_kwh=0.13,
        )

        assert len(result.loads) == 6
        assert result.total_kwh > 0
        assert result.total_cost > 0

    def test_empty_loads(self):
        """Empty load list produces zero totals."""
        result = calculate_electricity_cost(loads=[], rate_per_kwh=0.13)

        assert result.total_kwh == 0.0
        assert result.total_cost == 0.0
        assert result.loads == []


class TestElectricityValidation:
    """Tests for electricity calculator input validation."""

    def test_rejects_negative_rate(self):
        with pytest.raises(ValueError, match="rate_per_kwh must be non-negative"):
            calculate_electricity_cost([], rate_per_kwh=-0.01)

    def test_rejects_negative_kw_rating(self):
        with pytest.raises(ValueError, match="spindle: kw_rating must be non-negative"):
            calculate_electricity_cost(
                [MachineLoad("spindle", -9.0, 0.65, 100)],
                rate_per_kwh=0.13,
            )

    def test_rejects_load_factor_above_one(self):
        with pytest.raises(ValueError, match="spindle: load_factor must be between 0 and 1"):
            calculate_electricity_cost(
                [MachineLoad("spindle", 9.0, 1.2, 100)],
                rate_per_kwh=0.13,
            )

    def test_rejects_negative_load_factor(self):
        with pytest.raises(ValueError, match="spindle: load_factor must be between 0 and 1"):
            calculate_electricity_cost(
                [MachineLoad("spindle", 9.0, -0.1, 100)],
                rate_per_kwh=0.13,
            )

    def test_rejects_negative_hours(self):
        with pytest.raises(ValueError, match="spindle: hours must be non-negative"):
            calculate_electricity_cost(
                [MachineLoad("spindle", 9.0, 0.65, -10)],
                rate_per_kwh=0.13,
            )


# ---------------------------------------------------------------------------
# Loaded Labor Rate Tests
# ---------------------------------------------------------------------------


class TestLoadedLaborRate:
    """Tests for loaded labor rate calculation."""

    def test_standard_burden(self):
        """$23/hr wage with 25% burden = $28.75/hr loaded rate."""
        rate = calculate_loaded_labor_rate(
            wage_per_hour=23.00,
            payroll_burden_pct=25.0,  # 25% as percentage points
        )

        assert rate == 28.75

    def test_zero_burden(self):
        """Zero burden returns base wage."""
        rate = calculate_loaded_labor_rate(
            wage_per_hour=23.00,
            payroll_burden_pct=0.0,
        )

        assert rate == 23.00

    def test_high_burden_allowed(self):
        """Burden over 100% is allowed (some jurisdictions)."""
        rate = calculate_loaded_labor_rate(
            wage_per_hour=20.00,
            payroll_burden_pct=150.0,  # 150% burden
        )

        assert rate == 50.00  # 20 * 2.5

    def test_rejects_negative_wage(self):
        with pytest.raises(ValueError, match="wage_per_hour must be non-negative"):
            calculate_loaded_labor_rate(wage_per_hour=-10, payroll_burden_pct=25.0)

    def test_rejects_negative_burden(self):
        with pytest.raises(ValueError, match="payroll_burden_pct must be non-negative"):
            calculate_loaded_labor_rate(wage_per_hour=23, payroll_burden_pct=-10.0)


# ---------------------------------------------------------------------------
# Machine Burden Rate Tests
# ---------------------------------------------------------------------------


class TestMachineBurdenRate:
    """Tests for machine burden rate calculation."""

    def test_typical_cnc_burden(self):
        """$35/hr burden from typical annual costs and 1200 billable hours."""
        result = calculate_machine_burden_rate(
            annual_depreciation=18000,
            annual_maintenance=6000,
            annual_insurance=2400,
            annual_shop_overhead_allocation=15600,
            billable_hours_per_year=1200,
        )

        # (18000 + 6000 + 2400 + 15600) / 1200 = 42000 / 1200 = 35
        assert result.total_annual_cost == 42000.0
        assert result.burden_rate_per_hour == 35.0

    def test_minimal_operation(self):
        """Low-utilization machine with minimal costs."""
        result = calculate_machine_burden_rate(
            annual_depreciation=5000,
            annual_maintenance=1000,
            annual_insurance=500,
            annual_shop_overhead_allocation=0,
            billable_hours_per_year=500,
        )

        # 6500 / 500 = 13
        assert result.burden_rate_per_hour == 13.0

    def test_rejects_negative_depreciation(self):
        with pytest.raises(ValueError, match="annual_depreciation must be non-negative"):
            calculate_machine_burden_rate(
                annual_depreciation=-1000,
                annual_maintenance=0,
                annual_insurance=0,
                annual_shop_overhead_allocation=0,
                billable_hours_per_year=1000,
            )

    def test_rejects_zero_billable_hours(self):
        with pytest.raises(ValueError, match="billable_hours_per_year must be positive"):
            calculate_machine_burden_rate(
                annual_depreciation=10000,
                annual_maintenance=0,
                annual_insurance=0,
                annual_shop_overhead_allocation=0,
                billable_hours_per_year=0,
            )

    def test_rejects_negative_billable_hours(self):
        with pytest.raises(ValueError, match="billable_hours_per_year must be positive"):
            calculate_machine_burden_rate(
                annual_depreciation=10000,
                annual_maintenance=0,
                annual_insurance=0,
                annual_shop_overhead_allocation=0,
                billable_hours_per_year=-100,
            )


# ---------------------------------------------------------------------------
# Simple Job Cost Tests
# ---------------------------------------------------------------------------


class TestSimpleJobCost:
    """Tests for simple job cost calculation."""

    def test_example_job(self):
        """Test case from handoff: $400 material, 4hr runtime, 35% margin."""
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=400,
                setup_programming_cost=150,
                machine_runtime_hours=4,
                operator_hours=4,
                operator_wage_per_hour=23,
                payroll_burden_pct=25.0,
                machine_burden_rate_per_hour=35,
                electricity_cost_per_hour=2,
                tooling_cost_per_hour=8,
                consumables_cost=30,
                scrap_pct=0.0,
                contingency_pct=10.0,
                target_margin_pct=35.0,
            )
        )

        assert result.loaded_labor_rate == 28.75
        assert result.labor_cost == 115.00
        assert result.true_runtime_rate == 45.00
        assert result.runtime_cost == 180.00
        assert result.direct_job_cost == 875.00
        assert result.risked_job_cost == 962.50
        assert result.quote_price == 1480.77
        assert result.effective_margin_pct == 35.0

    def test_zero_margin(self):
        """Zero margin returns cost as quote price."""
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=100,
                setup_programming_cost=0,
                machine_runtime_hours=1,
                operator_hours=1,
                operator_wage_per_hour=20,
                payroll_burden_pct=0.0,
                machine_burden_rate_per_hour=10,
                electricity_cost_per_hour=2,
                tooling_cost_per_hour=3,
                consumables_cost=0,
                scrap_pct=0.0,
                contingency_pct=0.0,
                target_margin_pct=0.0,
            )
        )

        assert result.direct_job_cost == 135.00  # 100 + 20 + 15
        assert result.risked_job_cost == 135.00
        assert result.quote_price == 135.00
        assert result.gross_profit == 0.0

    def test_with_scrap_and_contingency(self):
        """Scrap and contingency compound on direct cost."""
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=1000,
                setup_programming_cost=0,
                machine_runtime_hours=0,
                operator_hours=0,
                operator_wage_per_hour=0,
                payroll_burden_pct=0.0,
                machine_burden_rate_per_hour=0,
                electricity_cost_per_hour=0,
                tooling_cost_per_hour=0,
                consumables_cost=0,
                scrap_pct=5.0,
                contingency_pct=10.0,
                target_margin_pct=0.0,
            )
        )

        # 1000 * 1.05 * 1.10 = 1155
        assert result.direct_job_cost == 1000.00
        assert result.risked_job_cost == 1155.00


# ---------------------------------------------------------------------------
# CRITICAL: Target Margin vs Markup Anti-Regression Test
# ---------------------------------------------------------------------------


class TestTargetMarginNotMarkup:
    """CRITICAL: Verify target margin pricing, NOT markup.

    This test exists because the consultant identified a markup/margin
    inconsistency in other repo modules. This calculator MUST use
    target margin pricing.
    """

    def test_margin_formula_not_markup(self):
        """
        For cost=1000 and target_margin_pct=30.0:
            Markup would give: 1000 * 1.30 = 1300 (WRONG)
            Target margin gives: 1000 / (1 - 0.30) = 1428.57 (CORRECT)
        """
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=1000,
                setup_programming_cost=0,
                machine_runtime_hours=0,
                operator_hours=0,
                operator_wage_per_hour=0,
                payroll_burden_pct=0.0,
                machine_burden_rate_per_hour=0,
                electricity_cost_per_hour=0,
                tooling_cost_per_hour=0,
                consumables_cost=0,
                scrap_pct=0.0,
                contingency_pct=0.0,
                target_margin_pct=30.0,
            )
        )

        # Target margin formula: price = cost / (1 - margin/100)
        # 1000 / 0.70 = 1428.57
        assert result.quote_price == 1428.57

        # NOT markup: 1000 * 1.30 = 1300
        assert result.quote_price != 1300.00

        # Verify effective margin is actually 30%
        assert result.effective_margin_pct == 30.0

    def test_margin_50_percent(self):
        """50% margin doubles the quote price."""
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=1000,
                setup_programming_cost=0,
                machine_runtime_hours=0,
                operator_hours=0,
                operator_wage_per_hour=0,
                payroll_burden_pct=0.0,
                machine_burden_rate_per_hour=0,
                electricity_cost_per_hour=0,
                tooling_cost_per_hour=0,
                consumables_cost=0,
                scrap_pct=0.0,
                contingency_pct=0.0,
                target_margin_pct=50.0,
            )
        )

        # 1000 / (1 - 0.50) = 1000 / 0.50 = 2000
        assert result.quote_price == 2000.00
        assert result.effective_margin_pct == 50.0


# ---------------------------------------------------------------------------
# Job Cost Validation Tests
# ---------------------------------------------------------------------------


class TestJobCostValidation:
    """Tests for job cost input validation."""

    def test_rejects_negative_material(self):
        with pytest.raises(ValueError, match="material_cost must be non-negative"):
            calculate_simple_job_cost(
                SimpleJobCostInput(
                    material_cost=-100,
                    setup_programming_cost=0,
                    machine_runtime_hours=0,
                    operator_hours=0,
                    operator_wage_per_hour=0,
                    payroll_burden_pct=0,
                    machine_burden_rate_per_hour=0,
                    electricity_cost_per_hour=0,
                    tooling_cost_per_hour=0,
                    consumables_cost=0,
                    scrap_pct=0,
                    contingency_pct=0,
                    target_margin_pct=0,
                )
            )

    def test_rejects_margin_at_100_percent(self):
        """100% margin is invalid (division by zero)."""
        with pytest.raises(ValueError, match="target_margin_pct must be >= 0 and < 100"):
            calculate_simple_job_cost(
                SimpleJobCostInput(
                    material_cost=100,
                    setup_programming_cost=0,
                    machine_runtime_hours=0,
                    operator_hours=0,
                    operator_wage_per_hour=0,
                    payroll_burden_pct=0,
                    machine_burden_rate_per_hour=0,
                    electricity_cost_per_hour=0,
                    tooling_cost_per_hour=0,
                    consumables_cost=0,
                    scrap_pct=0,
                    contingency_pct=0,
                    target_margin_pct=100.0,
                )
            )

    def test_rejects_margin_over_100_percent(self):
        """Margin over 100% is invalid."""
        with pytest.raises(ValueError, match="target_margin_pct must be >= 0 and < 100"):
            calculate_simple_job_cost(
                SimpleJobCostInput(
                    material_cost=100,
                    setup_programming_cost=0,
                    machine_runtime_hours=0,
                    operator_hours=0,
                    operator_wage_per_hour=0,
                    payroll_burden_pct=0,
                    machine_burden_rate_per_hour=0,
                    electricity_cost_per_hour=0,
                    tooling_cost_per_hour=0,
                    consumables_cost=0,
                    scrap_pct=0,
                    contingency_pct=0,
                    target_margin_pct=150.0,
                )
            )

    def test_rejects_negative_scrap(self):
        with pytest.raises(ValueError, match="scrap_pct must be >= 0 and < 100"):
            calculate_simple_job_cost(
                SimpleJobCostInput(
                    material_cost=100,
                    setup_programming_cost=0,
                    machine_runtime_hours=0,
                    operator_hours=0,
                    operator_wage_per_hour=0,
                    payroll_burden_pct=0,
                    machine_burden_rate_per_hour=0,
                    electricity_cost_per_hour=0,
                    tooling_cost_per_hour=0,
                    consumables_cost=0,
                    scrap_pct=-5.0,
                    contingency_pct=0,
                    target_margin_pct=0,
                )
            )

    def test_rejects_scrap_at_100_percent(self):
        with pytest.raises(ValueError, match="scrap_pct must be >= 0 and < 100"):
            calculate_simple_job_cost(
                SimpleJobCostInput(
                    material_cost=100,
                    setup_programming_cost=0,
                    machine_runtime_hours=0,
                    operator_hours=0,
                    operator_wage_per_hour=0,
                    payroll_burden_pct=0,
                    machine_burden_rate_per_hour=0,
                    electricity_cost_per_hour=0,
                    tooling_cost_per_hour=0,
                    consumables_cost=0,
                    scrap_pct=100.0,
                    contingency_pct=0,
                    target_margin_pct=0,
                )
            )


# ---------------------------------------------------------------------------
# Result Structure Tests
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Tests for result data structure integrity."""

    def test_electricity_result_contains_rate(self):
        result = calculate_electricity_cost(
            loads=[MachineLoad("spindle", 9.0, 0.65, 100)],
            rate_per_kwh=0.13,
        )

        assert result.rate_per_kwh == 0.13

    def test_load_cost_preserves_inputs(self):
        result = calculate_electricity_cost(
            loads=[MachineLoad("spindle", 9.0, 0.65, 100)],
            rate_per_kwh=0.13,
        )

        load = result.loads[0]
        assert load.name == "spindle"
        assert load.kw_rating == 9.0
        assert load.load_factor == 0.65
        assert load.hours == 100

    def test_dataclasses_are_frozen(self):
        result = calculate_electricity_cost(
            loads=[MachineLoad("spindle", 9.0, 0.65, 100)],
            rate_per_kwh=0.13,
        )

        with pytest.raises(AttributeError):
            result.total_cost = 999.99  # type: ignore

    def test_machine_burden_result_preserves_inputs(self):
        result = calculate_machine_burden_rate(
            annual_depreciation=18000,
            annual_maintenance=6000,
            annual_insurance=2400,
            annual_shop_overhead_allocation=15600,
            billable_hours_per_year=1200,
        )

        assert result.annual_depreciation == 18000
        assert result.annual_maintenance == 6000
        assert result.annual_insurance == 2400
        assert result.annual_shop_overhead_allocation == 15600
        assert result.billable_hours_per_year == 1200
