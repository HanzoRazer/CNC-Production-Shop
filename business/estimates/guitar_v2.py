"""Pure calculator for governed thin-skin guitar build estimates.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1

Computes internal direct manufacturing cost only. Applies no overhead, margin,
markup, warranty reserve, fulfillment cost, or customer price. CNC machine cost
is derived via path-explicit build_machine_costing; non-CNC equipment occupancy
is derived via path-explicit build_equipment_occupancy_costing.

Rounding policy
---------------
Labor is summed from per-operation rounded costs, so every operation line in
the estimate is a real auditable number that adds up to its category.

Machine time and equipment occupancy are derived once from aggregate minutes,
because rounding each operation's share independently and then summing them
drifts against the governed hour rate. The per-operation machine and equipment
figures in operation_results are therefore informational allocations: they may
differ from the aggregate by a cent or two and must not be re-summed to form a
total. This matches the V1 calculator's treatment of machine cost.
"""

from __future__ import annotations

from pathlib import Path

from business.bids.machine_costing import build_machine_costing
from business.calculators.cnc_electricity import calculate_loaded_labor_rate
from business.calculators.equipment_cost_basis import derive_equipment_occupancy_cost
from business.calculators.machine_cost_basis import as_money, derive_machine_time_cost
from business.estimates.equipment_costing import build_equipment_occupancy_costing
from business.estimates.models_v2 import (
    LABOR_CATEGORIES,
    MATERIAL_CATEGORIES,
    EquipmentOccupancyCostingV1,
    EquipmentRefV2,
    EstimateCalculationMetaV2,
    EstimateProvenanceV2,
    LaborRateInputV2,
    ManufacturingOperationV2,
    MaterialInputV2,
    OperationCostResultV2,
    ProcessYieldReservePolicyV2,
    PurchasedComponentInputV2,
    RiskBasisDetailV2,
    ThinSkinBuildEstimateV2,
    ThinSkinCostSummaryV2,
    ThinSkinEstimateInputV2,
    ThinSkinTimeSummaryV2,
)

CALCULATOR_ID = "thin_skin_build_estimate_v2"
ROUNDING_POLICY = "currency_half_up_2dp"
DEFAULT_ESTIMATE_ID = "THIN-SKIN-GUITAR-BUILD-ESTIMATE-BASELINE-V1"
NO_COMPOUNDING = (
    "material_scrap_allowance is excluded from the process reserve base; "
    "the two risk mechanisms do not compound"
)

# Maps an input category to the cost-summary field it rolls up to.
_CATEGORY_TO_SUMMARY_FIELD: dict[str, str] = {
    "core_material": "core_material_cost",
    "skin_material": "skin_material_cost",
    "adhesive_lamination": "adhesive_and_lamination_consumables",
    "neck_fretboard": "neck_and_fretboard_cost",
    "hardware": "hardware_cost",
    "electronics": "electronics_cost",
    "finish_material": "finish_material_cost",
    "other_consumables": "other_consumables_cost",
}

_LABOR_CATEGORY_TO_SUMMARY_FIELD: dict[str, str] = {
    "lamination_labor": "lamination_labor_cost",
    "direct_build_labor": "direct_build_labor_cost",
    "finishing_labor": "finishing_labor_cost",
    "assembly_labor": "assembly_labor_cost",
    "setup_and_inspection": "setup_and_inspection_cost",
}


def _extended_cost(quantity: float, unit_cost: float, input_id: str) -> float:
    """Validate and extend one input line."""
    if quantity <= 0:
        raise ValueError(f"input {input_id} quantity must be > 0")
    if unit_cost < 0:
        raise ValueError(f"input {input_id} unit_cost must be >= 0")
    return quantity * unit_cost


def calculate_category_cost(
    material_inputs: tuple[MaterialInputV2, ...] | list[MaterialInputV2],
    purchased_component_inputs: (
        tuple[PurchasedComponentInputV2, ...] | list[PurchasedComponentInputV2]
    ),
    category: str,
) -> float:
    """Sum extended costs for one category across both input lists.

    Category placement is independent of which list an input lives in, so a
    purchased truss rod and a maple neck blank both land on
    neck_and_fretboard_cost without forcing either into the wrong list.
    """
    if category not in MATERIAL_CATEGORIES:
        raise ValueError(f"unsupported input category: {category}")
    total = 0.0
    for item in material_inputs:
        if item.category == category:
            total += _extended_cost(item.quantity, item.unit_cost, item.input_id)
    for component in purchased_component_inputs:
        if component.category == category:
            total += _extended_cost(
                component.quantity, component.unit_cost, component.input_id
            )
    return as_money(total)


def calculate_labor_cost(labor_minutes: float, loaded_rate_per_hour: float) -> float:
    """Convert operator-present minutes to loaded labor cost."""
    if labor_minutes < 0:
        raise ValueError("labor_minutes must be >= 0")
    if loaded_rate_per_hour < 0:
        raise ValueError("loaded_rate_per_hour must be >= 0")
    return as_money((labor_minutes / 60.0) * loaded_rate_per_hour)


def operation_machine_minutes(op: ManufacturingOperationV2, quantity: int) -> float:
    """CNC minutes for one operation at quantity.

    Setup is already carried inside machine_runtime_minutes for machine
    operations, because the spindle-side record is occupancy of the machine,
    not just cutting time. Setup labor is counted separately and in full.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    if not op.uses_machine:
        return 0.0
    return float(op.time_model.machine_runtime_minutes * quantity)


def operation_occupancy_minutes(op: ManufacturingOperationV2, quantity: int) -> float:
    """Non-CNC equipment minutes for one operation at quantity."""
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    if not op.equipment_id:
        return 0.0
    return float(op.time_model.equipment_occupancy_minutes * quantity)


def _labor_rates_by_id(
    rates: tuple[LaborRateInputV2, ...] | list[LaborRateInputV2],
) -> dict[str, LaborRateInputV2]:
    mapping: dict[str, LaborRateInputV2] = {}
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


def _validate_structure(estimate_input: ThinSkinEstimateInputV2) -> None:
    """Reject duplicate IDs, unknown categories, and dangling references."""
    ids = [m.input_id for m in estimate_input.material_inputs] + [
        p.input_id for p in estimate_input.purchased_component_inputs
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate input_id values are not allowed")

    for item in estimate_input.material_inputs:
        if item.category not in MATERIAL_CATEGORIES:
            raise ValueError(
                f"material {item.input_id} has unsupported category: {item.category}"
            )
    for component in estimate_input.purchased_component_inputs:
        if component.category not in MATERIAL_CATEGORIES:
            raise ValueError(
                f"component {component.input_id} has unsupported category: "
                f"{component.category}"
            )

    op_ids = [o.operation_id for o in estimate_input.operations]
    if len(op_ids) != len(set(op_ids)):
        raise ValueError("duplicate operation_id values are not allowed")
    wbs_codes = [o.wbs_code for o in estimate_input.operations]
    if len(wbs_codes) != len(set(wbs_codes)):
        raise ValueError("duplicate wbs_code values are not allowed")

    declared_equipment = {ref.equipment_id for ref in estimate_input.equipment_refs}
    if len(declared_equipment) != len(estimate_input.equipment_refs):
        raise ValueError("duplicate equipment_id in equipment_refs")

    for op in estimate_input.operations:
        if op.labor_category not in LABOR_CATEGORIES:
            raise ValueError(
                f"operation {op.operation_id} has unsupported labor_category: "
                f"{op.labor_category}"
            )
        if op.equipment_id and op.equipment_id not in declared_equipment:
            raise ValueError(
                f"operation {op.operation_id} references undeclared equipment_id: "
                f"{op.equipment_id}"
            )
        if op.time_model.equipment_occupancy_minutes > 0 and not op.equipment_id:
            raise ValueError(
                f"operation {op.operation_id} books equipment occupancy without "
                f"an equipment_id"
            )
        if op.time_model.machine_runtime_minutes > 0 and not op.uses_machine:
            raise ValueError(
                f"operation {op.operation_id} books machine runtime without "
                f"uses_machine"
            )


def calculate_material_scrap_allowance(
    *,
    material_inputs: tuple[MaterialInputV2, ...] | list[MaterialInputV2],
    purchased_component_inputs: (
        tuple[PurchasedComponentInputV2, ...] | list[PurchasedComponentInputV2]
    ),
    eligible_input_ids: tuple[str, ...] | list[str],
    scrap_rate: float,
) -> tuple[float, float]:
    """Apply scrap only to explicitly eligible input IDs.

    Returns (base, allowance).
    """
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
    return as_money(base), as_money(base * scrap_rate)


def _reserve_material_base(
    estimate_input: ThinSkinEstimateInputV2,
    policy: ProcessYieldReservePolicyV2,
) -> float:
    eligible = set(policy.eligible_input_ids)
    known_ids = {i.input_id for i in estimate_input.material_inputs} | {
        i.input_id for i in estimate_input.purchased_component_inputs
    }
    missing = eligible - known_ids
    if missing:
        raise ValueError(f"reserve eligible_input_ids not found: {sorted(missing)}")
    base = 0.0
    for material in estimate_input.material_inputs:
        if material.input_id in eligible:
            base += material.quantity * material.unit_cost
    for component in estimate_input.purchased_component_inputs:
        if component.input_id in eligible:
            base += component.quantity * component.unit_cost
    return as_money(base)


def _build_equipment_costing(
    estimate_input: ThinSkinEstimateInputV2,
    occupancy_by_equipment: dict[str, float],
    repo_root: Path | None,
) -> tuple[EquipmentOccupancyCostingV1, ...]:
    """Build one occupancy record per declared equipment reference."""
    records: list[EquipmentOccupancyCostingV1] = []
    for ref in estimate_input.equipment_refs:
        record = build_equipment_occupancy_costing(
            equipment_id=ref.equipment_id,
            occupancy_minutes=occupancy_by_equipment.get(ref.equipment_id, 0.0),
            equipment_profile_path=Path(ref.equipment_profile_ref),
            cost_basis_path=Path(ref.cost_basis_ref),
            repo_root=repo_root,
        )
        if record.cost_basis_id != ref.cost_basis_id:
            raise ValueError(
                f"equipment cost_basis_id mismatch for {ref.equipment_id}: "
                f"input={ref.cost_basis_id!r} resolved={record.cost_basis_id!r}"
            )
        records.append(record)
    return tuple(records)


def _equipment_rates(
    records: tuple[EquipmentOccupancyCostingV1, ...],
) -> dict[str, float]:
    return {r.equipment_id: r.equipment_hour_rate for r in records}


def _validate_status_gating(estimate_input: ThinSkinEstimateInputV2) -> None:
    if (
        estimate_input.status == "approved"
        and estimate_input.provenance.confidence != "approved"
    ):
        raise ValueError("approved estimate status requires approved provenance confidence")
    if estimate_input.provenance.confidence == "draft" and estimate_input.status not in {
        "draft",
        "superseded",
        "retired",
    }:
        raise ValueError("draft provenance cannot produce reviewed/approved estimate status")


def calculate_thin_skin_build_estimate(
    estimate_input: ThinSkinEstimateInputV2,
    *,
    estimate_id: str = DEFAULT_ESTIMATE_ID,
    estimate_input_ref: str,
    effective_date: str,
    machine_profile_path: Path | None = None,
    cost_basis_path: Path | None = None,
    repo_root: Path | None = None,
) -> ThinSkinBuildEstimateV2:
    """Calculate a deterministic internal thin-skin manufacturing estimate."""
    _validate_status_gating(estimate_input)
    _validate_structure(estimate_input)
    rates = _labor_rates_by_id(estimate_input.labor_rate_inputs)

    quantity = estimate_input.quantity
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

    # Aggregate minutes first so machine and equipment costings can be built
    # once against the governed hour rates.
    total_machine_minutes = 0.0
    occupancy_by_equipment: dict[str, float] = {}
    for op in estimate_input.operations:
        total_machine_minutes += operation_machine_minutes(op, quantity)
        occupancy = operation_occupancy_minutes(op, quantity)
        if occupancy > 0:
            occupancy_by_equipment[op.equipment_id] = (
                occupancy_by_equipment.get(op.equipment_id, 0.0) + occupancy
            )

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

    equipment_costing = _build_equipment_costing(
        estimate_input, occupancy_by_equipment, repo_root
    )
    equipment_rate_by_id = _equipment_rates(equipment_costing)
    machine_rate = machine_costing.machine_hour_rate

    labor_cost_by_category: dict[str, float] = dict.fromkeys(LABOR_CATEGORIES, 0.0)
    labor_minutes_by_category: dict[str, float] = dict.fromkeys(LABOR_CATEGORIES, 0.0)
    operation_results: list[OperationCostResultV2] = []
    reserve_labor_base = 0.0
    total_labor_minutes = 0.0
    total_occupancy_minutes = 0.0
    total_elapsed_wait_minutes = 0.0
    total_rework_minutes = 0.0

    for op in estimate_input.operations:
        if op.labor_rate_id not in rates:
            raise ValueError(f"missing labor_rate_id reference: {op.labor_rate_id}")
        loaded_rate = rates[op.labor_rate_id].loaded_rate_per_hour

        # Setup recurs per unit unless the operation declares otherwise. At
        # quantity one the two scopes agree exactly, so no existing estimate
        # moves; only a run of more than one unit can tell them apart.
        labor_minutes = op.time_model.labor_minutes_for(quantity)
        labor_cost = calculate_labor_cost(labor_minutes, loaded_rate)
        machine_minutes = operation_machine_minutes(op, quantity)
        occupancy_minutes = operation_occupancy_minutes(op, quantity)

        # Informational allocations only; totals come from the aggregate
        # derivations above. See the module docstring on rounding.
        op_machine_cost = (
            derive_machine_time_cost(machine_rate, machine_minutes)
            if machine_minutes > 0
            else 0.0
        )
        op_occupancy_cost = (
            derive_equipment_occupancy_cost(
                equipment_rate_by_id[op.equipment_id], occupancy_minutes
            )
            if occupancy_minutes > 0
            else 0.0
        )

        labor_cost_by_category[op.labor_category] += labor_cost
        labor_minutes_by_category[op.labor_category] += labor_minutes
        if op.reserve_eligible:
            reserve_labor_base += labor_cost

        total_labor_minutes += labor_minutes
        total_occupancy_minutes += occupancy_minutes
        total_elapsed_wait_minutes += op.time_model.elapsed_wait_minutes * quantity
        total_rework_minutes += op.time_model.rework_minutes * quantity

        operation_results.append(
            OperationCostResultV2(
                operation_id=op.operation_id,
                wbs_code=op.wbs_code,
                labor_category=op.labor_category,
                attendance=op.attendance,
                labor_minutes=labor_minutes,
                machine_runtime_minutes=machine_minutes,
                equipment_occupancy_minutes=occupancy_minutes,
                elapsed_wait_minutes=op.time_model.elapsed_wait_minutes * quantity,
                rework_minutes=op.time_model.rework_minutes * quantity,
                equipment_id=op.equipment_id,
                labor_cost=labor_cost,
                machine_time_cost=as_money(op_machine_cost),
                equipment_occupancy_cost=as_money(op_occupancy_cost),
                operation_cost=as_money(
                    labor_cost + op_machine_cost + op_occupancy_cost
                ),
            )
        )

    material_costs = {
        field_name: calculate_category_cost(
            estimate_input.material_inputs,
            estimate_input.purchased_component_inputs,
            category,
        )
        for category, field_name in _CATEGORY_TO_SUMMARY_FIELD.items()
    }

    machine_time_cost = machine_costing.derived_machine_time_cost
    equipment_occupancy_cost = as_money(
        sum(r.derived_occupancy_cost for r in equipment_costing)
    )

    labor_costs = {
        field_name: as_money(labor_cost_by_category[category])
        for category, field_name in _LABOR_CATEGORY_TO_SUMMARY_FIELD.items()
    }

    scrap_base, scrap_allowance = calculate_material_scrap_allowance(
        material_inputs=estimate_input.material_inputs,
        purchased_component_inputs=estimate_input.purchased_component_inputs,
        eligible_input_ids=estimate_input.material_scrap_policy.eligible_input_ids,
        scrap_rate=estimate_input.material_scrap_policy.scrap_rate,
    )

    reserve_policy = estimate_input.process_yield_reserve_policy
    if reserve_policy.reserve_rate < 0 or reserve_policy.reserve_rate > 1:
        raise ValueError("reserve_rate must be between 0 and 1")
    reserve_material_base = _reserve_material_base(estimate_input, reserve_policy)
    reserve_machine_base = machine_time_cost if reserve_policy.include_machine_time else 0.0
    reserve_equipment_base = (
        equipment_occupancy_cost if reserve_policy.include_equipment_occupancy else 0.0
    )
    reserve_labor_base = as_money(reserve_labor_base)
    reserve_base = as_money(
        reserve_material_base
        + reserve_machine_base
        + reserve_equipment_base
        + reserve_labor_base
    )
    process_reserve = as_money(reserve_base * reserve_policy.reserve_rate)

    total = as_money(
        sum(material_costs.values())
        + machine_time_cost
        + equipment_occupancy_cost
        + sum(labor_costs.values())
        + scrap_allowance
        + process_reserve
    )

    cost_summary = ThinSkinCostSummaryV2(
        core_material_cost=material_costs["core_material_cost"],
        skin_material_cost=material_costs["skin_material_cost"],
        adhesive_and_lamination_consumables=material_costs[
            "adhesive_and_lamination_consumables"
        ],
        neck_and_fretboard_cost=material_costs["neck_and_fretboard_cost"],
        hardware_cost=material_costs["hardware_cost"],
        electronics_cost=material_costs["electronics_cost"],
        finish_material_cost=material_costs["finish_material_cost"],
        other_consumables_cost=material_costs["other_consumables_cost"],
        machine_time_cost=machine_time_cost,
        equipment_occupancy_cost=equipment_occupancy_cost,
        lamination_labor_cost=labor_costs["lamination_labor_cost"],
        direct_build_labor_cost=labor_costs["direct_build_labor_cost"],
        finishing_labor_cost=labor_costs["finishing_labor_cost"],
        assembly_labor_cost=labor_costs["assembly_labor_cost"],
        setup_and_inspection_cost=labor_costs["setup_and_inspection_cost"],
        material_scrap_allowance=scrap_allowance,
        process_rework_and_yield_reserve=process_reserve,
        total_direct_manufacturing_cost=total,
    )

    time_summary = ThinSkinTimeSummaryV2(
        total_labor_minutes=round(total_labor_minutes, 4),
        total_machine_runtime_minutes=round(total_machine_minutes, 4),
        total_equipment_occupancy_minutes=round(total_occupancy_minutes, 4),
        total_elapsed_wait_minutes=round(total_elapsed_wait_minutes, 4),
        total_rework_minutes=round(total_rework_minutes, 4),
        lamination_labor_minutes=round(labor_minutes_by_category["lamination_labor"], 4),
        direct_build_labor_minutes=round(
            labor_minutes_by_category["direct_build_labor"], 4
        ),
        finishing_labor_minutes=round(labor_minutes_by_category["finishing_labor"], 4),
        assembly_labor_minutes=round(labor_minutes_by_category["assembly_labor"], 4),
        setup_and_inspection_minutes=round(
            labor_minutes_by_category["setup_and_inspection"], 4
        ),
    )

    risk_basis = RiskBasisDetailV2(
        material_scrap_rate=estimate_input.material_scrap_policy.scrap_rate,
        material_scrap_base=scrap_base,
        process_reserve_rate=reserve_policy.reserve_rate,
        process_reserve_material_base=reserve_material_base,
        process_reserve_machine_base=reserve_machine_base,
        process_reserve_equipment_base=reserve_equipment_base,
        process_reserve_labor_base=reserve_labor_base,
        process_reserve_base=reserve_base,
        compounding=NO_COMPOUNDING,
    )

    return ThinSkinBuildEstimateV2(
        estimate_id=estimate_id,
        product_id=estimate_input.product_id,
        product_ref=estimate_input.product_ref,
        variant_id=estimate_input.variant_id,
        variant_description=estimate_input.variant_description,
        estimate_input_id=estimate_input.estimate_input_id,
        estimate_input_ref=estimate_input_ref,
        status=estimate_input.status,
        quantity=quantity,
        currency=estimate_input.currency,
        cost_summary=cost_summary,
        time_summary=time_summary,
        risk_basis=risk_basis,
        operation_results=tuple(operation_results),
        machine_costing=machine_costing,
        equipment_costing=equipment_costing,
        calculation=EstimateCalculationMetaV2(
            calculator_id=CALCULATOR_ID,
            rounding_policy=ROUNDING_POLICY,
            effective_date=effective_date,
        ),
        provenance=EstimateProvenanceV2(
            source="calculated",
            confidence=estimate_input.provenance.confidence,
            note=(
                "Internal direct manufacturing cost only. No overhead allocation, "
                "warranty reserve, fulfillment cost, margin, or customer price."
            ),
        ),
        notes=tuple(estimate_input.notes),
    )


__all__ = [
    "CALCULATOR_ID",
    "DEFAULT_ESTIMATE_ID",
    "EquipmentRefV2",
    "ROUNDING_POLICY",
    "calculate_category_cost",
    "calculate_labor_cost",
    "calculate_material_scrap_allowance",
    "calculate_thin_skin_build_estimate",
    "operation_machine_minutes",
    "operation_occupancy_minutes",
]
