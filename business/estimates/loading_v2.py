"""Load thin-skin estimate fixtures into domain models.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from business.estimates.models_v2 import (
    EquipmentRefV2,
    EstimateProvenanceV2,
    LaborRateInputV2,
    ManufacturingOperationV2,
    MaterialInputV2,
    MaterialScrapPolicyV2,
    OperationTimeModelV2,
    ProcessYieldReservePolicyV2,
    PurchasedComponentInputV2,
    ThinSkinEstimateInputV2,
)


def _prov(data: dict[str, Any]) -> EstimateProvenanceV2:
    return EstimateProvenanceV2(
        source=str(data["source"]),
        confidence=str(data["confidence"]),
        note=str(data.get("note", "") or ""),
    )


def _time_model(data: dict[str, Any]) -> OperationTimeModelV2:
    return OperationTimeModelV2(
        setup_minutes=float(data.get("setup_minutes", 0.0)),
        operator_touch_minutes=float(data.get("operator_touch_minutes", 0.0)),
        machine_runtime_minutes=float(data.get("machine_runtime_minutes", 0.0)),
        equipment_occupancy_minutes=float(data.get("equipment_occupancy_minutes", 0.0)),
        elapsed_wait_minutes=float(data.get("elapsed_wait_minutes", 0.0)),
        rework_minutes=float(data.get("rework_minutes", 0.0)),
    )


def load_thin_skin_estimate_input(path: Path) -> ThinSkinEstimateInputV2:
    """Load ThinSkinEstimateInputV2 from a JSON fixture path."""
    with open(path, encoding="utf-8") as f:
        raw = cast(dict[str, Any], json.load(f))

    return ThinSkinEstimateInputV2(
        estimate_input_id=raw["estimate_input_id"],
        product_id=raw["product_id"],
        product_ref=raw["product_ref"],
        variant_id=raw["variant_id"],
        variant_description=raw["variant_description"],
        status=raw["status"],
        quantity=int(raw["quantity"]),
        currency=raw["currency"],
        material_inputs=tuple(
            MaterialInputV2(
                input_id=m["input_id"],
                description=m["description"],
                category=m["category"],
                quantity=float(m["quantity"]),
                unit=m["unit"],
                unit_cost=float(m["unit_cost"]),
                provenance=_prov(m["provenance"]),
            )
            for m in raw["material_inputs"]
        ),
        purchased_component_inputs=tuple(
            PurchasedComponentInputV2(
                input_id=p["input_id"],
                description=p["description"],
                category=p["category"],
                quantity=float(p["quantity"]),
                unit=p["unit"],
                unit_cost=float(p["unit_cost"]),
                provenance=_prov(p["provenance"]),
            )
            for p in raw["purchased_component_inputs"]
        ),
        labor_rate_inputs=tuple(
            LaborRateInputV2(
                labor_rate_id=r["labor_rate_id"],
                description=r["description"],
                base_wage_per_hour=float(r["base_wage_per_hour"]),
                payroll_burden_pct=float(r["payroll_burden_pct"]),
                loaded_rate_per_hour=float(r["loaded_rate_per_hour"]),
                provenance=_prov(r["provenance"]),
            )
            for r in raw["labor_rate_inputs"]
        ),
        operations=tuple(
            ManufacturingOperationV2(
                operation_id=o["operation_id"],
                wbs_code=o["wbs_code"],
                description=o["description"],
                labor_category=o["labor_category"],
                attendance=o["attendance"],
                time_model=_time_model(o["time_model"]),
                labor_rate_id=o["labor_rate_id"],
                provenance=_prov(o["provenance"]),
                uses_machine=bool(o.get("uses_machine", False)),
                equipment_id=str(o.get("equipment_id", "") or ""),
                reserve_eligible=bool(o.get("reserve_eligible", False)),
            )
            for o in raw["operations"]
        ),
        machine_profile_ref=raw["machine_profile_ref"],
        cost_basis_ref=raw["cost_basis_ref"],
        machine_id=raw["machine_id"],
        cost_basis_id=raw["cost_basis_id"],
        equipment_refs=tuple(
            EquipmentRefV2(
                equipment_id=e["equipment_id"],
                equipment_profile_ref=e["equipment_profile_ref"],
                cost_basis_ref=e["cost_basis_ref"],
                cost_basis_id=e["cost_basis_id"],
            )
            for e in raw["equipment_refs"]
        ),
        material_scrap_policy=MaterialScrapPolicyV2(
            scrap_rate=float(raw["material_scrap_policy"]["scrap_rate"]),
            eligible_input_ids=tuple(
                raw["material_scrap_policy"]["eligible_input_ids"]
            ),
            provenance=_prov(raw["material_scrap_policy"]["provenance"]),
        ),
        process_yield_reserve_policy=ProcessYieldReservePolicyV2(
            reserve_rate=float(raw["process_yield_reserve_policy"]["reserve_rate"]),
            eligible_input_ids=tuple(
                raw["process_yield_reserve_policy"]["eligible_input_ids"]
            ),
            include_machine_time=bool(
                raw["process_yield_reserve_policy"]["include_machine_time"]
            ),
            include_equipment_occupancy=bool(
                raw["process_yield_reserve_policy"]["include_equipment_occupancy"]
            ),
            provenance=_prov(raw["process_yield_reserve_policy"]["provenance"]),
        ),
        provenance=_prov(raw["provenance"]),
        notes=tuple(raw.get("notes", [])),
    )
