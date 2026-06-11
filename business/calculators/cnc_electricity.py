"""CNC Cost Calculators — Electricity, Labor, Machine Burden, and Job Costing.

Pure calculators for CNC shop cost analysis. No CAM/toolpath imports.

Percentage Convention:
    All percentage fields use percentage POINTS, not decimals.
    - target_margin_pct = 35.0 means 35%
    - scrap_pct = 5.0 means 5%
    - payroll_burden_pct = 25.0 means 25%

    Exception: load_factor is a physical ratio (0.0–1.0)
    - load_factor = 0.65 means 65% of rated load

Electricity Formula:
    Energy_i = kW_i × LoadFactor_i × Hours_i
    Cost_i = Energy_i × RatePerKwh
    TotalKwh = Σ Energy_i
    TotalCost = TotalKwh × RatePerKwh

Job Cost Formula:
    DirectCost = Material + Setup + Labor + Runtime + Consumables
    RiskedCost = DirectCost × (1 + Scrap%/100) × (1 + Contingency%/100)
    QuotePrice = RiskedCost / (1 - TargetMargin%/100)

    NOTE (ADR-0001): This MULTIPLICATIVE model is the *manufacturing /
    job-cost adjustment* concept (canonical name: manufacturing_adjusted_cost),
    NOT the canonical commercial bid risked cost. Final customer bid pricing
    uses the ADDITIVE four-factor model in business/bids/calculator.py
    (risked_bid_cost). The field below is still named `risked_job_cost`; it will
    be renamed under the deferred quote_scenario_v2 migration (see ADR-0001).

Dev Order: CNC-COST-CORE-1
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Electricity Cost Calculator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MachineLoad:
    """A single equipment load in the CNC setup.

    Attributes:
        name: Equipment identifier (spindle, vacuum_pump, etc.)
        kw_rating: Rated power in kilowatts
        load_factor: Physical load ratio 0.0–1.0 (NOT percentage points)
        hours: Operating hours for the period
    """

    name: str
    kw_rating: float
    load_factor: float
    hours: float


@dataclass(frozen=True)
class MachineLoadCost:
    """Computed cost for a single equipment load."""

    name: str
    kw_rating: float
    load_factor: float
    hours: float
    kwh: float
    cost: float


@dataclass(frozen=True)
class ElectricityCostResult:
    """Result of electricity cost calculation."""

    rate_per_kwh: float
    total_kwh: float
    total_cost: float
    loads: list[MachineLoadCost]


def calculate_electricity_cost(
    loads: list[MachineLoad],
    rate_per_kwh: float,
) -> ElectricityCostResult:
    """Calculate electricity cost for CNC equipment loads.

    Args:
        loads: List of equipment loads (spindle, vacuum, dust collector, etc.)
        rate_per_kwh: Electricity rate in $/kWh

    Returns:
        ElectricityCostResult with per-load breakdown and totals

    Raises:
        ValueError: If inputs are invalid
    """
    if rate_per_kwh < 0:
        raise ValueError("rate_per_kwh must be non-negative")

    load_costs: list[MachineLoadCost] = []
    total_kwh = 0.0

    for load in loads:
        if load.kw_rating < 0:
            raise ValueError(f"{load.name}: kw_rating must be non-negative")
        if load.hours < 0:
            raise ValueError(f"{load.name}: hours must be non-negative")
        if load.load_factor < 0 or load.load_factor > 1:
            raise ValueError(f"{load.name}: load_factor must be between 0 and 1")

        kwh = load.kw_rating * load.load_factor * load.hours
        cost = kwh * rate_per_kwh
        total_kwh += kwh

        load_costs.append(
            MachineLoadCost(
                name=load.name,
                kw_rating=load.kw_rating,
                load_factor=load.load_factor,
                hours=load.hours,
                kwh=round(kwh, 2),
                cost=round(cost, 2),
            )
        )

    return ElectricityCostResult(
        rate_per_kwh=rate_per_kwh,
        total_kwh=round(total_kwh, 2),
        total_cost=round(total_kwh * rate_per_kwh, 2),
        loads=load_costs,
    )


# ---------------------------------------------------------------------------
# Loaded Labor Rate Calculator
# ---------------------------------------------------------------------------


def calculate_loaded_labor_rate(
    wage_per_hour: float,
    payroll_burden_pct: float,
) -> float:
    """Calculate loaded labor rate including payroll burden.

    Args:
        wage_per_hour: Base wage rate in $/hr
        payroll_burden_pct: Payroll burden in PERCENTAGE POINTS (25.0 = 25%)

    Returns:
        Loaded labor rate: wage × (1 + burden/100)

    Raises:
        ValueError: If wage or burden is negative
    """
    if wage_per_hour < 0:
        raise ValueError("wage_per_hour must be non-negative")
    if payroll_burden_pct < 0:
        raise ValueError("payroll_burden_pct must be non-negative")

    return round(wage_per_hour * (1 + payroll_burden_pct / 100), 2)


# ---------------------------------------------------------------------------
# Machine Burden Rate Calculator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MachineBurdenResult:
    """Result of machine burden rate calculation."""

    annual_depreciation: float
    annual_maintenance: float
    annual_insurance: float
    annual_shop_overhead_allocation: float
    total_annual_cost: float
    billable_hours_per_year: float
    burden_rate_per_hour: float


def calculate_machine_burden_rate(
    annual_depreciation: float,
    annual_maintenance: float,
    annual_insurance: float,
    annual_shop_overhead_allocation: float,
    billable_hours_per_year: float,
) -> MachineBurdenResult:
    """Calculate machine burden rate per hour.

    Formula:
        burden_rate = (depreciation + maintenance + insurance + overhead) / billable_hours

    Args:
        annual_depreciation: Annual depreciation or lease payment
        annual_maintenance: Annual maintenance and repair budget
        annual_insurance: Annual equipment insurance
        annual_shop_overhead_allocation: Shop overhead allocated to this machine
        billable_hours_per_year: Expected billable machine hours per year

    Returns:
        MachineBurdenResult with breakdown and hourly rate

    Raises:
        ValueError: If any cost is negative or billable hours is not positive
    """
    for name, value in [
        ("annual_depreciation", annual_depreciation),
        ("annual_maintenance", annual_maintenance),
        ("annual_insurance", annual_insurance),
        ("annual_shop_overhead_allocation", annual_shop_overhead_allocation),
    ]:
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    if billable_hours_per_year <= 0:
        raise ValueError("billable_hours_per_year must be positive")

    total_annual_cost = (
        annual_depreciation
        + annual_maintenance
        + annual_insurance
        + annual_shop_overhead_allocation
    )

    burden_rate = total_annual_cost / billable_hours_per_year

    return MachineBurdenResult(
        annual_depreciation=annual_depreciation,
        annual_maintenance=annual_maintenance,
        annual_insurance=annual_insurance,
        annual_shop_overhead_allocation=annual_shop_overhead_allocation,
        total_annual_cost=round(total_annual_cost, 2),
        billable_hours_per_year=billable_hours_per_year,
        burden_rate_per_hour=round(burden_rate, 2),
    )


# ---------------------------------------------------------------------------
# Simple Job Cost Calculator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimpleJobCostInput:
    """Input parameters for simple CNC job cost calculation.

    All percentage fields use PERCENTAGE POINTS (35.0 = 35%), not decimals.
    """

    material_cost: float
    setup_programming_cost: float
    machine_runtime_hours: float
    operator_hours: float
    operator_wage_per_hour: float
    payroll_burden_pct: float
    machine_burden_rate_per_hour: float
    electricity_cost_per_hour: float
    tooling_cost_per_hour: float
    consumables_cost: float
    scrap_pct: float
    contingency_pct: float
    target_margin_pct: float


@dataclass(frozen=True)
class SimpleJobCostResult:
    """Result of simple CNC job cost calculation."""

    loaded_labor_rate: float
    true_runtime_rate: float
    labor_cost: float
    runtime_cost: float
    direct_job_cost: float
    risked_job_cost: float
    quote_price: float
    gross_profit: float
    effective_margin_pct: float


def calculate_simple_job_cost(data: SimpleJobCostInput) -> SimpleJobCostResult:
    """Calculate simple CNC job cost with target-margin pricing.

    Uses TARGET MARGIN pricing (not markup):
        quote_price = risked_cost / (1 - target_margin_pct / 100)

    For cost=1000 at 30% margin: 1000 / (1 - 0.30) = 1428.57
    NOT markup: 1000 * 1.30 = 1300

    Args:
        data: Job cost input parameters (percentages in POINTS, not decimals)

    Returns:
        SimpleJobCostResult with cost breakdown and quote price

    Raises:
        ValueError: If inputs are invalid
    """
    for name, value in [
        ("material_cost", data.material_cost),
        ("setup_programming_cost", data.setup_programming_cost),
        ("machine_runtime_hours", data.machine_runtime_hours),
        ("operator_hours", data.operator_hours),
        ("operator_wage_per_hour", data.operator_wage_per_hour),
        ("machine_burden_rate_per_hour", data.machine_burden_rate_per_hour),
        ("electricity_cost_per_hour", data.electricity_cost_per_hour),
        ("tooling_cost_per_hour", data.tooling_cost_per_hour),
        ("consumables_cost", data.consumables_cost),
    ]:
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    if data.payroll_burden_pct < 0:
        raise ValueError("payroll_burden_pct must be non-negative")

    if data.scrap_pct < 0 or data.scrap_pct >= 100:
        raise ValueError("scrap_pct must be >= 0 and < 100")

    if data.contingency_pct < 0 or data.contingency_pct >= 100:
        raise ValueError("contingency_pct must be >= 0 and < 100")

    if data.target_margin_pct < 0 or data.target_margin_pct >= 100:
        raise ValueError("target_margin_pct must be >= 0 and < 100")

    loaded_labor_rate = calculate_loaded_labor_rate(
        data.operator_wage_per_hour,
        data.payroll_burden_pct,
    )

    labor_cost = data.operator_hours * loaded_labor_rate

    true_runtime_rate = (
        data.machine_burden_rate_per_hour
        + data.electricity_cost_per_hour
        + data.tooling_cost_per_hour
    )

    runtime_cost = data.machine_runtime_hours * true_runtime_rate

    direct_job_cost = (
        data.material_cost
        + data.setup_programming_cost
        + labor_cost
        + runtime_cost
        + data.consumables_cost
    )

    risked_job_cost = (
        direct_job_cost
        * (1 + data.scrap_pct / 100)
        * (1 + data.contingency_pct / 100)
    )

    quote_price = risked_job_cost / (1 - data.target_margin_pct / 100)
    gross_profit = quote_price - risked_job_cost
    effective_margin_pct = (gross_profit / quote_price * 100) if quote_price else 0.0

    return SimpleJobCostResult(
        loaded_labor_rate=round(loaded_labor_rate, 2),
        true_runtime_rate=round(true_runtime_rate, 2),
        labor_cost=round(labor_cost, 2),
        runtime_cost=round(runtime_cost, 2),
        direct_job_cost=round(direct_job_cost, 2),
        risked_job_cost=round(risked_job_cost, 2),
        quote_price=round(quote_price, 2),
        gross_profit=round(gross_profit, 2),
        effective_margin_pct=round(effective_margin_pct, 2),
    )
