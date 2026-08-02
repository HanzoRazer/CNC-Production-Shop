"""Equipment-hour cost-basis calculators.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1

Pure calculators that connect a governed non-CNC equipment profile (vacuum
press, spray booth, cure rack) to an equipment-hour COST rate, and that derive
an operation's occupancy cost from that rate.

This mirrors business/calculators/machine_cost_basis.py deliberately: the
assembly formula, the percentage convention, and the "cost input, never a
billing rate" boundary are identical. Equipment is kept in a separate module
and a separate fixture tree so that CNC machine time and equipment occupancy
never collapse into a single number.

Percentage / ratio convention:
    load_factor is a physical ratio (0.0-1.0). It is NOT percentage points.

Electricity formula:
    electricity_cost_per_hour = connected_load_kw * load_factor * price_per_kwh

Equipment-hour rate assembly:
    equipment_hour_rate = equipment_burden_rate_per_hour
                          + electricity_cost_per_hour
                          + consumables_cost_per_hour

Occupancy cost for an operation:
    occupancy_cost = equipment_hour_rate * (occupancy_minutes / 60)

Occupancy is NOT labor. An operation may hold a press for 90 minutes while
consuming zero operator-touch minutes; both facts are recorded separately.
"""

from __future__ import annotations

from dataclasses import dataclass

from business.calculators.machine_cost_basis import as_money


@dataclass(frozen=True)
class EquipmentHourRate:
    """Breakdown of an equipment-hour true-cost rate."""

    equipment_burden_rate_per_hour: float
    electricity_cost_per_hour: float
    consumables_cost_per_hour: float
    equipment_hour_rate: float


def derive_equipment_electricity_cost_per_hour(
    connected_load_kw: float,
    load_factor: float,
    price_per_kwh: float,
) -> float:
    """Derive electricity cost per equipment-hour from connected load.

    Args:
        connected_load_kw: Total connected load in kW from the equipment profile
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

    return as_money(connected_load_kw * load_factor * price_per_kwh)


def assemble_equipment_hour_rate(
    equipment_burden_rate_per_hour: float,
    electricity_cost_per_hour: float,
    consumables_cost_per_hour: float,
) -> EquipmentHourRate:
    """Assemble the true-cost equipment-hour rate from its components.

    Formula:
        equipment_hour_rate = burden + electricity + consumables

    Args:
        equipment_burden_rate_per_hour: Depreciation/maintenance/space per
            equipment-hour
        electricity_cost_per_hour: Electricity per equipment-hour, typically
            derived via derive_equipment_electricity_cost_per_hour
        consumables_cost_per_hour: Wear-item allowance per equipment-hour
            (bag/breather/tape for a press, filters for a booth)

    Returns:
        EquipmentHourRate with component breakdown and assembled rate

    Raises:
        ValueError: If any component is negative
    """
    for name, value in [
        ("equipment_burden_rate_per_hour", equipment_burden_rate_per_hour),
        ("electricity_cost_per_hour", electricity_cost_per_hour),
        ("consumables_cost_per_hour", consumables_cost_per_hour),
    ]:
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    rate = (
        equipment_burden_rate_per_hour
        + electricity_cost_per_hour
        + consumables_cost_per_hour
    )

    return EquipmentHourRate(
        equipment_burden_rate_per_hour=equipment_burden_rate_per_hour,
        electricity_cost_per_hour=electricity_cost_per_hour,
        consumables_cost_per_hour=consumables_cost_per_hour,
        equipment_hour_rate=as_money(rate),
    )


def derive_equipment_occupancy_cost(
    equipment_hour_rate: float,
    occupancy_minutes: float,
) -> float:
    """Derive occupancy cost for one operation from an equipment-hour rate.

    Formula:
        occupancy_cost = equipment_hour_rate * (occupancy_minutes / 60)

    Args:
        equipment_hour_rate: True-cost equipment-hour rate (currency/hour)
        occupancy_minutes: Minutes the equipment is held by this operation

    Returns:
        Occupancy cost, rounded to 2 decimal places

    Raises:
        ValueError: If either input is negative
    """
    if isinstance(equipment_hour_rate, bool) or equipment_hour_rate < 0:
        raise ValueError("equipment_hour_rate must be a non-negative number")
    if isinstance(occupancy_minutes, bool) or occupancy_minutes < 0:
        raise ValueError("occupancy_minutes must be a non-negative number")

    return as_money(equipment_hour_rate * (occupancy_minutes / 60))
