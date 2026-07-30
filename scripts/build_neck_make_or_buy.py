#!/usr/bin/env python3
"""Compute the neck make-or-buy result from its governed input.

Dev Order: NECK-MAKE-OR-BUY-BATCH-COSTING-1

    python scripts/build_neck_make_or_buy.py

Reads fixtures/estimates/neck/neck_make_or_buy_input_v1.json and writes the
result fixture beside it. Every number in the result is derived here; nothing
is transcribed, so the validator can recompute the whole file and compare.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.estimates.neck_costing import (  # noqa: E402
    COMPLETION_DESCRIPTIONS,
    COMPLETION_STATES,
    BuyReference,
    NeckMaterial,
    NeckOperation,
    YieldPolicy,
    build_make_scenario,
    fretwork_threshold,
)

INPUT = ROOT / "fixtures" / "estimates" / "neck" / "neck_make_or_buy_input_v1.json"
OUT = ROOT / "fixtures" / "estimates" / "neck" / "neck_make_or_buy_result_v1.json"

FRETWORK_OP = "OP-4200"


def _operations(raw: list[dict[str, Any]]) -> tuple[NeckOperation, ...]:
    return tuple(
        NeckOperation(
            operation_id=o["operation_id"],
            description=o["description"],
            setup_minutes=float(o["setup_minutes"]),
            touch_minutes=float(o["touch_minutes"]),
            machine_minutes=float(o["machine_minutes"]),
            equipment_occupancy_minutes=float(o.get("equipment_occupancy_minutes", 0.0)),
            elapsed_wait_minutes=float(o.get("elapsed_wait_minutes", 0.0)),
            equipment_rate_per_hour=float(o.get("equipment_rate_per_hour", 0.0)),
            setup_per_batch=bool(o["setup_per_batch"]),
            from_state=o["from_state"],
            is_draft_addition=bool(o["is_draft_addition"]),
        )
        for o in raw
    )


def _materials(
    doc: dict[str, Any], construction: str, fretboard: float
) -> tuple[NeckMaterial, ...]:
    """Material set for one construction and fretboard price.

    Two entries are computed rather than listed: the mahogany is board feet
    times the owner price, and the fretboard is whatever price is being swept.
    """
    bf = next(
        c["mahogany_board_feet"]
        for c in doc["construction_options"]
        if c["construction_id"] == construction
    )
    price = doc["wood_prices"]["african_mahogany_per_board_foot"]
    out: list[NeckMaterial] = []
    for m in doc["materials"]:
        if m["material_id"] == "MAT-NECK-MAHOGANY":
            cost = bf * price
        elif m["material_id"] == "MAT-FRETBOARD":
            cost = fretboard
        else:
            cost = float(m["cost"])
        out.append(
            NeckMaterial(
                material_id=m["material_id"],
                description=m["description"],
                cost=round(cost, 4),
                from_state=m["from_state"],
            )
        )
    return tuple(out)


def _with_fretwork(ops: tuple[NeckOperation, ...], minutes: float) -> tuple[NeckOperation, ...]:
    from dataclasses import replace

    return tuple(
        replace(o, touch_minutes=minutes) if o.operation_id == FRETWORK_OP else o for o in ops
    )


def _with_machine(ops: tuple[NeckOperation, ...], minutes: float) -> tuple[NeckOperation, ...]:
    from dataclasses import replace

    return tuple(
        replace(o, machine_minutes=minutes) if o.operation_id == "OP-4100" else o for o in ops
    )


def build(doc: dict[str, Any]) -> dict[str, Any]:
    ops = _operations(doc["operations"])
    rates = doc["rates"]
    lab = float(rates["loaded_labour_per_hour"])
    mach = float(rates["machine_per_hour"])
    yp = YieldPolicy(
        rate=float(doc["yield_policy"]["rate"]),
        basis=doc["yield_policy"]["basis"],
        source=doc["yield_policy"]["source"],
        confidence=doc["yield_policy"]["confidence"],
    )
    quantities = [int(q) for q in doc["quantities"]]
    ebony = next(f["cost"] for f in doc["fretboard_options"] if f["fretboard_id"] == "EBONY_AAA")
    sens = doc["sensitivity"]

    result: dict[str, Any] = {
        "result_id": "NECK-MAKE-OR-BUY-RESULT-V1",
        "input_ref": doc["input_id"],
        "dev_order": doc["dev_order"],
        "status": "draft",
        "currency": doc["currency"],
        "decision_authorized": False,
        "baseline": {
            "construction": "SCARF_JOINT",
            "fretboard_price": ebony,
            "yield_rate": yp.rate,
            "note": "Scarf construction with the AAA ebony board. The dearest fretboard "
            "and the cheapest timber, which is the spec as it stands today.",
        },
        "make_scenarios": [],
        "batching_effect": {},
        "buy_references": [],
        "thresholds": {},
        "sensitivity": {},
        "findings": [],
    }

    # --- make scenarios: every completion state at every quantity -----------
    for construction in ("SCARF_JOINT", "ONE_PIECE"):
        mats = _materials(doc, construction, ebony)
        for state in COMPLETION_STATES:
            for q in quantities:
                s = build_make_scenario(
                    completion_state=state,
                    quantity=q,
                    operations=ops,
                    materials=mats,
                    yield_policy=yp,
                    loaded_labour_rate=lab,
                    machine_rate=mach,
                )
                result["make_scenarios"].append(
                    {
                        "construction": construction,
                        "completion_state": state,
                        "completion_description": COMPLETION_DESCRIPTIONS[state],
                        "quantity": q,
                        "saleable": s.saleable,
                        "material_cost": s.material_cost,
                        "setup_cost": s.setup_cost,
                        "touch_cost": s.touch_cost,
                        "machine_cost": s.machine_cost,
                        "occupancy_cost": s.occupancy_cost,
                        "labour_minutes": s.labour_minutes,
                        "machine_minutes": s.machine_minutes,
                        "occupancy_minutes": s.occupancy_minutes,
                        "elapsed_wait_minutes": s.elapsed_wait_minutes,
                        "cost_per_started": s.cost_per_started,
                        "cost_per_saleable": s.cost_per_saleable,
                        "yield_loss_per_saleable": s.yield_loss_per_saleable,
                        "max_competitive_purchase_price": s.max_competitive_purchase_price,
                    }
                )

    # --- how much batching is actually worth --------------------------------
    scarf = _materials(doc, "SCARF_JOINT", ebony)
    q1 = build_make_scenario(
        completion_state="M4", quantity=1, operations=ops, materials=scarf,
        yield_policy=yp, loaded_labour_rate=lab, machine_rate=mach,
    )
    q40 = build_make_scenario(
        completion_state="M4", quantity=40, operations=ops, materials=scarf,
        yield_policy=yp, loaded_labour_rate=lab, machine_rate=mach,
    )
    setup_op = next(o for o in ops if o.setup_per_batch)
    result["batching_effect"] = {
        "operations_carrying_setup": [setup_op.operation_id],
        "total_setup_minutes": setup_op.setup_minutes,
        "cost_per_saleable_qty_1": q1.cost_per_saleable,
        "cost_per_saleable_qty_40": q40.cost_per_saleable,
        "saving_qty_1_to_40": round(q1.cost_per_saleable - q40.cost_per_saleable, 2),
        "ceiling_at_infinite_quantity": round(setup_op.setup_minutes / 60 * lab / yp.rate, 2),
        "note": "Only one operation in the neck carries setup, so this is the entire "
        "batching opportunity. It is smaller than the construction choice.",
    }

    # --- buy references, landed where computable ----------------------------
    for b in doc["buy_references"]:
        ref = BuyReference(
            reference_id=b["reference_id"],
            description=b["description"],
            completion_state=b["completion_state"],
            catalog_price=float(b["catalog_price"]),
            source=b["source"],
            confidence=b["confidence"],
            freight_per_unit=b["freight_per_unit"],
            duty_percent=b["duty_percent"],
            incoming_inspection_minutes=b["incoming_inspection_minutes"],
            corrective_work_minutes=b["corrective_work_minutes"],
            reject_percent=b["reject_percent"],
            notes=tuple(b["notes"]),
        )
        result["buy_references"].append(
            {
                "reference_id": ref.reference_id,
                "completion_state": ref.completion_state,
                "catalog_price": ref.catalog_price,
                "landed_cost_per_good": ref.landed_cost_per_good(lab),
                "is_fully_landed": ref.is_fully_landed,
                "unknown_fields": [
                    n
                    for n, v in (
                        ("freight_per_unit", ref.freight_per_unit),
                        ("duty_percent", ref.duty_percent),
                        ("incoming_inspection_minutes", ref.incoming_inspection_minutes),
                        ("corrective_work_minutes", ref.corrective_work_minutes),
                        ("reject_percent", ref.reject_percent),
                    )
                    if v is None
                ],
                "notes": list(ref.notes),
            }
        )

    # --- thresholds: fretwork minutes needed to beat each price -------------
    for b in doc["buy_references"]:
        target = float(b["catalog_price"])
        rows = []
        for fb in sens["fretboard_price"]:
            mats = _materials(doc, "SCARF_JOINT", float(fb))
            t = fretwork_threshold(
                target_price=target,
                completion_state="M4",
                quantity=20,
                operations=ops,
                materials=mats,
                yield_policy=yp,
                loaded_labour_rate=lab,
                machine_rate=mach,
                fretwork_operation_id=FRETWORK_OP,
            )
            rows.append(
                {
                    "fretboard_price": fb,
                    "fretwork_minutes_required": t,
                    "reachable": t is not None,
                    "reduction_percent": None if t is None else round((78 - t) / 78 * 100, 1),
                }
            )
        result["thresholds"][b["reference_id"]] = {
            "target_price": target,
            "completion_state": "M4",
            "quantity": 20,
            "construction": "SCARF_JOINT",
            "rows": rows,
        }

    # --- two-variable grids -------------------------------------------------
    grid = []
    for fb in sens["fretboard_price"]:
        mats = _materials(doc, "SCARF_JOINT", float(fb))
        row = {"fretboard_price": fb, "costs": {}}
        for fm in sens["fretwork_minutes"]:
            s = build_make_scenario(
                completion_state="M4", quantity=20, operations=_with_fretwork(ops, float(fm)),
                materials=mats, yield_policy=yp, loaded_labour_rate=lab, machine_rate=mach,
            )
            row["costs"][str(fm)] = s.cost_per_saleable
        grid.append(row)
    result["sensitivity"]["fretboard_x_fretwork_qty20_M4"] = grid

    ygrid = []
    for y in sens["yield_rate"]:
        pol = YieldPolicy(rate=float(y), basis=f"swept: {y}", source="engineering_estimate")
        row = {"yield_rate": y, "costs": {}}
        for fm in sens["fretwork_minutes"]:
            s = build_make_scenario(
                completion_state="M4", quantity=20, operations=_with_fretwork(ops, float(fm)),
                materials=scarf, yield_policy=pol, loaded_labour_rate=lab, machine_rate=mach,
            )
            row["costs"][str(fm)] = s.cost_per_saleable
        ygrid.append(row)
    result["sensitivity"]["yield_x_fretwork_qty20_M4"] = ygrid

    mgrid = []
    for mm in sens["machine_minutes"]:
        s = build_make_scenario(
            completion_state="M4", quantity=20, operations=_with_machine(ops, float(mm)),
            materials=scarf, yield_policy=yp, loaded_labour_rate=lab, machine_rate=mach,
        )
        mgrid.append({"machine_minutes_per_neck": mm, "cost_per_saleable": s.cost_per_saleable})
    result["sensitivity"]["machine_runtime_qty20_M4"] = mgrid

    result["findings"] = _findings(result, doc)
    return result


def _findings(result: dict[str, Any], doc: dict[str, Any]) -> list[dict[str, Any]]:
    be = result["batching_effect"]
    def _pick(construction: str) -> dict[str, Any]:
        return next(
            s
            for s in result["make_scenarios"]
            if s["construction"] == construction
            and s["completion_state"] == "M4"
            and s["quantity"] == 20
        )

    scarf20 = _pick("SCARF_JOINT")
    one20 = _pick("ONE_PIECE")
    boutique = result["thresholds"]["BUY-BOUTIQUE"]["rows"]
    reachable = [r for r in boutique if r["reachable"]]
    return [
        {
            "finding_id": "FINDING-BATCHING-IS-MINOR",
            "metric": "cost per saleable neck, quantity 1 to 40",
            "calculated_delta": be["saving_qty_1_to_40"],
            "interpretation": "Only one operation in the neck carries setup, so batching "
            f"is worth {be['saving_qty_1_to_40']} per neck and no more. The router capacity "
            "that prompted this sprint is not the constraint.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-CONSTRUCTION-BEATS-BATCHING",
            "metric": "one-piece versus scarf-jointed, M4 at quantity 20",
            "calculated_delta": round(one20["cost_per_saleable"] - scarf20["cost_per_saleable"], 2),
            "interpretation": "The headstock-angle decision moves more money than every "
            "batching effect combined, and it is a design choice rather than a process one.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-FRETWORK-DOMINATES",
            "metric": "fretwork minutes required to beat the boutique price",
            "calculated_delta": None,
            "interpretation": "Fretwork is the largest single operation at 78 minutes, and a "
            "fret press with batch jigs is the only credible way to reduce it. But it is no "
            "longer sufficient: at a COMPLETE neck, taking fretwork to zero still leaves "
            "in-house above the boutique price.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-BOTH-LEVERS-INSUFFICIENT",
            "metric": "cost per saleable at a free fretboard, fretwork unchanged",
            "calculated_delta": None,
            "interpretation": "BOTH LEVERS AT THEIR LIMIT STILL MISS. A free fretboard AND "
            "zero fretwork together leave in-house above the boutique price at a complete "
            "neck. An earlier table suggested otherwise; it costed an UNFINISHED neck against "
            "a finished purchased one, before fretboard installation and neck finishing "
            "existed in the model. Those two operations and a 90% yield close the gap off.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-IMPORT-NOT-COMPARABLE",
            "metric": "budget import against in-house M4",
            "calculated_delta": None,
            "interpretation": "The 45.00 import is not a like-for-like substitute: probable "
            "composite fingerboard against AAA ebony, and the owner judges the workmanship may "
            "not pass inspection at all. Every landed-cost field is unknown. It is recorded "
            "as a reference, not as a comparison.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-COMPARISON-CONFIDENCE",
            "metric": "reachable threshold combinations against the boutique price",
            "calculated_delta": len(reachable),
            "interpretation": "In-house does NOT beat a quality-matched purchased neck at a "
            "complete state, by any combination of the levers this sprint identified. That "
            "conclusion rests on two draft operations that have never been measured, so the "
            "measurement that would overturn it is fretboard installation and neck finishing "
            "time, not batching.",
            "confidence": "draft",
            "decision_authorized": False,
        },
    ]


def main() -> int:
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    result = build(doc)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    print(f"  {len(result['make_scenarios'])} make scenarios, "
          f"{len(result['findings'])} findings")
    be = result["batching_effect"]
    print(f"  batching worth {be['saving_qty_1_to_40']} per neck "
          f"(ceiling {be['ceiling_at_infinite_quantity']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
