"""Tests for risk cost terminology disambiguation.

Dev Order: CNC-REPO-STABILIZATION-1

These tests verify that:
1. The additive bid-level risked cost remains additive
2. The multiplicative manufacturing adjustment remains multiplicative
3. The two formulas intentionally produce different results

See ADR-0001 for terminology definitions.
"""

from business.bids.calculator import calculate_risked_cost
from business.calculators.cnc_electricity import (
    SimpleJobCostInput,
    calculate_simple_job_cost,
)


class TestBidRiskRemainAdditive:
    """Verify the bid-level risked cost uses additive model."""

    def test_additive_formula(self):
        """Bid risked cost = base × (1 + sum_of_percentages / 100)."""
        base = 100.0
        tool_wear = 5.0
        contingency = 10.0
        overhead = 10.0
        engineering = 15.0

        result = calculate_risked_cost(
            base_cost=base,
            tool_wear_pct=tool_wear,
            manufacturing_contingency_pct=contingency,
            business_overhead_pct=overhead,
            engineering_recovery_pct=engineering,
        )

        # Additive: 100 × (1 + 40/100) = 140
        expected = 140.0
        assert result == expected

    def test_additive_with_different_base(self):
        """Verify additive formula scales linearly with base cost."""
        result = calculate_risked_cost(
            base_cost=200.0,
            tool_wear_pct=5.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=10.0,
            engineering_recovery_pct=15.0,
        )

        # Additive: 200 × (1 + 40/100) = 280
        assert result == 280.0


class TestManufacturingAdjustmentRemainMultiplicative:
    """Verify the manufacturing adjustment uses multiplicative model."""

    def test_multiplicative_formula(self):
        """Manufacturing adjustment = direct × (1+scrap) × (1+contingency)."""
        data = SimpleJobCostInput(
            material_cost=100.0,
            setup_programming_cost=0.0,
            machine_runtime_hours=0.0,
            operator_hours=0.0,
            operator_wage_per_hour=0.0,
            payroll_burden_pct=0.0,
            machine_burden_rate_per_hour=0.0,
            electricity_cost_per_hour=0.0,
            tooling_cost_per_hour=0.0,
            consumables_cost=0.0,
            scrap_pct=10.0,
            contingency_pct=10.0,
            target_margin_pct=0.0,
        )

        result = calculate_simple_job_cost(data)

        # Multiplicative: 100 × (1 + 10/100) × (1 + 10/100) = 121
        expected = 121.0
        assert result.risked_job_cost == expected


class TestFormulasIntentionallyDiffer:
    """Verify the two formulas produce different results for same percentages."""

    def test_additive_vs_multiplicative_differ(self):
        """Same percentages produce different results in each model."""
        # Additive model: 100 × (1 + 20/100) = 120
        additive_result = calculate_risked_cost(
            base_cost=100.0,
            tool_wear_pct=10.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=0.0,
            engineering_recovery_pct=0.0,
        )

        # Multiplicative model: 100 × (1 + 10/100) × (1 + 10/100) = 121
        data = SimpleJobCostInput(
            material_cost=100.0,
            setup_programming_cost=0.0,
            machine_runtime_hours=0.0,
            operator_hours=0.0,
            operator_wage_per_hour=0.0,
            payroll_burden_pct=0.0,
            machine_burden_rate_per_hour=0.0,
            electricity_cost_per_hour=0.0,
            tooling_cost_per_hour=0.0,
            consumables_cost=0.0,
            scrap_pct=10.0,
            contingency_pct=10.0,
            target_margin_pct=0.0,
        )
        multiplicative_result = calculate_simple_job_cost(data)

        # They MUST differ — this prevents accidental formula collapse
        assert additive_result != multiplicative_result.risked_job_cost
        assert additive_result == 120.0
        assert multiplicative_result.risked_job_cost == 121.0
