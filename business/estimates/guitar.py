"""Pure calculator for governed guitar build estimates.

Dev Order: GUITAR-BUILD-ESTIMATE-1

Computes internal manufacturing cost only. Does not apply margin, markup,
or customer pricing. Machine cost is derived via path-explicit
build_machine_costing.
"""

from __future__ import annotations

from pathlib import Path

from business.bids.machine_costing import build_machine_costing
from business.calculators.cnc_electricity import calculate_loaded_labor_rate
from business.calculators.machine_cost_basis import as_money, derive_machine_time_cost
from business.estimates.models import (
    EstimateCalculationMetaV1,
    EstimateProvenanceV1,
    GuitarBuildEstimateV1,
    GuitarCostSummaryV1,
    GuitarEstimateInputV1,
    LaborRateInputV1,
    ManufacturingOperationV1,
    MaterialInputV1,
    OperationCostResultV1,
    PurchasedComponentInputV1,
)

CALCULATOR_ID = "guitar_build_estimate_v1"
ROUNDING_POLICY = "currency_half_up_2dp"
DEFAULT_ESTIMATE_ID = "GUITAR-BUILD-ESTIMATE-BASELINE-V1"


def calculate_material_cost(items: tuple[MaterialInputV1, ...] | list[MaterialInputV1]) -> float:
    """Sum extended wood material costs."""
    total = 0.0
    for item in items:
        if item.quantity <= 0:
            raise ValueError(f"material {item.input_id} quantity must be > 0")
        if item.unit_cost < 0:
            raise ValueError(f"material {item.input_id} unit_cost must be >= 0")
        total += item.quantity * item.unit_cost
    return as_money(total)


def calculate_component_cost(
    items: tuple[PurchasedComponentInputV1, ...] | list[PurchasedComponentInputV1],
    category: str,
) -> float:
    """Sum extended purchased-component costs for one category."""
    total = 0.0
    for item in items:
        if item.category != category:
            continue
        if item.quantity <= 0:
            raise ValueError(f"component {item.input_id} quantity must be > 0")
        if item.unit_cost < 0:
            raise ValueError(f"component {item.input_id} unit_cost must be >= 0")
        total += item.quantity * item.unit_cost
    return as_money(total)


def calculate_labor_cost(labor_minutes: float, loaded_rate_per_hour: float) -> float:
    """Convert labor minutes to loaded labor cost."""
    if labor_minutes < 0:
        raise ValueError("labor_minutes must be >= 0")
    if loaded_rate_per_hour < 0:
        raise ValueError("loaded_rate_per_hour must be >= 0")
    return as_money((labor_minutes / 60.0) * loaded_rate_per_hour)


def operation_machine_minutes(op: ManufacturingOperationV1, quantity: int) -> float:
    """Setup + run minutes for one operation at quantity."""
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    if not op.uses_machine:
        return 0.0
    return float(op.setup_minutes + op.run_minutes_per_unit * quantity)


def operation_labor_minutes(op: ManufacturingOperationV1) -> float:
    """Explicit labor minutes only (cure/wait excluded)."""
    return float(
        op.setup_labor_minutes
        + op.attended_run_labor_minutes
        + op.manual_labor_minutes
    )


def _labor_rates_by_id(
    rates: tuple[LaborRateInputV1, ...] | list[LaborRateInputV1],
) -> dict[str, LaborRateInputV1]:
    mapping: dict[str, LaborRateInputV1] = {}
    for rate in rates:
        if rate.labor_rate_id in mapping:
            raise ValueError(f"duplicate labor_rate_id: {rate.labor_rate_id}")
        expected = calculate_loaded_labor_rate(
            rate.base_wage_per_hour, rate.payroll_burden_pct
        )
        if as_money(rate.loaded_rate_per_hour) != expected:
            raise ValueError(
                f"labor rate {rate.labor_rate_id} loaded_rate_per_hour "
                f"{rate.loaded_rate_per_hour} != derived {expected}"
            )
        mapping[rate.labor_rate_id] = rate
    return mapping


def calculate_operation_machine_cost(
    op: ManufacturingOperationV1,
    *,
    quantity: int,
    machine_hour_rate: float,
) -> tuple[float, float]:
    """Return (machine_minutes, machine_time_cost) for one operation."""
    minutes = operation_machine_minutes(op, quantity)
    if minutes == 0:
        return 0.0, 0.0
    return minutes, derive_machine_time_cost(machine_hour_rate, minutes)


def calculate_scrap_allowance(
    *,
    material_inputs: tuple[MaterialInputV1, ...] | list[MaterialInputV1],
    purchased_component_inputs: (
        tuple[PurchasedComponentInputV1, ...] | list[PurchasedComponentInputV1]
    ),
    eligible_input_ids: tuple[str, ...] | list[str],
    scrap_rate: float,
) -> float:
    """Apply scrap only to explicitly eligible input IDs."""
    if scrap_rate < 0 or scrap_rate > 1:
        raise ValueError("scrap_rate must be between 0 and 1")
    eligible = set(eligible_input_ids)
    known_ids = {i.input_id for i in material_inputs} | {
        i.input_id for i in purchased_component_inputs
    }
    missing = eligible - known_ids
    if missing:
        raise ValueError(f"scrap eligible_input_ids not found: {sorted(missing)}")

    base = 0.0
    for material in material_inputs:
        if material.input_id in eligible:
            base += material.quantity * material.unit_cost
    for component in purchased_component_inputs:
        if component.input_id in eligible:
            base += component.quantity * component.unit_cost
    return as_money(base * scrap_rate)


def _validate_unique_input_ids(estimate_input: GuitarEstimateInputV1) -> None:
    ids = [m.input_id for m in estimate_input.material_inputs] + [
        p.input_id for p in estimate_input.purchased_component_inputs
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate input_id values are not allowed")
    op_ids = [o.operation_id for o in estimate_input.operations]
    if len(op_ids) != len(set(op_ids)):
        raise ValueError("duplicate operation_id values are not allowed")


def calculate_guitar_build_estimate(
    estimate_input: GuitarEstimateInputV1,
    *,
    estimate_id: str = DEFAULT_ESTIMATE_ID,
    estimate_input_ref: str,
    effective_date: str,
    machine_profile_path: Path | None = None,
    cost_basis_path: Path | None = None,
    repo_root: Path | None = None,
) -> GuitarBuildEstimateV1:
    """Calculate a deterministic internal guitar manufacturing estimate."""
    if estimate_input.status == "approved" and estimate_input.provenance.confidence != "approved":
        raise ValueError("approved estimate status requires approved provenance confidence")
    if estimate_input.provenance.confidence == "draft" and estimate_input.status not in {
        "draft",
        "superseded",
        "retired",
    }:
        raise ValueError("draft provenance cannot produce reviewed/approved estimate status")

    _validate_unique_input_ids(estimate_input)
    rates = _labor_rates_by_id(estimate_input.labor_rate_inputs)

    profile_path = (
        Path(machine_profile_path)
        if machine_profile_path is not None
        else Path(estimate_input.machine_profile_ref)
    )
    basis_path = (
        Path(cost_basis_path)
        if cost_basis_path is not None
        else Path(estimate_input.cost_basis_ref)
    )

    # Resolve aggregate machine minutes first so machine_costing can be built.
    total_machine_minutes = 0.0
    for op in estimate_input.operations:
        total_machine_minutes += operation_machine_minutes(op, estimate_input.quantity)

    if total_machine_minutes <= 0:
        raise ValueError("estimate requires at least one machine operation with runtime")

    machine_costing = build_machine_costing(
        machine_id=estimate_input.machine_id,
        runtime_minutes=total_machine_minutes,
        machine_profile_path=profile_path,
        cost_basis_path=basis_path,
        repo_root=repo_root,
    )
    if machine_costing.cost_basis_id != estimate_input.cost_basis_id:
        raise ValueError(
            f"cost_basis_id mismatch: input={estimate_input.cost_basis_id!r} "
            f"resolved={machine_costing.cost_basis_id!r}"
        )

    rate = machine_costing.machine_hour_rate
    operation_results: list[OperationCostResultV1] = []
    direct_labor_cost = 0.0
    finishing_cost = 0.0
    inspection_and_setup_cost = 0.0

    for op in estimate_input.operations:
        if op.labor_rate_id not in rates:
            raise ValueError(f"missing labor_rate_id reference: {op.labor_rate_id}")
        labor_rate = rates[op.labor_rate_id].loaded_rate_per_hour
        machine_minutes, op_machine_cost = calculate_operation_machine_cost(
            op, quantity=estimate_input.quantity, machine_hour_rate=rate
        )
        labor_minutes = operation_labor_minutes(op)
        labor_cost = calculate_labor_cost(labor_minutes, labor_rate)

        if op.cost_category == "machine":
            # Machine dollars roll up via machine_costing aggregate; labor is separate.
            category_cost = as_money(op_machine_cost + labor_cost)
            direct_labor_cost += labor_cost
        elif op.cost_category == "direct_labor":
            category_cost = labor_cost
            direct_labor_cost += labor_cost
        elif op.cost_category == "finishing":
            # Finish labor only; finish materials are in consumables.
            category_cost = labor_cost
            finishing_cost += labor_cost
        elif op.cost_category == "inspection_and_setup":
            category_cost = labor_cost
            inspection_and_setup_cost += labor_cost
        else:
            raise ValueError(f"unsupported cost_category: {op.cost_category}")

        operation_results.append(
            OperationCostResultV1(
                operation_id=op.operation_id,
                wbs_code=op.wbs_code,
                cost_category=op.cost_category,
                machine_minutes=machine_minutes,
                labor_minutes=labor_minutes,
                cure_or_wait_minutes=float(op.cure_or_wait_minutes),
                machine_time_cost=as_money(op_machine_cost),
                labor_cost=labor_cost,
                category_cost=as_money(category_cost),
            )
        )

    wood = calculate_material_cost(estimate_input.material_inputs)
    hardware = calculate_component_cost(
        estimate_input.purchased_component_inputs, "hardware"
    )
    electronics = calculate_component_cost(
        estimate_input.purchased_component_inputs, "electronics"
    )
    consumables = calculate_component_cost(
        estimate_input.purchased_component_inputs, "consumables"
    )
    scrap = calculate_scrap_allowance(
        material_inputs=estimate_input.material_inputs,
        purchased_component_inputs=estimate_input.purchased_component_inputs,
        eligible_input_ids=estimate_input.scrap_policy.eligible_input_ids,
        scrap_rate=estimate_input.scrap_policy.scrap_rate,
    )

    # Single aggregate derivation — avoids sum-of-rounded per-op drift.
    machine_time_cost = machine_costing.derived_machine_time_cost
    direct_labor_cost = as_money(direct_labor_cost)
    finishing_cost = as_money(finishing_cost)
    inspection_and_setup_cost = as_money(inspection_and_setup_cost)

    total = as_money(
        wood
        + hardware
        + electronics
        + consumables
        + machine_time_cost
        + direct_labor_cost
        + finishing_cost
        + inspection_and_setup_cost
        + scrap
    )

    summary = GuitarCostSummaryV1(
        wood_material_cost=wood,
        hardware_cost=hardware,
        electronics_cost=electronics,
        consumables_cost=consumables,
        machine_time_cost=machine_time_cost,
        direct_labor_cost=direct_labor_cost,
        finishing_cost=finishing_cost,
        inspection_and_setup_cost=inspection_and_setup_cost,
        scrap_allowance=scrap,
        total_direct_manufacturing_cost=total,
    )

    return GuitarBuildEstimateV1(
        estimate_id=estimate_id,
        product_id=estimate_input.product_id,
        product_ref=estimate_input.product_ref,
        estimate_input_id=estimate_input.estimate_input_id,
        estimate_input_ref=estimate_input_ref,
        status=estimate_input.status,
        quantity=estimate_input.quantity,
        currency=estimate_input.currency,
        cost_summary=summary,
        operation_results=tuple(operation_results),
        machine_costing=machine_costing,
        calculation=EstimateCalculationMetaV1(
            calculator_id=CALCULATOR_ID,
            rounding_policy=ROUNDING_POLICY,
            effective_date=effective_date,
        ),
        provenance=EstimateProvenanceV1(
            source="calculated",
            confidence=estimate_input.provenance.confidence,
            note=(
                "Internal manufacturing cost only; no customer price or margin applied."
            ),
        ),
        notes=tuple(estimate_input.notes),
    )
