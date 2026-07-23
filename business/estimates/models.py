"""Models for governed guitar manufacturing estimates.

Dev Order: GUITAR-BUILD-ESTIMATE-1

These records describe internal manufacturing cost only. They do not carry
customer price, markup, or margin.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from business.bids.models import MachineCostingV1


@dataclass(frozen=True)
class EstimateProvenanceV1:
    """Provenance for an estimate input or calculated estimate."""

    source: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class MaterialInputV1:
    """Wood or other material line input."""

    input_id: str
    description: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    provenance: EstimateProvenanceV1


@dataclass(frozen=True)
class PurchasedComponentInputV1:
    """Hardware, electronics, or consumables line input."""

    input_id: str
    description: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    provenance: EstimateProvenanceV1


@dataclass(frozen=True)
class LaborRateInputV1:
    """Loaded labor rate definition used by operations."""

    labor_rate_id: str
    description: str
    base_wage_per_hour: float
    payroll_burden_pct: float
    loaded_rate_per_hour: float
    provenance: EstimateProvenanceV1


@dataclass(frozen=True)
class ManufacturingOperationV1:
    """One WBS-oriented manufacturing operation."""

    operation_id: str
    wbs_code: str
    description: str
    cost_category: str
    attendance: str
    setup_minutes: float
    run_minutes_per_unit: float
    setup_labor_minutes: float
    attended_run_labor_minutes: float
    manual_labor_minutes: float
    cure_or_wait_minutes: float
    uses_machine: bool
    labor_rate_id: str
    provenance: EstimateProvenanceV1


@dataclass(frozen=True)
class ScrapPolicyV1:
    """Explicit scrap eligibility policy."""

    scrap_rate: float
    eligible_input_ids: tuple[str, ...]
    provenance: EstimateProvenanceV1


@dataclass(frozen=True)
class GuitarEstimateInputV1:
    """Complete governed estimate input record."""

    estimate_input_id: str
    product_id: str
    product_ref: str
    status: str
    quantity: int
    currency: str
    material_inputs: tuple[MaterialInputV1, ...]
    purchased_component_inputs: tuple[PurchasedComponentInputV1, ...]
    labor_rate_inputs: tuple[LaborRateInputV1, ...]
    operations: tuple[ManufacturingOperationV1, ...]
    machine_profile_ref: str
    cost_basis_ref: str
    machine_id: str
    cost_basis_id: str
    scrap_policy: ScrapPolicyV1
    provenance: EstimateProvenanceV1
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationCostResultV1:
    """Calculated result for one operation."""

    operation_id: str
    wbs_code: str
    cost_category: str
    machine_minutes: float
    labor_minutes: float
    cure_or_wait_minutes: float
    machine_time_cost: float
    labor_cost: float
    category_cost: float


@dataclass(frozen=True)
class GuitarCostSummaryV1:
    """Explicit manufacturing cost categories."""

    wood_material_cost: float
    hardware_cost: float
    electronics_cost: float
    consumables_cost: float
    machine_time_cost: float
    direct_labor_cost: float
    finishing_cost: float
    inspection_and_setup_cost: float
    scrap_allowance: float
    total_direct_manufacturing_cost: float


@dataclass(frozen=True)
class EstimateCalculationMetaV1:
    """Calculator identity and rounding policy."""

    calculator_id: str
    rounding_policy: str
    effective_date: str


@dataclass(frozen=True)
class GuitarBuildEstimateV1:
    """Calculated internal guitar manufacturing estimate."""

    estimate_id: str
    product_id: str
    product_ref: str
    estimate_input_id: str
    estimate_input_ref: str
    status: str
    quantity: int
    currency: str
    cost_summary: GuitarCostSummaryV1
    operation_results: tuple[OperationCostResultV1, ...]
    machine_costing: MachineCostingV1
    calculation: EstimateCalculationMetaV1
    provenance: EstimateProvenanceV1
    notes: tuple[str, ...] = field(default_factory=tuple)
