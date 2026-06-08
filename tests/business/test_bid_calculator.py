"""Tests for bid pricing calculator.

Dev Order: CNC-BID-CORE-1

Percentage Convention:
    All percentage fields use PERCENTAGE POINTS (30.0 = 30%), not decimals.

Critical Anti-Regression Test:
    calculate_bid_price(1000, 30.0) == 1428.57 (target margin)
    NOT 1300.00 (markup)
"""

import pytest

from business.bids import (
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
)


class TestCalculateRiskedCost:
    """Tests for risked cost calculation."""

    def test_applies_percentages_as_percentage_points(self):
        """Percentages are percentage points, not decimals."""
        result = calculate_risked_cost(
            base_cost=1000.0,
            tool_wear_pct=5.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=10.0,
            engineering_recovery_pct=15.0,
        )
        # 1000 × (1 + 40/100) = 1400
        assert result == 1400.00

    def test_eco_loom_prototype_calculation(self):
        """Verify Eco-Loom prototype risked cost."""
        result = calculate_risked_cost(
            base_cost=315.08,
            tool_wear_pct=5.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=10.0,
            engineering_recovery_pct=15.0,
        )
        assert result == 441.11

    def test_zero_base_cost(self):
        """Zero base cost returns zero."""
        result = calculate_risked_cost(
            base_cost=0.0,
            tool_wear_pct=10.0,
            manufacturing_contingency_pct=10.0,
            business_overhead_pct=10.0,
            engineering_recovery_pct=10.0,
        )
        assert result == 0.0

    def test_zero_risk_factors(self):
        """Zero risk factors returns base cost."""
        result = calculate_risked_cost(
            base_cost=1000.0,
            tool_wear_pct=0.0,
            manufacturing_contingency_pct=0.0,
            business_overhead_pct=0.0,
            engineering_recovery_pct=0.0,
        )
        assert result == 1000.0

    def test_rejects_negative_base_cost(self):
        """Negative base cost raises error."""
        with pytest.raises(ValueError, match="base_cost must be non-negative"):
            calculate_risked_cost(
                base_cost=-100.0,
                tool_wear_pct=5.0,
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=10.0,
                engineering_recovery_pct=15.0,
            )

    def test_rejects_negative_tool_wear(self):
        """Negative tool wear raises error."""
        with pytest.raises(ValueError, match="tool_wear_pct must be non-negative"):
            calculate_risked_cost(
                base_cost=1000.0,
                tool_wear_pct=-5.0,
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=10.0,
                engineering_recovery_pct=15.0,
            )

    def test_rejects_negative_contingency(self):
        """Negative contingency raises error."""
        with pytest.raises(
            ValueError, match="manufacturing_contingency_pct must be non-negative"
        ):
            calculate_risked_cost(
                base_cost=1000.0,
                tool_wear_pct=5.0,
                manufacturing_contingency_pct=-10.0,
                business_overhead_pct=10.0,
                engineering_recovery_pct=15.0,
            )

    def test_rejects_negative_overhead(self):
        """Negative overhead raises error."""
        with pytest.raises(
            ValueError, match="business_overhead_pct must be non-negative"
        ):
            calculate_risked_cost(
                base_cost=1000.0,
                tool_wear_pct=5.0,
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=-10.0,
                engineering_recovery_pct=15.0,
            )

    def test_rejects_negative_engineering_recovery(self):
        """Negative engineering recovery raises error."""
        with pytest.raises(
            ValueError, match="engineering_recovery_pct must be non-negative"
        ):
            calculate_risked_cost(
                base_cost=1000.0,
                tool_wear_pct=5.0,
                manufacturing_contingency_pct=10.0,
                business_overhead_pct=10.0,
                engineering_recovery_pct=-15.0,
            )


class TestCalculateBidPrice:
    """Tests for bid price calculation."""

    def test_margin_invariant(self):
        """Critical: target margin formula, not markup.

        calculate_bid_price(1000, 30.0) == 1428.57
        NOT 1300.00 (which would be markup)
        """
        result = calculate_bid_price(risked_cost=1000.0, target_margin_pct=30.0)
        assert result == 1428.57

    def test_eco_loom_prototype_calculation(self):
        """Verify Eco-Loom prototype quote price."""
        result = calculate_bid_price(risked_cost=441.11, target_margin_pct=30.0)
        assert result == 630.16

    def test_zero_margin(self):
        """Zero margin returns risked cost."""
        result = calculate_bid_price(risked_cost=1000.0, target_margin_pct=0.0)
        assert result == 1000.0

    def test_high_margin(self):
        """High margin significantly increases price."""
        result = calculate_bid_price(risked_cost=1000.0, target_margin_pct=50.0)
        assert result == 2000.0

    def test_rejects_margin_100(self):
        """Margin of 100% raises error (division by zero)."""
        with pytest.raises(ValueError, match="target_margin_pct must be less than 100"):
            calculate_bid_price(risked_cost=1000.0, target_margin_pct=100.0)

    def test_rejects_margin_over_100(self):
        """Margin over 100% raises error."""
        with pytest.raises(ValueError, match="target_margin_pct must be less than 100"):
            calculate_bid_price(risked_cost=1000.0, target_margin_pct=150.0)

    def test_rejects_negative_margin(self):
        """Negative margin raises error."""
        with pytest.raises(
            ValueError, match="target_margin_pct must be non-negative"
        ):
            calculate_bid_price(risked_cost=1000.0, target_margin_pct=-10.0)

    def test_rejects_negative_risked_cost(self):
        """Negative risked cost raises error."""
        with pytest.raises(ValueError, match="risked_cost must be non-negative"):
            calculate_bid_price(risked_cost=-1000.0, target_margin_pct=30.0)


class TestCalculatePricePerUnit:
    """Tests for price per unit calculation."""

    def test_computes_correctly(self):
        """Basic price per unit calculation."""
        result = calculate_price_per_unit(quote_price=630.16, quantity=10)
        assert result == 63.02

    def test_single_unit(self):
        """Single unit returns quote price."""
        result = calculate_price_per_unit(quote_price=100.0, quantity=1)
        assert result == 100.0

    def test_rounds_to_two_decimals(self):
        """Result is rounded to 2 decimal places."""
        result = calculate_price_per_unit(quote_price=100.0, quantity=3)
        assert result == 33.33

    def test_rejects_zero_quantity(self):
        """Zero quantity raises error."""
        with pytest.raises(ValueError, match="quantity must be at least 1"):
            calculate_price_per_unit(quote_price=100.0, quantity=0)

    def test_rejects_negative_quantity(self):
        """Negative quantity raises error."""
        with pytest.raises(ValueError, match="quantity must be at least 1"):
            calculate_price_per_unit(quote_price=100.0, quantity=-5)
