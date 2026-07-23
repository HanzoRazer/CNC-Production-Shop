"""Pure calculators for CNC shop business operations.

Exports:
    - calculate_electricity_cost: Equipment electricity cost
    - calculate_loaded_labor_rate: Labor rate with payroll burden
    - calculate_machine_burden_rate: Machine hourly burden rate
    - calculate_simple_job_cost: Full job cost with target-margin pricing
    - derive_electricity_cost_per_hour: Electricity/hour from connected load
    - assemble_machine_hour_rate: True-cost machine-hour rate assembly
    - derive_machine_time_cost: Bid machine_time_cost from a machine-hour rate

Data classes:
    - MachineLoad: Equipment load input
    - MachineLoadCost: Computed load cost
    - ElectricityCostResult: Electricity calculation result
    - MachineBurdenResult: Machine burden calculation result
    - SimpleJobCostInput: Job cost input parameters
    - SimpleJobCostResult: Job cost calculation result
    - MachineHourRate: True-cost machine-hour rate breakdown
"""

from business.calculators.cnc_electricity import (
    ElectricityCostResult,
    MachineBurdenResult,
    MachineLoad,
    MachineLoadCost,
    SimpleJobCostInput,
    SimpleJobCostResult,
    calculate_electricity_cost,
    calculate_loaded_labor_rate,
    calculate_machine_burden_rate,
    calculate_simple_job_cost,
)
from business.calculators.machine_cost_basis import (
    MONEY_DECIMALS,
    MachineHourRate,
    as_money,
    assemble_machine_hour_rate,
    derive_electricity_cost_per_hour,
    derive_machine_time_cost,
    money_equal,
)

__all__ = [
    "MachineLoad",
    "MachineLoadCost",
    "ElectricityCostResult",
    "MachineBurdenResult",
    "SimpleJobCostInput",
    "SimpleJobCostResult",
    "MachineHourRate",
    "MONEY_DECIMALS",
    "as_money",
    "calculate_electricity_cost",
    "calculate_loaded_labor_rate",
    "calculate_machine_burden_rate",
    "calculate_simple_job_cost",
    "derive_electricity_cost_per_hour",
    "assemble_machine_hour_rate",
    "derive_machine_time_cost",
    "money_equal",
]
