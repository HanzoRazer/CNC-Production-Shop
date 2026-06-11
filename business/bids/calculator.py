"""Bid pricing calculator functions.

Dev Order: CNC-BID-CORE-1

This is the canonical ADDITIVE bid-level risked cost model used by BidV1.
See ADR-0001 for the distinction between this model and the multiplicative
manufacturing-adjustment model in business/calculators/cnc_electricity.py.

Percentage Convention:
    All percentage fields use PERCENTAGE POINTS (30.0 = 30%), not decimals.

Critical Invariant:
    calculate_bid_price(1000, 30.0) == 1428.57

    This is TARGET MARGIN pricing, not markup.
    quote_price = risked_cost / (1 - target_margin_pct / 100)
"""


def calculate_risked_cost(
    base_cost: float,
    tool_wear_pct: float,
    manufacturing_contingency_pct: float,
    business_overhead_pct: float,
    engineering_recovery_pct: float,
) -> float:
    """Calculate risked cost by applying additive risk factors.

    Formula:
        risked_cost = base_cost × (1 + (sum of percentages) / 100)

    Args:
        base_cost: Base manufacturing cost before risk factors
        tool_wear_pct: Tool wear allowance (percentage points)
        manufacturing_contingency_pct: Manufacturing contingency (percentage points)
        business_overhead_pct: Business overhead (percentage points)
        engineering_recovery_pct: Engineering recovery (percentage points)

    Returns:
        Risked cost with all factors applied

    Raises:
        ValueError: If base_cost is negative or any percentage is negative
    """
    if base_cost < 0:
        raise ValueError("base_cost must be non-negative")
    if tool_wear_pct < 0:
        raise ValueError("tool_wear_pct must be non-negative")
    if manufacturing_contingency_pct < 0:
        raise ValueError("manufacturing_contingency_pct must be non-negative")
    if business_overhead_pct < 0:
        raise ValueError("business_overhead_pct must be non-negative")
    if engineering_recovery_pct < 0:
        raise ValueError("engineering_recovery_pct must be non-negative")

    total_risk_pct = (
        tool_wear_pct
        + manufacturing_contingency_pct
        + business_overhead_pct
        + engineering_recovery_pct
    )

    risked = base_cost * (1 + total_risk_pct / 100)
    return round(risked, 2)


def calculate_bid_price(
    risked_cost: float,
    target_margin_pct: float,
) -> float:
    """Calculate quote price using target margin formula.

    Formula:
        quote_price = risked_cost / (1 - target_margin_pct / 100)

    This is TARGET MARGIN, not markup:
        - calculate_bid_price(1000, 30.0) == 1428.57
        - NOT 1300.00 (which would be markup)

    Args:
        risked_cost: Cost after risk factors applied
        target_margin_pct: Target gross margin (percentage points)

    Returns:
        Quote price that achieves the target margin

    Raises:
        ValueError: If risked_cost is negative
        ValueError: If target_margin_pct is negative or >= 100
    """
    if risked_cost < 0:
        raise ValueError("risked_cost must be non-negative")
    if target_margin_pct < 0:
        raise ValueError("target_margin_pct must be non-negative")
    if target_margin_pct >= 100:
        raise ValueError("target_margin_pct must be less than 100")

    quote = risked_cost / (1 - target_margin_pct / 100)
    return round(quote, 2)


def calculate_price_per_unit(
    quote_price: float,
    quantity: int,
) -> float:
    """Calculate price per unit.

    Args:
        quote_price: Total quote price
        quantity: Number of units

    Returns:
        Price per unit, rounded to 2 decimal places

    Raises:
        ValueError: If quantity is less than 1
    """
    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    return round(quote_price / quantity, 2)
