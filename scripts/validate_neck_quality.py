#!/usr/bin/env python3
"""Validate the neck defect-mode taxonomy.

Dev Order: NECK-QUALITY-TAXONOMY-1

    python scripts/validate_neck_quality.py

Recomputes the result from the taxonomy and compares, then asserts the
distinctions the model exists to hold. The one that matters most is the refusal:
where a source leaves a non-remediable mode open, the result must decline to
report a remediation price rather than quote one. A number there would say
parity is purchasable when it is not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_neck_quality import build  # noqa: E402

NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_defect_taxonomy_v1.json"
RESULT = NECK / "neck_defect_taxonomy_result_v1.json"
COST_RESULT = NECK / "neck_make_or_buy_result_v1.json"


def _fail(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(f"FAIL {message}")


def main() -> int:
    errors: list[str] = []
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    stored = json.loads(RESULT.read_text(encoding="utf-8"))

    # 1. The whole result must be reproducible from the taxonomy.
    recomputed = build(doc)
    if stored != recomputed:
        differing = sorted(
            k for k in set(stored) | set(recomputed) if stored.get(k) != recomputed.get(k)
        )
        errors.append(f"FAIL result does not recompute from input; sections differ: {differing}")

    modes = {d["defect_id"]: d for d in doc["defect_modes"]}
    _fail(errors, len(modes) == len(doc["defect_modes"]), "duplicate defect_id in the taxonomy")

    # 2. PROCESS modes cost NOTHING to prevent. This is the central claim of the
    #    whole model - that machine precision is quality an hourly rate cannot
    #    erode - and if a cost ever creeps in here the claim is silently false.
    for d in doc["defect_modes"]:
        if d["elimination"] == "PROCESS":
            _fail(
                errors,
                d["labour_minutes"] == 0 and d["material_cost"] == 0,
                f"{d['defect_id']}: a PROCESS mode carries a prevention cost. Holding "
                f"position is not an extra operation; if it costs something it is not "
                f"a PROCESS mode.",
            )

    # 3. Prevention and repair must stay distinct. A defect that is free to
    #    prevent is rarely free to repair, and collapsing the two would make
    #    buy-then-fix look costless.
    for d in doc["defect_modes"]:
        if d["remediable"]:
            _fail(
                errors,
                d["remediation_minutes"] > 0 or d["remediation_material"] > 0,
                f"{d['defect_id']}: remediable at zero cost. Nothing is repaired free.",
            )
        else:
            _fail(
                errors,
                d["remediation_minutes"] == 0 and d["remediation_material"] == 0,
                f"{d['defect_id']}: irremediable but priced for repair; pick one",
            )

    # 4. THE REFUSAL. Where blocking modes exist the result must report no price.
    #    Proven necessary by the whole preceding sprint, which happily produced
    #    cost deltas between a basswood neck and a khaya one.
    for c in stored["comparisons"]:
        if c["blocking_modes"]:
            _fail(errors, c["comparable"] is False, f"{c['source_id']}: blockers but comparable")
            for field in ("remediation_cost", "remediation_minutes", "remediation_material"):
                _fail(
                    errors,
                    c[field] is None,
                    f"{c['source_id']}: reports {field} despite "
                    f"{len(c['blocking_modes'])} mode(s) no spend can close",
                )
            for m in c["blocking_modes"]:
                _fail(
                    errors,
                    modes[m]["remediable"] is False,
                    f"{c['source_id']}: {m} listed as blocking but is remediable",
                )
        else:
            _fail(
                errors,
                c["comparable"] is True,
                f"{c['source_id']}: no blockers but reported not comparable",
            )

    # 5. A source may only address modes that exist, and uncharacterised sources
    #    must NOT acquire coverage by appearing in both lists.
    characterised = {s["source_id"] for s in doc["sources"]}
    for s in doc["sources"]:
        unknown = sorted(set(s["addresses"]) - set(modes))
        _fail(errors, not unknown, f"{s['source_id']} addresses unknown modes: {unknown}")
        _fail(
            errors,
            len(set(s["addresses"])) == len(s["addresses"]),
            f"{s['source_id']} lists a mode twice",
        )
    for u in doc["uncharacterised_sources"]:
        _fail(
            errors,
            u["source_id"] not in characterised,
            f"{u['source_id']} is listed as uncharacterised AND characterised",
        )
        _fail(errors, bool(u.get("why")), f"{u['source_id']} gives no reason for being unknown")

    # 6. Nothing here is measured, and nothing may claim to be. The shop's own
    #    full-coverage row is intent; if it ever silently became evidence, the
    #    model would be asserting a build quality nobody has demonstrated.
    for s in doc["sources"]:
        _fail(
            errors,
            s["evidence"] in ("assumed", "owner_observed"),
            f"{s['source_id']} claims evidence class {s['evidence']!r}; no source has "
            f"been measured because no neck has been built",
        )
    shop = next(s for s in doc["sources"] if s["source_id"] == "SRC-SHOP-CNC")
    if len(shop["addresses"]) == len(modes):
        _fail(
            errors,
            shop["evidence"] == "assumed",
            "the shop is credited with FULL coverage; that must be recorded as "
            "assumed, never as observation",
        )
        _fail(
            errors,
            any(
                f["finding_id"] == "FINDING-COVERAGE-IS-INTENT-NOT-MEASUREMENT"
                for f in stored["findings"]
            ),
            "full shop coverage is claimed with no finding saying it is intent",
        )

    # 7. Cross-fixture: quality labour is a SUBSET of the neck's labour, not an
    #    addition to it. If these ever sum past the cost model's total, the two
    #    fixtures are double-counting the same minutes.
    if COST_RESULT.exists():
        cost = json.loads(COST_RESULT.read_text(encoding="utf-8"))
        m4 = next(
            s
            for s in cost["make_scenarios"]
            if s["completion_state"] == "M4"
            and s["quantity"] == 20
            and s["construction"] == "SCARF_JOINT"
        )
        quality_minutes = next(
            p["labour_minutes"]
            for p in stored["source_profiles"]
            if p["source_id"] == "SRC-SHOP-CNC"
        )
        _fail(
            errors,
            quality_minutes <= m4["labour_minutes"],
            f"quality labour {quality_minutes} min exceeds the cost model's total "
            f"{m4['labour_minutes']} min. These are the SAME minutes viewed by "
            f"purpose, not extra work, and a total above it means double counting.",
        )

    # 8. THE YARDSTICK. Both sides must face the same criteria, and a criterion
    #    that cannot be run must never be scored as a pass. Crediting a purchase
    #    with checks nobody performed is the assumption that made $35 look like
    #    a bargain against $187.88.
    criteria = {a["defect_id"]: a for a in doc["acceptance"]}
    stages = ["MATERIAL_RECEIPT", "M1", "M2", "M3", "M4", "IN_SERVICE"]
    for a in doc["acceptance"]:
        _fail(errors, a["defect_id"] in modes, f"criterion for unknown mode {a['defect_id']}")
        _fail(errors, a["stage"] in stages, f"{a['defect_id']}: bad stage {a['stage']!r}")
        _fail(errors, bool(a["method"].strip()), f"{a['defect_id']}: no method, so not a gate")
        _fail(errors, bool(a["pass_criterion"].strip()), f"{a['defect_id']}: nothing decides")
        _fail(
            errors,
            not (a["owner_confirmed"] and a["threshold_source"] == "proposed_draft"),
            f"{a['defect_id']}: owner_confirmed on a threshold that is still a draft "
            f"proposal. Confirmation needs a source.",
        )
    _fail(
        errors,
        stored["acceptance_gate"]["owner_confirmed_thresholds"]
        == sum(1 for a in doc["acceptance"] if a["owner_confirmed"]),
        "the reported count of owner-confirmed thresholds does not match the fixture",
    )
    _fail(
        errors,
        not stored["acceptance_gate"]["modes_without_criterion"],
        f"modes with no criterion cannot be judged on either side: "
        f"{stored['acceptance_gate']['modes_without_criterion']}",
    )

    # 9. Verifiability must be recomputed from arrival stage, and the asymmetry
    #    must survive. A source that arrives finished CANNOT be checked against
    #    criteria describing stages that already happened somewhere else.
    by_source = {s["source_id"]: s for s in doc["sources"]}
    for v in stored["verifiability"]:
        arrival = by_source[v["source_id"]]["arrival_stage"]
        _fail(errors, v["arrival_stage"] == arrival, f"{v['source_id']}: arrival stage drifted")
        expected = sorted(
            d for d, a in criteria.items() if stages.index(a["stage"]) >= stages.index(arrival)
        )
        _fail(
            errors,
            v["verifiable"] == expected,
            f"{v['source_id']}: runnable criteria do not follow from arriving at {arrival}",
        )
        _fail(
            errors,
            len(v["verifiable"]) + len(v["unverifiable"]) == v["criteria_total"],
            f"{v['source_id']}: criteria went missing between verifiable and not",
        )
        _fail(
            errors,
            not (set(v["verifiable"]) & set(v["unverifiable"])),
            f"{v['source_id']}: a criterion is counted as both runnable and buried",
        )
        for m in v["unverifiable_and_irrecoverable"]:
            _fail(
                errors,
                m in v["unverifiable"] and modes[m]["remediable"] is False,
                f"{v['source_id']}: {m} flagged unverifiable-and-irrecoverable wrongly",
            )
    shop_v = next(v for v in stored["verifiability"] if v["source_id"] == "SRC-SHOP-CNC")
    buy_v = next(v for v in stored["verifiability"] if v["source_id"] != "SRC-SHOP-CNC")
    _fail(
        errors,
        buy_v["verifiable_count"] < shop_v["verifiable_count"],
        "a neck bought finished cannot be verifiable against as many criteria as one "
        "built from the blank; if it is, the arrival stages are wrong",
    )

    # 10. Dispositions are DERIVED from remediability, never chosen, and an
    #     unrecoverable neck may not be dressed up as rework.
    for ex in stored["example_dispositions"]:
        failed = ex["failed_modes"]
        unrec = [m for m in failed if not modes[m]["remediable"]]
        expected = "ACCEPT" if not failed else ("SCRAP" if unrec else "REWORK")
        _fail(
            errors,
            ex["verdict"] == expected,
            f"{ex['example_id']}: verdict {ex['verdict']} but the failed modes imply "
            f"{expected}. Disposition follows remediability; it is not a choice.",
        )
        if expected == "SCRAP":
            _fail(
                errors,
                ex["rework_cost"] == 0 and ex["rework_minutes"] == 0,
                f"{ex['example_id']}: scrap carries a rework price, which buries an "
                f"unrecoverable loss in a rework budget",
            )

    # 11. Governance.
    _fail(errors, doc["status"] == "draft", "input status is not draft")
    _fail(errors, stored["status"] == "draft", "result status is not draft")
    _fail(errors, stored["decision_authorized"] is False, "result authorises a decision")
    for f in stored["findings"]:
        _fail(errors, f["confidence"] == "draft", f"finding {f['finding_id']} is not draft")
        _fail(
            errors,
            f["decision_authorized"] is False,
            f"finding {f['finding_id']} authorises a decision",
        )
    _fail(
        errors,
        "rebuild" in json.dumps(doc["provenance"]).lower(),
        "provenance must name what would trigger a rebuild",
    )

    if errors:
        for e in errors:
            print(e)
        return 1

    summary = {e["elimination"]: e for e in stored["elimination_summary"]}
    cmp = stored["comparisons"][0]
    print(f"PASS {INPUT.relative_to(ROOT).as_posix()}")
    print(f"PASS {RESULT.relative_to(ROOT).as_posix()}")
    print(f"  {len(modes)} defect modes recomputed")
    print(f"  {summary['PROCESS']['mode_count']} eliminated free by process, "
          f"{summary['SPECIFICATION']['mode_count']} by specification, "
          f"{summary['LABOUR']['mode_count']} by labour")
    print(f"  {cmp['source_id']} vs {cmp['against_id']}: comparable={cmp['comparable']}, "
          f"{len(cmp['blocking_modes'])} blocking")
    print("PASS recomputation, the free-process invariant, and the comparison refusal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
