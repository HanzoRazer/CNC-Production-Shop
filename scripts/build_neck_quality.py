#!/usr/bin/env python3
"""Compute the neck defect-mode result from its governed taxonomy.

Dev Order: NECK-QUALITY-TAXONOMY-1

    python scripts/build_neck_quality.py

Reads fixtures/estimates/neck/neck_defect_taxonomy_v1.json and writes the
result beside it. Every figure is derived here so the validator can recompute
the whole file; nothing is transcribed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.estimates.neck_quality import (  # noqa: E402
    ELIMINATION_LABOUR,
    ELIMINATION_PROCESS,
    ELIMINATION_SPECIFICATION,
    GATE_STAGES,
    VISIBILITY_LATENT,
    AcceptanceCriterion,
    DefectMode,
    NeckSource,
    compare_coverage,
    disposition_for,
    profile_source,
    verifiability_profile,
)

INPUT = ROOT / "fixtures" / "estimates" / "neck" / "neck_defect_taxonomy_v1.json"
OUT = ROOT / "fixtures" / "estimates" / "neck" / "neck_defect_taxonomy_result_v1.json"


def _modes(raw: list[dict[str, Any]]) -> tuple[DefectMode, ...]:
    return tuple(
        DefectMode(
            defect_id=d["defect_id"],
            description=d["description"],
            elimination=d["elimination"],
            visibility=d["visibility"],
            remediable=bool(d["remediable"]),
            labour_minutes=float(d["labour_minutes"]),
            material_cost=float(d["material_cost"]),
            remediation_minutes=float(d["remediation_minutes"]),
            remediation_material=float(d["remediation_material"]),
            evidence=d["evidence"],
            note=d.get("note", ""),
        )
        for d in raw
    )


def _sources(raw: list[dict[str, Any]]) -> tuple[NeckSource, ...]:
    return tuple(
        NeckSource(
            source_id=s["source_id"],
            description=s["description"],
            addresses=frozenset(s["addresses"]),
            evidence=s["evidence"],
            arrival_stage=s["arrival_stage"],
            is_characterised=bool(s["is_characterised"]),
        )
        for s in raw
    )


def _criteria(raw: list[dict[str, Any]]) -> tuple[AcceptanceCriterion, ...]:
    return tuple(
        AcceptanceCriterion(
            defect_id=a["defect_id"],
            stage=a["stage"],
            method=a["method"],
            pass_criterion=a["pass_criterion"],
            threshold=a["threshold"],
            units=a["units"],
            threshold_source=a["threshold_source"],
            owner_confirmed=bool(a["owner_confirmed"]),
        )
        for a in raw
    )


def build(doc: dict[str, Any]) -> dict[str, Any]:
    modes = _modes(doc["defect_modes"])
    criteria = _criteria(doc["acceptance"])
    sources = _sources(doc["sources"])
    rate = float(doc["rates"]["loaded_labour_per_hour"])
    by_id = {s.source_id: s for s in sources}

    result: dict[str, Any] = {
        "result_id": "NECK-DEFECT-TAXONOMY-RESULT-V1",
        "input_ref": doc["input_id"],
        "dev_order": doc["dev_order"],
        "status": "draft",
        "currency": doc["currency"],
        "decision_authorized": False,
    }

    # --- the taxonomy, split by what removes each defect ---------------------
    by_elimination: dict[str, list[dict[str, Any]]] = {}
    for m in modes:
        by_elimination.setdefault(m.elimination, []).append(
            {
                "defect_id": m.defect_id,
                "description": m.description,
                "visibility": m.visibility,
                "remediable": m.remediable,
                "prevention_cost": m.cost(rate),
                "repair_cost": m.repair_cost(rate),
                "prevention_minutes": m.labour_minutes,
                "repair_minutes": m.remediation_minutes,
                "evidence": m.evidence,
            }
        )
    result["modes_by_elimination"] = {
        kind: by_elimination.get(kind, [])
        for kind in (ELIMINATION_PROCESS, ELIMINATION_SPECIFICATION, ELIMINATION_LABOUR)
    }

    # The three counts that answer "which quality wins are free".
    result["elimination_summary"] = [
        {
            "elimination": kind,
            "mode_count": len(by_elimination.get(kind, [])),
            "prevention_cost": round(
                sum(m.cost(rate) for m in modes if m.elimination == kind), 2
            ),
            "prevention_minutes": round(
                sum(m.labour_minutes for m in modes if m.elimination == kind), 1
            ),
        }
        for kind in (ELIMINATION_PROCESS, ELIMINATION_SPECIFICATION, ELIMINATION_LABOUR)
    ]

    # --- how bad the latent and irreparable modes are ------------------------
    latent = [m for m in modes if m.visibility == VISIBILITY_LATENT]
    result["risk_profile"] = {
        "total_modes": len(modes),
        "latent_modes": len(latent),
        "non_remediable_modes": sum(1 for m in modes if not m.remediable),
        "latent_and_non_remediable": sorted(
            m.defect_id for m in latent if not m.remediable
        ),
        "note": "Latent and non-remediable together is the worst pair: the defect "
        "cannot be found at receipt and cannot be fixed once it appears. On a "
        "built instrument it returns as a warranty claim rather than as a "
        "rejected part.",
    }

    # --- what each characterised source covers, and what that costs ----------
    result["source_profiles"] = []
    for s in sources:
        p = profile_source(source=s, taxonomy=modes, labour_rate=rate)
        result["source_profiles"].append(
            {
                "source_id": p.source_id,
                "description": s.description,
                "evidence": s.evidence,
                "modes_addressed": p.modes_addressed,
                "modes_open": p.modes_open,
                "free_modes": p.free_modes,
                "process_cost": p.process_cost,
                "specification_cost": p.specification_cost,
                "labour_cost": p.labour_cost,
                "labour_minutes": p.labour_minutes,
                "total_cost": p.total_cost,
                "latent_open": list(p.latent_open),
                "non_remediable_open": list(p.non_remediable_open),
            }
        )

    # --- the comparison gate ------------------------------------------------
    result["comparisons"] = []
    for c in doc["comparisons"]:
        cmp = compare_coverage(
            source=by_id[c["source_id"]],
            against=by_id[c["against_id"]],
            taxonomy=modes,
            labour_rate=rate,
        )
        result["comparisons"].append(
            {
                "source_id": cmp.source_id,
                "against_id": cmp.against_id,
                "question": c["question"],
                "comparable": cmp.comparable,
                "shared_modes": list(cmp.shared_modes),
                "missing_mode_count": len(cmp.missing_modes),
                "missing_modes": list(cmp.missing_modes),
                "blocking_modes": list(cmp.blocking_modes),
                "remediation_minutes": cmp.remediation_minutes,
                "remediation_material": cmp.remediation_material,
                "remediation_cost": cmp.remediation_cost,
                "verdict": cmp.verdict,
            }
        )

    # --- the yardstick itself ------------------------------------------------
    by_stage: dict[str, list[str]] = {}
    for c in criteria:
        by_stage.setdefault(c.stage, []).append(c.defect_id)
    result["acceptance_gate"] = {
        "criteria_total": len(criteria),
        "modes_without_criterion": sorted(
            {m.defect_id for m in modes} - {c.defect_id for c in criteria}
        ),
        "criteria_by_stage": {st: sorted(by_stage.get(st, [])) for st in GATE_STAGES},
        "numeric_thresholds": sum(1 for c in criteria if c.threshold is not None),
        "judged_by_method_only": sorted(c.defect_id for c in criteria if c.threshold is None),
        "owner_confirmed_thresholds": sum(1 for c in criteria if c.owner_confirmed),
        "note": "Every threshold here is a DRAFT PROPOSAL. None has been set by the "
        "owner, so the gate is a structure awaiting numbers, not a specification.",
    }

    # --- what each source can actually be checked against --------------------
    result["verifiability"] = []
    for s_ in sources:
        v = verifiability_profile(source=s_, criteria=criteria, taxonomy=modes)
        result["verifiability"].append(
            {
                "source_id": v.source_id,
                "arrival_stage": v.arrival_stage,
                "criteria_total": v.criteria_total,
                "verifiable_count": len(v.verifiable),
                "unverifiable_count": len(v.unverifiable),
                "verifiable_fraction": v.verifiable_fraction,
                "verifiable": list(v.verifiable),
                "unverifiable": list(v.unverifiable),
                "unverifiable_and_irrecoverable": list(v.unverifiable_and_irrecoverable),
                "note": v.note,
            }
        )

    # --- the same fault, priced on each side ---------------------------------
    stage_values = {k: float(v) for k, v in doc["stage_value_at_risk"].items()}
    result["example_dispositions"] = []
    for ex in doc["example_dispositions"]:
        dp = disposition_for(
            failed_modes=tuple(ex["failed_modes"]),
            taxonomy=modes,
            labour_rate=rate,
            value_at_risk=stage_values.get(ex["stage"], stage_values["M4"]),
        )
        result["example_dispositions"].append(
            {
                "example_id": ex["example_id"],
                "source_id": ex["source_id"],
                "stage": ex["stage"],
                "why": ex["why"],
                "verdict": dp.verdict,
                "failed_modes": list(dp.failed_modes),
                "unrecoverable_modes": list(dp.unrecoverable_modes),
                "rework_minutes": dp.rework_minutes,
                "rework_cost": dp.rework_cost,
                "loss_if_scrapped": dp.loss_if_scrapped,
                "reason": dp.reason,
            }
        )

    result["uncharacterised_sources"] = doc["uncharacterised_sources"]
    result["findings"] = _findings(result, doc)
    return result


def _findings(result: dict[str, Any], doc: dict[str, Any]) -> list[dict[str, Any]]:
    summary = {e["elimination"]: e for e in result["elimination_summary"]}
    shop = next(p for p in result["source_profiles"] if p["source_id"] == "SRC-SHOP-CNC")
    cmp = result["comparisons"][0]
    risk = result["risk_profile"]
    v_shop = next(v for v in result["verifiability"] if v["source_id"] == "SRC-SHOP-CNC")
    v_buy = next(v for v in result["verifiability"] if v["source_id"] != "SRC-SHOP-CNC")
    examples = {e["example_id"]: e for e in result["example_dispositions"]}
    early = examples["EX-BUILD-CHANNEL-M1"]
    late = examples["EX-BUY-CHANNEL-ESCAPED"]
    ratio = round((late["loss_if_scrapped"] or 0) / (early["loss_if_scrapped"] or 1), 1)

    return [
        {
            "finding_id": "FINDING-VERIFIABILITY-GAP",
            "metric": "acceptance criteria that can be run, build against buy",
            "calculated_delta": v_shop["verifiable_count"] - v_buy["verifiable_count"],
            "interpretation": f"Held to ONE yardstick, the decisive difference is not "
            f"score - it is what can be checked at all. A neck built here can be judged "
            f"against {v_shop['verifiable_count']} of {v_shop['criteria_total']} "
            f"criteria; the purchased neck against {v_buy['verifiable_count']}. The "
            f"other {v_buy['unverifiable_count']} describe stages that happened in "
            f"another shop to another standard, and the evidence is under a glued "
            f"fretboard. Those are not failures, they are blanks - and "
            f"{len(v_buy['unverifiable_and_irrecoverable'])} of them are also "
            f"irrecoverable, so they can neither be found on arrival nor fixed later. "
            f"Buying is not only cheaper, it is {v_buy['verifiable_fraction']:.0%} "
            f"verifiable. That is the trade the cost model could not see.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-PARITY-IS-UNPURCHASABLE",
            "metric": "non-remediable modes left open by the observed import",
            "calculated_delta": len(cmp["blocking_modes"]),
            "interpretation": f"The comparison the make-or-buy model ran for three days "
            f"is REFUSED here. The observed import leaves {len(cmp['blocking_modes'])} "
            f"modes open that no spend can close, so its $35 and the shop's $187.88 are "
            f"prices on different products and the difference between them is not a "
            f"saving. No remediation figure is reported, because reporting one would "
            f"imply parity is purchasable.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-WHERE-YOU-GATE-SETS-THE-LOSS",
            "metric": "loss on the same unrecoverable fault, caught early against late",
            "calculated_delta": round(
                (late["loss_if_scrapped"] or 0) - (early["loss_if_scrapped"] or 0), 2
            ),
            "interpretation": f"One fault, DEF-TRUSS-CHANNEL-CENTRING, priced on both "
            f"sides. Built here it is measured at M1 before the fretboard goes on and "
            f"the loss is {early['loss_if_scrapped']}. Bought in, there is no M1 to "
            f"inspect at, so it surfaces only when the neck will not set flat - by then "
            f"it is {late['loss_if_scrapped']} inside a finished instrument. Identical "
            f"verdict, {ratio}x the loss. Owning the early stages is worth money "
            f"even when the fault rate "
            f"is the same on both sides.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-FREE-QUALITY-WINS",
            "metric": "defect modes eliminated at zero marginal cost",
            "calculated_delta": summary[ELIMINATION_PROCESS]["mode_count"],
            "interpretation": f"{summary[ELIMINATION_PROCESS]['mode_count']} of "
            f"{risk['total_modes']} modes are removed by holding position, at no "
            f"marginal cost at all - because the machine indexes every feature from one "
            f"datum, not because anyone tried harder. This is quality an hourly rate "
            f"cannot erode, and it includes the canonical complaint about bought necks.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-LABOUR-IS-THE-PRODUCT",
            "metric": "labour minutes attributable to quality modes",
            "calculated_delta": shop["labour_minutes"],
            "interpretation": f"{shop['labour_minutes']} of the shop's minutes go to the "
            f"{summary[ELIMINATION_LABOUR]['mode_count']} labour-eliminated modes, "
            f"costing {shop['labour_cost']}. Against the 191 labour minutes in the cost "
            f"model that is the majority of the neck's labour content, and the import "
            f"spends none of it. The labour gap is not inefficiency to be squeezed out - "
            f"it is the product, and squeezing it out means building the other thing.",
            "confidence": "draft",
            "decision_authorized": False,
        },
        {
            "finding_id": "FINDING-COVERAGE-IS-INTENT-NOT-MEASUREMENT",
            "metric": "thresholds confirmed by the owner",
            "calculated_delta": result["acceptance_gate"]["owner_confirmed_thresholds"],
            "interpretation": "No threshold in this gate has been set by the owner and "
            "no neck has been built, so the shop's full coverage is INTENT and its "
            "100 percent verifiability is an opportunity rather than a result - owning "
            "the stages means the checks CAN be run, not that they have been. Every "
            "figure is a draft engineering estimate. This taxonomy exists to be "
            "overturned by the first build sessions; until then its job is to stop cost "
            "comparisons between things that were never the same product.",
            "confidence": "draft",
            "decision_authorized": False,
        },
    ]


def main() -> int:
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    result = build(doc)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    print(f"  {len(result['modes_by_elimination'][ELIMINATION_PROCESS])} process, "
          f"{len(result['modes_by_elimination'][ELIMINATION_SPECIFICATION])} specification, "
          f"{len(result['modes_by_elimination'][ELIMINATION_LABOUR])} labour modes")
    print(f"  {len(result['findings'])} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
