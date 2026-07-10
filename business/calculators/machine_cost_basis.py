"""Machine-hour cost-basis calculators.

Dev Order: CNC-MACHINE-COST-BASIS-1

Pure calculators that connect a governed machine profile to a machine-hour
COST rate, and that derive a bid's machine_time_cost from that rate.

These functions compute a TRUE-COST machine-hour rate (burden + electricity +
tooling). This is a cost input, NOT a customer-facing billing rate and NOT a
margin-inclusive price. Downstream bid pricing (risk factors + target margin)
is applied separately in business/bids/calculator.py.

Percentage / ratio convention:
    load_factor is a physical ratio (0.0-1.0), e.g. 0.684 means 68.4% of the
    connected load is drawn on average. It is NOT percentage points.

Electricity formula (derived from the machine profile's connected load):
    electricity_cost_per_hour = connected_load_kw * load_factor * price_per_kwh

Machine-hour rate assembly:
    machine_hour_rate = machine_burden_rate_per_hour
                        + electricity_cost_per_hour
                        + tooling_cost_per_hour

Machine time cost for a bid (opt-in):
    machine_time_cost = machine_hour_rate * (machine_minutes / 60)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MachineHourRate:
    """Breakdown of a machine-hour true-cost rate."""

    machine_burden_rate_per_hour: float
    electricity_cost_per_hour: float
    tooling_cost_per_hour: float
    machine_hour_rate: float


def derive_electricity_cost_per_hour(
    connected_load_kw: float,
    load_factor: float,
    price_per_kwh: float,
) -> float:
    """Derive electricity cost per machine-hour from connected load.

    Formula:
        electricity_cost_per_hour = connected_load_kw * load_factor * price_per_kwh

    Args:
        connected_load_kw: Total connected load in kW (from the machine profile's
            connected_load_estimate.total_kw)
        load_factor: Physical average load ratio 0.0-1.0 (NOT percentage points)
        price_per_kwh: Electricity price in currency/kWh

    Returns:
        Electricity cost per hour, rounded to 2 decimal places

    Raises:
        ValueError: If any input is out of range
    """
    if connected_load_kw < 0:
        raise ValueError("connected_load_kw must be non-negative")
    if load_factor <= 0 or load_factor > 1:
        raise ValueError("load_factor must be greater than 0 and at most 1")
    if price_per_kwh < 0:
        raise ValueError("price_per_kwh must be non-negative")

    return round(connected_load_kw * load_factor * price_per_kwh, 2)


def assemble_machine_hour_rate(
    machine_burden_rate_per_hour: float,
    electricity_cost_per_hour: float,
    tooling_cost_per_hour: float,
) -> MachineHourRate:
    """Assemble the true-cost machine-hour rate from its components.

    Formula:
        machine_hour_rate = burden + electricity + tooling

    Args:
        machine_burden_rate_per_hour: Depreciation/maintenance/insurance/overhead
            per machine-hour (owner-confirmed input)
        electricity_cost_per_hour: Electricity cost per machine-hour (typically
            derived via derive_electricity_cost_per_hour)
        tooling_cost_per_hour: Consumable tooling wear allowance per machine-hour

    Returns:
        MachineHourRate with component breakdown and assembled rate

    Raises:
        ValueError: If any component is negative
    """
    for name, value in [
        ("machine_burden_rate_per_hour", machine_burden_rate_per_hour),
        ("electricity_cost_per_hour", electricity_cost_per_hour),
        ("tooling_cost_per_hour", tooling_cost_per_hour),
    ]:
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    rate = machine_burden_rate_per_hour + electricity_cost_per_hour + tooling_cost_per_hour

    return MachineHourRate(
        machine_burden_rate_per_hour=machine_burden_rate_per_hour,
        electricity_cost_per_hour=electricity_cost_per_hour,
        tooling_cost_per_hour=tooling_cost_per_hour,
        machine_hour_rate=round(rate, 2),
    )


def derive_machine_time_cost(
    machine_hour_rate: float,
    machine_minutes: float,
) -> float:
    """Derive a bid's machine_time_cost from a machine-hour rate.

    Formula:
        machine_time_cost = machine_hour_rate * (machine_minutes / 60)

    Args:
        machine_hour_rate: True-cost machine-hour rate (currency/hour)
        machine_minutes: Machine runtime for the job, in minutes

    Returns:
        Machine time cost, rounded to 2 decimal places

    Raises:
        ValueError: If either input is negative
    """
    if machine_hour_rate < 0:
        raise ValueError("machine_hour_rate must be non-negative")
    if machine_minutes < 0:
        raise ValueError("machine_minutes must be non-negative")

    return round(machine_hour_rate * (machine_minutes / 60), 2)
