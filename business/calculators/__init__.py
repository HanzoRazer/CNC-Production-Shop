"""Pure calculators for CNC shop business operations.

Exports:
    - calculate_electricity_cost: Equipment electricity cost
    - calculate_loaded_labor_rate: Labor rate with payroll burden
    - calculate_machine_burden_rate: Machine hourly burden rate
    - calculate_simple_job_cost: Full job cost with target-margin pricing

Data classes:
    - MachineLoad: Equipment load input
    - MachineLoadCost: Computed load cost
    - ElectricityCostResult: Electricity calculation result
    - MachineBurdenResult: Machine burden calculation result
    - SimpleJobCostInput: Job cost input parameters
    - SimpleJobCostResult: Job cost calculation result
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

__all__ = [
    "MachineLoad",
    "MachineLoadCost",
    "ElectricityCostResult",
    "MachineBurdenResult",
    "SimpleJobCostInput",
    "SimpleJobCostResult",
    "calculate_electricity_cost",
    "calculate_loaded_labor_rate",
    "calculate_machine_burden_rate",
    "calculate_simple_job_cost",
]
