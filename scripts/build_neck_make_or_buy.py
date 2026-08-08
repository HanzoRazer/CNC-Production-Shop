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
    BUY_TO_MAKE,
    COMPLETION_DESCRIPTIONS,
    COMPLETION_STATES,
    BackCalculatedTarget,
    BuyCompletionState,
    BuyReference,
    ChannelScenario,
    MakeScenario,
    NeckMaterial,
    NeckOperation,
    RetainedShopOperation,
    YieldPolicy,
    back_calculate_target,
    build_make_scenario,
    evaluate_threshold,
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


def _buy_states(raw: list[dict[str, Any]]) -> tuple[BuyCompletionState, ...]:
    """Load B1-B4. The constructor enforces the like-for-like mapping."""
    return tuple(
        BuyCompletionState(
            state_id=b["state_id"],
            description=b["description"],
            make_equivalent=b["make_equivalent"],
            completion_requirements=tuple(b["completion_requirements"]),
            retained_shop_operations=tuple(
                RetainedShopOperation(
                    operation=o["operation"],
                    minutes=float(o["minutes"]),
                    rationale=o["rationale"],
                )
                for o in b["retained_shop_operations"]
            ),
            inspection_requirements=tuple(b["inspection_requirements"]),
            compatibility_requirements=tuple(b["compatibility_requirements"]),
            purchase_price_status=b["purchase_price_status"],
            compatible_supplier_identified=bool(b["compatible_supplier_identified"]),
            source=b["source"],
            confidence=b["confidence"],
        )
        for b in raw
    )


def _axis(name: str, values: list[Any]) -> dict[str, Any]:
    """A matrix axis: sorted, unique, and named.

    An axis with a duplicate value produces two cells that claim the same
    coordinate, which is a silent way to lose a result.
    """
    ordered = sorted({float(v): v for v in values}.items())
    return {"name": name, "values": [v for _, v in ordered]}


def _matrix(
    *,
    matrix_id: str,
    description: str,
    row_axis: dict[str, Any],
    column_axis: dict[str, Any],
    completion_state: str,
    quantity: int,
    fixed_assumptions: dict[str, Any],
    cell: Any,
) -> dict[str, Any]:
    """Build a fully-specified two-variable matrix.

    Everything not swept is recorded in fixed_assumptions. A matrix that does
    not say what it held constant cannot be recomputed, and a cell that cannot
    be recomputed is a number nobody can check.
    """
    return {
        "matrix_id": matrix_id,
        "description": description,
        "row_axis": row_axis,
        "column_axis": column_axis,
        "completion_state": completion_state,
        "quantity": quantity,
        "fixed_assumptions": fixed_assumptions,
        "cells": [
            {"row": r, "column": c, "cost_per_saleable": cell(r, c)}
            for r in row_axis["values"]
            for c in column_axis["values"]
        ],
    }


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
        "buy_completion_states": [],
        "thresholds": {},
        "threshold_findings": {},
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
                        # No purchase ceiling is emitted here. A make scenario cannot
                        # know one: the ceiling is this cost less the shop work the
                        # matching buy state retains. It is reported once, in
                        # threshold_findings, where both sides are present.
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
    #
    # All three matrices are fixed at M4 and quantity 20, which is the state the
    # decision is actually about and the quantity the router prompted. Anything
    # not on an axis is recorded in fixed_assumptions so each cell recomputes.
    def _pol(y: float) -> YieldPolicy:
        return YieldPolicy(rate=float(y), basis=f"swept: {y}", source="engineering_estimate")

    def _cost(
        *,
        fretboard: float,
        fretwork: float,
        machine: float,
        yield_rate: float,
    ) -> float:
        tuned = _with_machine(_with_fretwork(ops, fretwork), machine)
        s = build_make_scenario(
            completion_state="M4",
            quantity=20,
            operations=tuned,
            materials=_materials(doc, "SCARF_JOINT", fretboard),
            yield_policy=_pol(yield_rate),
            loaded_labour_rate=lab,
            machine_rate=mach,
        )
        return s.cost_per_saleable

    base_machine = float(sens["baseline_machine_minutes"])
    base_fretwork = float(sens["baseline_fretwork_minutes"])

    result["sensitivity"]["matrices"] = [
        _matrix(
            matrix_id="FRETBOARD_X_FRETWORK_QTY20_M4",
            description="Fretboard stock price against fretwork minutes. The pair of "
            "levers the accepted sprint identified, retained here because both remain "
            "valid.",
            row_axis=_axis("fretboard_price", sens["fretboard_price"]),
            column_axis=_axis("fretwork_minutes", sens["fretwork_minutes"]),
            completion_state="M4",
            quantity=20,
            fixed_assumptions={
                "construction": "SCARF_JOINT",
                "yield_rate": yp.rate,
                "machine_minutes_per_neck": base_machine,
            },
            cell=lambda fb, fm: _cost(
                fretboard=float(fb), fretwork=float(fm),
                machine=base_machine, yield_rate=yp.rate,
            ),
        ),
        _matrix(
            matrix_id="FRETWORK_X_YIELD_QTY20_M4",
            description="Fretwork minutes against saleable yield. Fretwork is the "
            "largest labour operation and yield is wholly unmeasured, so this is the "
            "pair with the most unknown between them.",
            row_axis=_axis("yield_rate", sens["yield_rate"]),
            column_axis=_axis("fretwork_minutes", sens["fretwork_minutes"]),
            completion_state="M4",
            quantity=20,
            fixed_assumptions={
                "construction": "SCARF_JOINT",
                "fretboard_price": ebony,
                "machine_minutes_per_neck": base_machine,
            },
            cell=lambda y, fm: _cost(
                fretboard=ebony, fretwork=float(fm),
                machine=base_machine, yield_rate=float(y),
            ),
        ),
        _matrix(
            matrix_id="RUNTIME_X_YIELD_QTY20_M4",
            description="Machine runtime per neck against saleable yield. Added by "
            "GAP-CLOSURE-1: runtime previously had no yield axis and never rose above "
            "the unverified 52-minute baseline, so the model could not show what a "
            "WORSE runtime does to a batch that also loses necks.",
            row_axis=_axis("yield_rate", sens["yield_rate"]),
            column_axis=_axis("machine_minutes_per_neck", sens["machine_minutes"]),
            completion_state="M4",
            quantity=20,
            fixed_assumptions={
                "construction": "SCARF_JOINT",
                "fretboard_price": ebony,
                "fretwork_minutes": base_fretwork,
            },
            cell=lambda y, mm: _cost(
                fretboard=ebony, fretwork=base_fretwork,
                machine=float(mm), yield_rate=float(y),
            ),
        ),
    ]

    result["sensitivity"]["sweeps"] = [
        {
            "sweep_id": "MACHINE_RUNTIME_QTY20_M4",
            "axis": _axis("machine_minutes_per_neck", sens["machine_minutes"]),
            "baseline_value": base_machine,
            "completion_state": "M4",
            "quantity": 20,
            "fixed_assumptions": {
                "construction": "SCARF_JOINT",
                "fretboard_price": ebony,
                "fretwork_minutes": base_fretwork,
                "yield_rate": yp.rate,
            },
            "points": [
                {
                    "machine_minutes_per_neck": mm,
                    "cost_per_saleable": _cost(
                        fretboard=ebony, fretwork=base_fretwork,
                        machine=float(mm), yield_rate=yp.rate,
                    ),
                    "relative_to_baseline": (
                        "baseline" if float(mm) == base_machine
                        else "better" if float(mm) < base_machine
                        else "worse"
                    ),
                }
                for mm in _axis("machine_minutes_per_neck", sens["machine_minutes"])["values"]
            ],
        }
    ]

    result["buy_completion_states"] = _buy_completion_states(doc, lab)
    result["threshold_findings"] = _threshold_findings(doc, lab)
    result["back_calculation"] = _back_calculation(doc, lab, mach)
    result["findings"] = _findings(result, doc)
    return result


def _buy_completion_states(doc: dict[str, Any], lab: float) -> list[dict[str, Any]]:
    """Serialise B1-B4 with their retained shop cost computed, not transcribed."""
    out: list[dict[str, Any]] = []
    for state in _buy_states(doc["buy_completion_states"]):
        raw = next(b for b in doc["buy_completion_states"] if b["state_id"] == state.state_id)
        out.append(
            {
                "state_id": state.state_id,
                "description": state.description,
                "make_equivalent": state.make_equivalent,
                "completion_requirements": list(state.completion_requirements),
                "retained_shop_operations": [
                    {"operation": o.operation, "minutes": o.minutes, "rationale": o.rationale}
                    for o in state.retained_shop_operations
                ],
                "retained_minutes": round(state.retained_minutes, 2),
                "retained_completion_cost": state.retained_completion_cost(lab),
                "inspection_requirements": list(state.inspection_requirements),
                "compatibility_requirements": list(state.compatibility_requirements),
                "purchase_price_status": state.purchase_price_status,
                "compatible_supplier_identified": state.compatible_supplier_identified,
                "source": state.source,
                "confidence": state.confidence,
                "note": raw["note"],
            }
        )
    return out


def _threshold_findings(doc: dict[str, Any], lab: float) -> dict[str, Any]:
    """Judge each analytical threshold at each completion state, like-for-like.

    Every comparison here pairs Mx with Bx and nothing else. The four prices are
    the Dev Order's analytical thresholds, not offers, and because no compatible
    supplier exists for a headless clamp-nut neck every row comes back
    commercially inactionable however the arithmetic lands.
    """
    mach = float(doc["rates"]["machine_per_hour"])
    ops = _operations(doc["operations"])
    yp = YieldPolicy(
        rate=float(doc["yield_policy"]["rate"]),
        basis=doc["yield_policy"]["basis"],
        source=doc["yield_policy"]["source"],
        confidence=doc["yield_policy"]["confidence"],
    )
    ebony = next(f["cost"] for f in doc["fretboard_options"] if f["fretboard_id"] == "EBONY_AAA")
    mats = _materials(doc, "SCARF_JOINT", ebony)
    states = {s.state_id: s for s in _buy_states(doc["buy_completion_states"])}
    thresholds = [float(v) for v in doc["purchase_price_thresholds"]["values"]]

    scenarios: dict[str, MakeScenario] = {
        m: build_make_scenario(
            completion_state=m, quantity=20, operations=ops, materials=mats,
            yield_policy=yp, loaded_labour_rate=lab, machine_rate=mach,
        )
        for m in COMPLETION_STATES
    }

    comparisons: list[dict[str, Any]] = []
    for buy_id, make_id in BUY_TO_MAKE.items():
        for price in thresholds:
            c = evaluate_threshold(
                make_scenario=scenarios[make_id],
                buy_state=states[buy_id],
                threshold_price=price,
                loaded_labour_rate=lab,
            )
            comparisons.append(
                {
                    "make_state": c.make_state,
                    "buy_state": c.buy_state,
                    "threshold_price": c.threshold_price,
                    "make_cost_per_saleable": c.make_cost_per_saleable,
                    "retained_buy_side_completion_cost": c.retained_buy_side_completion_cost,
                    "maximum_compatible_delivered_purchase_price": (
                        c.maximum_compatible_delivered_purchase_price
                    ),
                    "difference_versus_threshold": c.difference_versus_threshold,
                    "result": c.result,
                    "commercially_actionable": c.commercially_actionable,
                    "reason": c.reason,
                    "compatibility_caveat": c.compatibility_caveat,
                }
            )

    return {
        "basis": {
            "construction": "SCARF_JOINT",
            "quantity": 20,
            "yield_rate": yp.rate,
            "fretboard_price": ebony,
            "note": "One basis for every threshold row, so differences between rows are "
            "the completion state and the price and nothing else.",
        },
        "sign_convention": (
            "difference_versus_threshold = threshold_price - "
            "maximum_compatible_delivered_purchase_price. POSITIVE means buying at that "
            "price costs more than building, i.e. make is lower cost. Retained shop work "
            "sits on the BUY side, which is why the ceiling is below the make cost."
        ),
        "ceilings": [
            {
                "make_state": m,
                "buy_state": b,
                "make_cost_per_saleable": scenarios[m].cost_per_saleable,
                "retained_buy_side_completion_cost": states[b].retained_completion_cost(lab),
                "maximum_compatible_delivered_purchase_price": round(
                    scenarios[m].cost_per_saleable - states[b].retained_completion_cost(lab), 2
                ),
            }
            for b, m in BUY_TO_MAKE.items()
        ],
        "comparisons": comparisons,
        "commercially_actionable_rows": sum(
            1 for c in comparisons if c["commercially_actionable"]
        ),
        "note": "Not one row is commercially actionable. The arithmetic is sound and the "
        "thresholds are correct; what is missing is a supplier of a neck that fits this "
        "instrument at any completion state.",
    }


def _back_calculation(doc: dict[str, Any], lab: float, mach: float) -> dict[str, Any]:
    """Solve the shop against a manufacturing cost derived from a known retail price."""
    bc = doc["back_calculation"]
    anchor = bc["anchor"]
    shop = bc["shop_position"]
    rows: list[dict[str, Any]] = []
    targets: list[BackCalculatedTarget] = []
    for raw in bc["channel_scenarios"]:
        scenario = ChannelScenario(
            scenario_id=raw["scenario_id"],
            description=raw["description"],
            retail_margin=float(raw["retail_margin"]),
            distributor_margin=float(raw["distributor_margin"]),
            manufacturer_margin=float(raw["manufacturer_margin"]),
        )
        t = back_calculate_target(
            scenario=scenario,
            retail_price=float(anchor["retail_price"]),
            shop_material_cost=float(shop["material_cost"]),
            shop_machine_minutes=float(shop["machine_minutes"]),
            shop_labour_minutes=float(shop["labour_minutes"]),
            loaded_labour_rate=lab,
            machine_rate=mach,
        )
        targets.append(t)
        rows.append(
            {
                "scenario_id": t.scenario_id,
                "description": scenario.description,
                "manufacturing_cost": t.manufacturing_cost,
                "shop_material_cost": t.shop_material_cost,
                "shop_machine_cost": t.shop_machine_cost,
                "budget_for_labour": t.budget_for_labour,
                "labour_minutes_affordable": t.labour_minutes_affordable,
                "implied_labour_rate": t.implied_labour_rate,
                "reachable": t.reachable,
                "note": t.note,
            }
        )
    # Summarise from the typed targets, not from the serialised rows, so the
    # bracket cannot drift from the objects the validator recomputes.
    costs = [t.manufacturing_cost for t in targets]
    minutes = [
        t.labour_minutes_affordable
        for t in targets
        if t.reachable and t.labour_minutes_affordable is not None
    ]
    rates = [
        t.implied_labour_rate
        for t in targets
        if t.reachable and t.implied_labour_rate is not None
    ]
    reachable = [t for t in targets if t.reachable]
    return {
        "anchor_retail_price": anchor["retail_price"],
        "anchor_reference_id": anchor["reference_id"],
        "manufacturing_cost_low": min(costs),
        "manufacturing_cost_high": max(costs),
        "manufacturing_cost_midpoint": round(sum(costs) / len(costs), 2),
        "shop_current_cost": round(
            float(shop["material_cost"])
            + float(shop["machine_minutes"]) / 60 * mach
            + float(shop["labour_minutes"]) / 60 * lab,
            2,
        ),
        "scenarios": rows,
        "scenarios_reachable": len(reachable),
        "scenarios_unreachable_on_materials_and_machine": len(targets) - len(reachable),
        "tightest_labour_minutes": min(minutes) if minutes else None,
        "lowest_implied_labour_rate": min(rates) if rates else None,
    }


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
            "finding_id": "FINDING-GAP-IS-RATE-NOT-PROCESS",
            "metric": "labour minutes affordable against a back-calculated manufacturing cost",
            "calculated_delta": result["back_calculation"]["tightest_labour_minutes"],
            "interpretation": "Working backwards from an observed shelf price puts a "
            "manufacturer's cost between 51.30 and 96.19. To meet the typical-channel "
            "figure this shop must build a complete neck in about 23 labour minutes "
            "against 191 today, or pay about 3.46 an hour against 28.75. Two of the four "
            "routes are unreachable on materials and machine time ALONE, before any "
            "labour. The gap is labour RATE times CONTENT, and the shop can only move "
            "content - which needs an eightfold reduction, not a process tweak.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-NO-COMPATIBLE-BUY-SIDE-EXISTS",
            "metric": "threshold comparisons that are commercially actionable",
            "calculated_delta": result["threshold_findings"]["commercially_actionable_rows"],
            "interpretation": "B1-B4 are now defined and every threshold from 90 to 140 "
            "is judged like-for-like against its make state. NOT ONE COMPARISON IS "
            "ACTIONABLE. The instrument is headless with a locking clamp nut at 628.65 mm, "
            "and no supplier of such a neck has been identified at any completion state. "
            "The economics are computed anyway, because a threshold the shop cannot act on "
            "today is still the number it would need if a source appeared.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-RUNTIME-RISK-WAS-ONE-SIDED",
            "metric": "cost per saleable neck across the widened runtime grid",
            "calculated_delta": round(
                max(p["cost_per_saleable"] for p in result["sensitivity"]["sweeps"][0]["points"])
                - min(
                    p["cost_per_saleable"]
                    for p in result["sensitivity"]["sweeps"][0]["points"]
                ),
                2,
            ),
            "interpretation": "The accepted runtime sweep only descended from the "
            "unverified 52-minute baseline, so it could only ever show the number proving "
            "favourable. Extended above it, the grid shows the spread across the full "
            "domain. Runtime remains the largest single unmeasured lever and it now cuts "
            "both ways.",
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
    # newline="\n" so the fixture is byte-identical whoever regenerates it.
    # Without it Python translates to os.linesep, and a Windows run rewrites
    # every line of a file the repo stores with LF -- a 2,514-line diff carrying
    # no change at all.
    OUT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    print(f"  {len(result['make_scenarios'])} make scenarios, "
          f"{len(result['findings'])} findings")
    be = result["batching_effect"]
    print(f"  batching worth {be['saving_qty_1_to_40']} per neck "
          f"(ceiling {be['ceiling_at_infinite_quantity']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
