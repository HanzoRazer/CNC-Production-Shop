"""CNC Quote Scenario Fixtures — Realistic Shop Examples.

Dev Order: CNC-COST-CORE-2

Purpose:
    Lock realistic quote scenarios so the calculator becomes business-usable,
    not just mathematically tested.

These fixtures use real-world shop values and verify the complete calculation
chain from raw inputs to final quote price.
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
# Shop Configuration Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def texas_guitar_shop_labor():
    """Texas Guitar Exchange labor configuration."""
    return {
        "operator_wage_per_hour": 23.00,
        "payroll_burden_pct": 25.0,
    }


@pytest.fixture
def texas_guitar_shop_machine():
    """Texas Guitar Exchange CNC machine configuration.

    Based on typical small-shop CNC router:
    - $60k machine amortized over 5 years
    - 1200 billable hours/year target
    - Includes maintenance, insurance, shop overhead allocation
    """
    return {
        "annual_depreciation": 12000.00,  # $60k / 5 years
        "annual_maintenance": 3600.00,    # ~$300/month
        "annual_insurance": 1200.00,      # ~$100/month
        "annual_shop_overhead_allocation": 6000.00,  # rent/utilities allocated
        "billable_hours_per_year": 1200.0,
    }


@pytest.fixture
def texas_guitar_shop_electricity():
    """Texas Guitar Exchange CNC electricity loads.

    Typical 4x8 CNC router setup:
    - 9kW spindle at 65% average load
    - 5.5kW vacuum pump at 100% during cuts
    - 3kW dust collector at 100% during operation
    - 2kW compressor at 40% duty cycle
    """
    return {
        "loads": [
            MachineLoad("spindle", kw_rating=9.0, load_factor=0.65, hours=1.0),
            MachineLoad("vacuum_pump", kw_rating=5.5, load_factor=1.0, hours=1.0),
            MachineLoad("dust_collector", kw_rating=3.0, load_factor=1.0, hours=1.0),
            MachineLoad("compressor", kw_rating=2.0, load_factor=0.40, hours=1.0),
        ],
        "rate_per_kwh": 0.13,
    }


@pytest.fixture
def texas_guitar_shop_runtime():
    """Texas Guitar Exchange runtime costs per hour."""
    return {
        "tooling_cost_per_hour": 8.00,  # End mills, V-bits, wear
    }


# ---------------------------------------------------------------------------
# Scenario 1: Single Guitar Body Routing
# ---------------------------------------------------------------------------


class TestScenarioGuitarBodyRouting:
    """Scenario: Route one Les Paul body from mahogany blank.

    Job details:
    - Material: $85 mahogany blank (pre-thicknessed)
    - Setup/programming: $50 (existing program, fixture setup)
    - Machine runtime: 1.5 hours
    - Operator time: 2 hours (setup, monitoring, finishing)
    - Consumables: $12 (sandpaper, sealant, packaging)
    - No scrap allowance (using proven program)
    - 10% contingency
    - 35% target margin
    """

    def test_complete_quote_calculation(
        self,
        texas_guitar_shop_labor,
        texas_guitar_shop_machine,
        texas_guitar_shop_electricity,
        texas_guitar_shop_runtime,
    ):
        """Calculate complete quote for single guitar body routing."""

        # Step 1: Calculate loaded labor rate
        loaded_labor_rate = calculate_loaded_labor_rate(
            wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
            payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
        )
        assert loaded_labor_rate == 28.75

        # Step 2: Calculate machine burden rate
        machine_burden = calculate_machine_burden_rate(
            annual_depreciation=texas_guitar_shop_machine["annual_depreciation"],
            annual_maintenance=texas_guitar_shop_machine["annual_maintenance"],
            annual_insurance=texas_guitar_shop_machine["annual_insurance"],
            annual_shop_overhead_allocation=texas_guitar_shop_machine["annual_shop_overhead_allocation"],
            billable_hours_per_year=texas_guitar_shop_machine["billable_hours_per_year"],
        )
        assert machine_burden.burden_rate_per_hour == 19.0

        # Step 3: Calculate electricity cost per hour
        electricity = calculate_electricity_cost(
            loads=texas_guitar_shop_electricity["loads"],
            rate_per_kwh=texas_guitar_shop_electricity["rate_per_kwh"],
        )
        electricity_per_hour = electricity.total_cost
        assert electricity_per_hour == 1.97

        # Step 4: Calculate full job cost
        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=85.00,
                setup_programming_cost=50.00,
                machine_runtime_hours=1.5,
                operator_hours=2.0,
                operator_wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
                payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
                machine_burden_rate_per_hour=machine_burden.burden_rate_per_hour,
                electricity_cost_per_hour=electricity_per_hour,
                tooling_cost_per_hour=texas_guitar_shop_runtime["tooling_cost_per_hour"],
                consumables_cost=12.00,
                scrap_pct=0.0,
                contingency_pct=10.0,
                target_margin_pct=35.0,
            )
        )

        # Verify intermediate calculations
        assert result.loaded_labor_rate == 28.75
        assert result.labor_cost == 57.50  # 2 hours * $28.75

        # Runtime rate: machine burden + electricity + tooling
        # 19.0 + 1.97 + 8.0 = 28.97
        assert result.true_runtime_rate == 28.97

        # Runtime cost: 1.5 hours * $28.97 = $43.45
        assert result.runtime_cost == 43.45

        # Direct cost: material + setup + labor + runtime + consumables
        # 85 + 50 + 57.50 + 43.45 + 12 = 247.95
        assert result.direct_job_cost == 247.95

        # Risked cost: 247.95 * 1.0 * 1.10 = 272.75
        assert result.risked_job_cost == 272.75

        # Quote price: 272.75 / (1 - 0.35) = 419.62
        assert result.quote_price == 419.62

        # Gross profit: 419.62 - 272.75 = 146.87
        assert result.gross_profit == 146.87

        # Effective margin: 35%
        assert result.effective_margin_pct == 35.0

    def test_quote_summary_output(
        self,
        texas_guitar_shop_labor,
        texas_guitar_shop_machine,
        texas_guitar_shop_electricity,
        texas_guitar_shop_runtime,
    ):
        """Generate human-readable quote summary."""

        loaded_labor_rate = calculate_loaded_labor_rate(
            wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
            payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
        )

        machine_burden = calculate_machine_burden_rate(
            annual_depreciation=texas_guitar_shop_machine["annual_depreciation"],
            annual_maintenance=texas_guitar_shop_machine["annual_maintenance"],
            annual_insurance=texas_guitar_shop_machine["annual_insurance"],
            annual_shop_overhead_allocation=texas_guitar_shop_machine["annual_shop_overhead_allocation"],
            billable_hours_per_year=texas_guitar_shop_machine["billable_hours_per_year"],
        )

        electricity = calculate_electricity_cost(
            loads=texas_guitar_shop_electricity["loads"],
            rate_per_kwh=texas_guitar_shop_electricity["rate_per_kwh"],
        )

        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=85.00,
                setup_programming_cost=50.00,
                machine_runtime_hours=1.5,
                operator_hours=2.0,
                operator_wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
                payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
                machine_burden_rate_per_hour=machine_burden.burden_rate_per_hour,
                electricity_cost_per_hour=electricity.total_cost,
                tooling_cost_per_hour=texas_guitar_shop_runtime["tooling_cost_per_hour"],
                consumables_cost=12.00,
                scrap_pct=0.0,
                contingency_pct=10.0,
                target_margin_pct=35.0,
            )
        )

        # Build summary dict for business use
        summary = {
            "job": "Les Paul Body Routing",
            "quantity": 1,
            "rates": {
                "loaded_labor_rate": f"${loaded_labor_rate}/hr",
                "machine_burden_rate": f"${machine_burden.burden_rate_per_hour}/hr",
                "electricity_rate": f"${electricity.total_cost}/hr",
                "tooling_rate": "$8.00/hr",
                "true_runtime_rate": f"${result.true_runtime_rate}/hr",
            },
            "costs": {
                "material": f"${result.direct_job_cost - result.labor_cost - result.runtime_cost - 50 - 12:.2f}",
                "setup_programming": "$50.00",
                "labor": f"${result.labor_cost}",
                "runtime": f"${result.runtime_cost}",
                "consumables": "$12.00",
                "direct_total": f"${result.direct_job_cost}",
                "risked_total": f"${result.risked_job_cost}",
            },
            "pricing": {
                "quote_price": f"${result.quote_price}",
                "gross_profit": f"${result.gross_profit}",
                "effective_margin": f"{result.effective_margin_pct}%",
            },
        }

        # Verify summary is complete
        assert summary["pricing"]["quote_price"] == "$419.62"
        assert summary["pricing"]["effective_margin"] == "35.0%"


# ---------------------------------------------------------------------------
# Scenario 2: Batch of 10 Pickguards
# ---------------------------------------------------------------------------


class TestScenarioPickguardBatch:
    """Scenario: Cut batch of 10 custom pickguards from acrylic.

    Job details:
    - Material: $45 acrylic sheet (yields 10 pickguards)
    - Setup/programming: $75 (new program, nesting)
    - Machine runtime: 0.75 hours (fast cuts, multiple parts)
    - Operator time: 1.5 hours (setup, monitoring, deburring)
    - Consumables: $8 (polish, packaging)
    - 5% scrap allowance (acrylic can chip)
    - 10% contingency
    - 40% target margin (custom work premium)
    """

    def test_batch_quote_with_per_unit_price(
        self,
        texas_guitar_shop_labor,
        texas_guitar_shop_machine,
        texas_guitar_shop_electricity,
        texas_guitar_shop_runtime,
    ):
        """Calculate batch quote with per-unit breakdown."""

        quantity = 10

        loaded_labor_rate = calculate_loaded_labor_rate(
            wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
            payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
        )

        machine_burden = calculate_machine_burden_rate(
            annual_depreciation=texas_guitar_shop_machine["annual_depreciation"],
            annual_maintenance=texas_guitar_shop_machine["annual_maintenance"],
            annual_insurance=texas_guitar_shop_machine["annual_insurance"],
            annual_shop_overhead_allocation=texas_guitar_shop_machine["annual_shop_overhead_allocation"],
            billable_hours_per_year=texas_guitar_shop_machine["billable_hours_per_year"],
        )

        electricity = calculate_electricity_cost(
            loads=texas_guitar_shop_electricity["loads"],
            rate_per_kwh=texas_guitar_shop_electricity["rate_per_kwh"],
        )

        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=45.00,
                setup_programming_cost=75.00,
                machine_runtime_hours=0.75,
                operator_hours=1.5,
                operator_wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
                payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
                machine_burden_rate_per_hour=machine_burden.burden_rate_per_hour,
                electricity_cost_per_hour=electricity.total_cost,
                tooling_cost_per_hour=texas_guitar_shop_runtime["tooling_cost_per_hour"],
                consumables_cost=8.00,
                scrap_pct=5.0,
                contingency_pct=10.0,
                target_margin_pct=40.0,
            )
        )

        # Verify batch totals
        assert result.direct_job_cost == 192.85
        assert result.risked_job_cost == 222.74
        assert result.quote_price == 371.24
        assert result.effective_margin_pct == 40.0

        # Calculate per-unit price
        price_per_unit = round(result.quote_price / quantity, 2)
        cost_per_unit = round(result.risked_job_cost / quantity, 2)
        profit_per_unit = round(result.gross_profit / quantity, 2)

        assert price_per_unit == 37.12
        assert cost_per_unit == 22.27
        assert profit_per_unit == 14.85


# ---------------------------------------------------------------------------
# Scenario 3: Complex Multi-Operation Job
# ---------------------------------------------------------------------------


class TestScenarioFretboardSlotting:
    """Scenario: Slot and radius 5 ebony fretboards.

    Job details:
    - Material: $250 (5 ebony blanks at $50 each)
    - Setup/programming: $125 (precision setup, multiple operations)
    - Machine runtime: 3.5 hours (slotting + radiusing + inlays)
    - Operator time: 5 hours (intensive monitoring, quality checks)
    - Consumables: $35 (fret wire test pieces, finishing supplies)
    - 8% scrap allowance (ebony is unforgiving)
    - 15% contingency (precision work)
    - 45% target margin (specialty lutherie work)
    """

    def test_premium_lutherie_quote(
        self,
        texas_guitar_shop_labor,
        texas_guitar_shop_machine,
        texas_guitar_shop_electricity,
        texas_guitar_shop_runtime,
    ):
        """Calculate premium lutherie job quote."""

        quantity = 5

        loaded_labor_rate = calculate_loaded_labor_rate(
            wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
            payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
        )

        machine_burden = calculate_machine_burden_rate(
            annual_depreciation=texas_guitar_shop_machine["annual_depreciation"],
            annual_maintenance=texas_guitar_shop_machine["annual_maintenance"],
            annual_insurance=texas_guitar_shop_machine["annual_insurance"],
            annual_shop_overhead_allocation=texas_guitar_shop_machine["annual_shop_overhead_allocation"],
            billable_hours_per_year=texas_guitar_shop_machine["billable_hours_per_year"],
        )

        electricity = calculate_electricity_cost(
            loads=texas_guitar_shop_electricity["loads"],
            rate_per_kwh=texas_guitar_shop_electricity["rate_per_kwh"],
        )

        result = calculate_simple_job_cost(
            SimpleJobCostInput(
                material_cost=250.00,
                setup_programming_cost=125.00,
                machine_runtime_hours=3.5,
                operator_hours=5.0,
                operator_wage_per_hour=texas_guitar_shop_labor["operator_wage_per_hour"],
                payroll_burden_pct=texas_guitar_shop_labor["payroll_burden_pct"],
                machine_burden_rate_per_hour=machine_burden.burden_rate_per_hour,
                electricity_cost_per_hour=electricity.total_cost,
                tooling_cost_per_hour=texas_guitar_shop_runtime["tooling_cost_per_hour"],
                consumables_cost=35.00,
                scrap_pct=8.0,
                contingency_pct=15.0,
                target_margin_pct=45.0,
            )
        )

        # Verify totals
        assert result.loaded_labor_rate == 28.75
        assert result.labor_cost == 143.75  # 5 hours * $28.75
        assert result.runtime_cost == 101.39  # 3.5 hours * $28.97

        # Direct: 250 + 125 + 143.75 + 101.39 + 35 = 655.14
        assert result.direct_job_cost == 655.14

        # Risked: 655.14 * 1.08 * 1.15 = 813.69
        assert result.risked_job_cost == 813.69

        # Quote: 813.69 / 0.55 = 1479.44
        assert result.quote_price == 1479.44

        # Per-fretboard price
        price_per_unit = round(result.quote_price / quantity, 2)
        assert price_per_unit == 295.89

        # Verify margin
        assert result.effective_margin_pct == 45.0


# ---------------------------------------------------------------------------
# Scenario 4: Monthly Electricity Cost Projection
# ---------------------------------------------------------------------------


class TestScenarioMonthlyElectricity:
    """Scenario: Project monthly electricity cost for shop planning.

    Based on:
    - 100 hours/month average CNC runtime
    - Vacuum runs full time during cuts
    - Dust collector runs 80% of cut time
    - Compressor runs 40% duty cycle, 30% of cut time
    """

    def test_monthly_electricity_projection(self, texas_guitar_shop_electricity):
        """Calculate monthly electricity cost projection."""

        monthly_runtime_hours = 100

        # Scale loads to monthly hours
        monthly_loads = [
            MachineLoad("spindle", 9.0, 0.65, monthly_runtime_hours),
            MachineLoad("vacuum_pump", 5.5, 1.0, monthly_runtime_hours),
            MachineLoad("dust_collector", 3.0, 1.0, monthly_runtime_hours * 0.80),
            MachineLoad("compressor", 2.0, 0.40, monthly_runtime_hours * 0.30),
        ]

        result = calculate_electricity_cost(
            loads=monthly_loads,
            rate_per_kwh=texas_guitar_shop_electricity["rate_per_kwh"],
        )

        # Verify per-load breakdown
        assert result.loads[0].name == "spindle"
        assert result.loads[0].kwh == 585.0
        assert result.loads[0].cost == 76.05

        assert result.loads[1].name == "vacuum_pump"
        assert result.loads[1].kwh == 550.0
        assert result.loads[1].cost == 71.5

        assert result.loads[2].name == "dust_collector"
        assert result.loads[2].kwh == 240.0
        assert result.loads[2].cost == 31.2

        assert result.loads[3].name == "compressor"
        assert result.loads[3].kwh == 24.0
        assert result.loads[3].cost == 3.12

        # Verify totals
        assert result.total_kwh == 1399.0
        assert result.total_cost == 181.87

        # Cost per runtime hour
        cost_per_runtime_hour = round(result.total_cost / monthly_runtime_hours, 2)
        assert cost_per_runtime_hour == 1.82


# ---------------------------------------------------------------------------
# Scenario 5: Machine Burden Rate Comparison
# ---------------------------------------------------------------------------


class TestScenarioMachineBurdenComparison:
    """Compare machine burden rates at different utilization levels."""

    def test_burden_rate_vs_utilization(self):
        """Show how burden rate decreases with higher utilization."""

        base_costs = {
            "annual_depreciation": 12000.00,
            "annual_maintenance": 3600.00,
            "annual_insurance": 1200.00,
            "annual_shop_overhead_allocation": 6000.00,
        }

        # Low utilization: 600 hours/year (50% of target)
        low_util = calculate_machine_burden_rate(
            **base_costs,
            billable_hours_per_year=600,
        )

        # Target utilization: 1200 hours/year
        target_util = calculate_machine_burden_rate(
            **base_costs,
            billable_hours_per_year=1200,
        )

        # High utilization: 1800 hours/year (150% of target)
        high_util = calculate_machine_burden_rate(
            **base_costs,
            billable_hours_per_year=1800,
        )

        # Verify rates scale inversely with utilization
        assert low_util.burden_rate_per_hour == 38.0     # $22,800 / 600
        assert target_util.burden_rate_per_hour == 19.0  # $22,800 / 1200
        assert high_util.burden_rate_per_hour == 12.67   # $22,800 / 1800

        # Higher utilization = lower burden per job = more competitive pricing
        assert high_util.burden_rate_per_hour < target_util.burden_rate_per_hour
        assert target_util.burden_rate_per_hour < low_util.burden_rate_per_hour
