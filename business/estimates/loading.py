"""Load guitar estimate fixtures into domain models.

Dev Order: GUITAR-BUILD-ESTIMATE-1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from business.estimates.models import (
    EstimateProvenanceV1,
    GuitarEstimateInputV1,
    LaborRateInputV1,
    ManufacturingOperationV1,
    MaterialInputV1,
    PurchasedComponentInputV1,
    ScrapPolicyV1,
)


def _prov(data: dict[str, Any]) -> EstimateProvenanceV1:
    return EstimateProvenanceV1(
        source=str(data["source"]),
        confidence=str(data["confidence"]),
        note=str(data.get("note", "") or ""),
    )


def load_guitar_estimate_input(path: Path) -> GuitarEstimateInputV1:
    """Load GuitarEstimateInputV1 from a JSON fixture path."""
    with open(path, encoding="utf-8") as f:
        raw = cast(dict[str, Any], json.load(f))

    return GuitarEstimateInputV1(
        estimate_input_id=raw["estimate_input_id"],
        product_id=raw["product_id"],
        product_ref=raw["product_ref"],
        status=raw["status"],
        quantity=int(raw["quantity"]),
        currency=raw["currency"],
        material_inputs=tuple(
            MaterialInputV1(
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
            PurchasedComponentInputV1(
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
            LaborRateInputV1(
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
            ManufacturingOperationV1(
                operation_id=o["operation_id"],
                wbs_code=o["wbs_code"],
                description=o["description"],
                cost_category=o["cost_category"],
                attendance=o["attendance"],
                setup_minutes=float(o["setup_minutes"]),
                run_minutes_per_unit=float(o["run_minutes_per_unit"]),
                setup_labor_minutes=float(o["setup_labor_minutes"]),
                attended_run_labor_minutes=float(o["attended_run_labor_minutes"]),
                manual_labor_minutes=float(o["manual_labor_minutes"]),
                cure_or_wait_minutes=float(o["cure_or_wait_minutes"]),
                uses_machine=bool(o["uses_machine"]),
                labor_rate_id=o["labor_rate_id"],
                provenance=_prov(o["provenance"]),
            )
            for o in raw["operations"]
        ),
        machine_profile_ref=raw["machine_profile_ref"],
        cost_basis_ref=raw["cost_basis_ref"],
        machine_id=raw["machine_id"],
        cost_basis_id=raw["cost_basis_id"],
        scrap_policy=ScrapPolicyV1(
            scrap_rate=float(raw["scrap_policy"]["scrap_rate"]),
            eligible_input_ids=tuple(raw["scrap_policy"]["eligible_input_ids"]),
            provenance=_prov(raw["scrap_policy"]["provenance"]),
        ),
        provenance=_prov(raw["provenance"]),
        notes=tuple(raw.get("notes", [])),
    )
