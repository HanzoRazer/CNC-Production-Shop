#!/usr/bin/env python3
"""Validate the neck make-or-buy input and result.

Dev Order: NECK-MAKE-OR-BUY-BATCH-COSTING-1

    python scripts/validate_neck_make_or_buy.py

Recomputes the whole result from the input and compares. A stored figure that
cannot be reproduced is the failure this guards against, because every number
here feeds a make-or-buy decision and none of it is measured.

Also asserts the boundaries the Dev Order set: no commercial pricing, draft
status throughout, decisions never authorised, batch setup divided by SALEABLE
units, and the accepted V2 estimate fixtures untouched.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.estimates.neck_costing import BUY_STATES, BUY_TO_MAKE  # noqa: E402
from scripts.build_neck_make_or_buy import build  # noqa: E402

NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_make_or_buy_input_v1.json"
RESULT = NECK / "neck_make_or_buy_result_v1.json"

SCHEMAS = ROOT / "schemas" / "estimates"
SCENARIO_SCHEMA = SCHEMAS / "neck_make_or_buy_scenario_v1.schema.json"
RESULT_SCHEMA = SCHEMAS / "neck_make_or_buy_result_v1.schema.json"

# Sections of either artifact that carry the make-or-buy analysis. The strategic
# back-calculation is deliberately NOT in this set: it is separately classified,
# and the separation is proven by perturbation in check 11 rather than asserted.
MAKE_OR_BUY_SECTIONS = (
    "make_scenarios",
    "batching_effect",
    "buy_references",
    "buy_completion_states",
    "thresholds",
    "threshold_findings",
    "sensitivity",
)

# The accepted V2 baseline this sprint is forbidden to disturb.
# Digests are taken over LF-normalised bytes, so they are the same on a CRLF
# checkout and a LF one. Hashing raw bytes made this validator pass on Windows
# and fail on every Linux CI runner.
IMMUTABLE = {
    "thin_skin_variant_a_input_v1.json": "75252f00d3637d2c",
    "thin_skin_variant_a_estimate_v1.json": "1c1ff3ff2eefdd07",
    "thin_skin_variant_b_input_v1.json": "913335de59c3b25f",
    "thin_skin_variant_b_estimate_v1.json": "223be312c3ced9cf",
}

FORBIDDEN = (
    "retail",
    "wholesale",
    "msrp",
    "margin",
    "markup",
    "overhead",
    "dealer",
    "list_price",
)


def _fail(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(f"FAIL {message}")


def _schema_errors(data: dict[str, Any], schema_path: Path, label: str) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        return [f"FAIL {label} schema $.{loc}: {exc.message}"]
    return []


def main() -> int:
    errors: list[str] = []
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    stored = json.loads(RESULT.read_text(encoding="utf-8"))

    # 0. Both artifacts must satisfy their governed contract. Recomputation
    #    proves the arithmetic; the schema proves the SHAPE, and a section that
    #    recomputes correctly can still carry a field nobody agreed to.
    errors += _schema_errors(doc, SCENARIO_SCHEMA, "scenario")
    errors += _schema_errors(stored, RESULT_SCHEMA, "result")

    # 1. The whole result must be reproducible from the input.
    recomputed = build(doc)
    if stored != recomputed:
        differing = sorted(
            k for k in set(stored) | set(recomputed) if stored.get(k) != recomputed.get(k)
        )
        errors.append(f"FAIL result does not recompute from input; sections differ: {differing}")

    # 2. The V2 baseline must be untouched.
    for name, prefix in IMMUTABLE.items():
        path = ROOT / "fixtures" / "estimates" / "guitar" / name
        actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]
        _fail(errors, actual == prefix, f"{name} changed: {actual} != {prefix}")

    # 3. Nothing commercial may appear anywhere. Matched on WORD BOUNDARIES:
    #    a substring test flags "marginal" and would flag a machining margin
    #    too, which are both legitimate and neither of which is a price.
    #
    #    The back_calculation section is EXEMPT, and the exemption is narrow.
    #    That section reads a third party's observed shelf price backwards to
    #    infer THEIR manufacturing cost; channel vocabulary is the method there,
    #    not a leak. What the original rule forbids is this model pricing the
    #    shop's own output, so that is asserted separately and specifically in
    #    3b rather than being dropped along with the exemption.
    scan_doc = {k: v for k, v in doc.items() if k != "back_calculation"}
    scan_res = {k: v for k, v in stored.items() if k != "back_calculation"}
    blob = json.dumps(scan_doc).lower() + json.dumps(scan_res).lower()
    for term in FORBIDDEN:
        pattern = r"\b" + re.escape(term) + r"\b"
        hit = re.search(pattern, blob)
        _fail(errors, hit is None, f"commercial term {term!r} present")

    # 3b. The exempt section may describe another manufacturer's channel. It may
    #     NOT price this shop's neck, and it may not quietly become a price list.
    bc_blob = (
        json.dumps(doc["back_calculation"]).lower()
        + json.dumps(stored["back_calculation"]).lower()
    )
    for term in ("our_price", "sell_price", "selling_price", "quote", "asking"):
        _fail(
            errors,
            re.search(r"\b" + re.escape(term) + r"\b", bc_blob) is None,
            f"back_calculation prices this shop's output ({term!r}); it may only "
            f"infer a third party's cost",
        )
    _fail(
        errors,
        doc["back_calculation"]["anchor"]["is_comparable_product"] is False,
        "the anchor must declare itself NOT a comparable product: it is a "
        "conventional headstock neck and this instrument is headless",
    )

    # 4. Governance: draft throughout, no decision authorised.
    _fail(errors, doc["status"] == "draft", "input status is not draft")
    _fail(errors, stored["status"] == "draft", "result status is not draft")
    _fail(errors, stored["decision_authorized"] is False, "result authorises a decision")
    for f in stored["findings"]:
        _fail(
            errors,
            f["decision_authorized"] is False,
            f"finding {f['finding_id']} authorises a decision",
        )
        _fail(errors, f["confidence"] == "draft", f"finding {f['finding_id']} is not draft")

    # 5. Batch setup divides by saleable units, not units started. At a yield
    #    below 1.0 the surviving necks must carry the whole setup.
    yr = doc["yield_policy"]["rate"]
    if yr < 1.0:
        q20 = next(
            s
            for s in stored["make_scenarios"]
            if s["quantity"] == 20
            and s["completion_state"] == "M4"
            and s["construction"] == "SCARF_JOINT"
        )
        _fail(
            errors,
            q20["saleable"] == round(20 * yr, 4),
            f"saleable {q20['saleable']} is not quantity x yield",
        )
        _fail(
            errors,
            q20["yield_loss_per_saleable"] > 0,
            "yield below 1.0 produced no yield loss",
        )
        _fail(
            errors,
            q20["cost_per_saleable"] > q20["cost_per_started"],
            "cost per saleable must exceed cost per started when necks are rejected",
        )

    # 6. Elapsed wait and equipment occupancy must NEVER be labour. The first
    #    version of this model had no fields for them, so clamp and cure time
    #    were charged at the loaded rate. Recompute labour from the input and
    #    assert the stored figure matches setup + touch alone.
    lab_rate = float(doc["rates"]["loaded_labour_per_hour"])
    yr_rate = float(doc["yield_policy"]["rate"])
    order = ["M1", "M2", "M3", "M4"]
    for s in stored["make_scenarios"]:
        included = order[: order.index(s["completion_state"]) + 1]
        saleable = s["quantity"] * yr_rate
        expected = 0.0
        wait = 0.0
        for o in doc["operations"]:
            if o["from_state"] not in included:
                continue
            setup = (
                o["setup_minutes"] / saleable
                if o["setup_per_batch"]
                else o["setup_minutes"] * s["quantity"] / saleable
            )
            expected += setup + o["touch_minutes"] * s["quantity"] / saleable
            wait += o.get("elapsed_wait_minutes", 0.0) * s["quantity"] / saleable
        _fail(
            errors,
            abs(s["labour_minutes"] - expected) < 0.02,
            f"{s['construction']}/{s['completion_state']}/q{s['quantity']}: labour "
            f"{s['labour_minutes']} != setup + touch {round(expected, 2)}",
        )
        _fail(
            errors,
            abs(s["elapsed_wait_minutes"] - wait) < 0.02,
            f"{s['construction']}/{s['completion_state']}/q{s['quantity']}: elapsed wait drifted",
        )
        labour_cost = s["setup_cost"] + s["touch_cost"]
        _fail(
            errors,
            abs(labour_cost - s["labour_minutes"] / 60 * lab_rate) < 0.05,
            f"{s['completion_state']}/q{s['quantity']}: labour cost is not labour minutes x rate",
        )

    # The arithmetic check above is necessary but NOT sufficient: it stays true
    # when the input itself misclassifies, because the result faithfully
    # reproduces a wrong input. Proven by reintroducing the original bug, which
    # it did not catch. What actually guards the distinction is naming the
    # operations that are cure-bound by definition and requiring them to say so.
    cure_bound = {
        "OP-4150": "glue must cure under clamps",
        "OP-4500": "finish must cure between and after coats",
    }
    for op_id, why in cure_bound.items():
        op = next((o for o in doc["operations"] if o["operation_id"] == op_id), None)
        if op is None:
            errors.append(f"FAIL {op_id} is missing; it is cure-bound and required")
            continue
        _fail(
            errors,
            op.get("elapsed_wait_minutes", 0) > 0,
            f"{op_id} declares no elapsed wait, but {why}. Setting it to zero "
            f"folds cure time back into operator labour, which is the defect "
            f"this check exists to prevent.",
        )

    m4 = next(
        s
        for s in stored["make_scenarios"]
        if s["completion_state"] == "M4" and s["quantity"] == 20
    )
    _fail(errors, m4["elapsed_wait_minutes"] > 0, "a complete neck records no cure time at all")
    _fail(errors, m4["occupancy_cost"] > 0, "finishing occupies no equipment")

    # 7. The back-calculation must recompute, and must stay a BRACKET. A single
    #    margin assumption would read as precision the method cannot support.
    bc_in, bc_out = doc["back_calculation"], stored["back_calculation"]
    retail = float(bc_in["anchor"]["retail_price"])
    shop = bc_in["shop_position"]
    for raw in bc_in["channel_scenarios"]:
        row = next(r for r in bc_out["scenarios"] if r["scenario_id"] == raw["scenario_id"])
        expected = (
            retail
            * (1 - raw["retail_margin"])
            * (1 - raw["distributor_margin"])
            * (1 - raw["manufacturer_margin"])
        )
        _fail(
            errors,
            abs(row["manufacturing_cost"] - round(expected, 2)) < 0.02,
            f"{raw['scenario_id']}: manufacturing cost {row['manufacturing_cost']} "
            f"!= {round(expected, 2)}",
        )
        machine_cost = float(shop["machine_minutes"]) / 60 * float(doc["rates"]["machine_per_hour"])
        budget = expected - float(shop["material_cost"]) - machine_cost
        _fail(
            errors,
            row["reachable"] is (budget > 0),
            f"{raw['scenario_id']}: reachable flag disagrees with the labour budget",
        )
        if budget <= 0:
            _fail(
                errors,
                row["labour_minutes_affordable"] is None
                and row["implied_labour_rate"] is None,
                f"{raw['scenario_id']}: unreachable target still reports a labour figure",
            )

    _fail(
        errors,
        len(bc_out["scenarios"]) >= 3,
        "back-calculation must span several channel routes; one margin is false precision",
    )
    _fail(
        errors,
        bc_out["manufacturing_cost_high"] > bc_out["manufacturing_cost_low"],
        "back-calculation collapsed to a point instead of a bracket",
    )
    _fail(
        errors,
        "rule of thumb" in bc_in["margin_provenance"]["note"].lower(),
        "margin provenance must say the margins are assumptions, not observations",
    )

    # 8. Draft additions must be flagged, because they have never been measured.
    drafts = [o["operation_id"] for o in doc["operations"] if o["is_draft_addition"]]
    _fail(errors, set(drafts) == {"OP-4150", "OP-4500"}, f"unexpected draft additions: {drafts}")

    # 9. Unknown buy-side fields must be reported, not silently defaulted.
    for ref in stored["buy_references"]:
        if not ref["is_fully_landed"]:
            _fail(
                errors,
                ref["landed_cost_per_good"] is None,
                f"{ref['reference_id']} reports a landed cost from incomplete inputs",
            )
            _fail(
                errors,
                len(ref["unknown_fields"]) > 0,
                f"{ref['reference_id']} is not fully landed but lists no unknown fields",
            )

    # 10. Only one operation may carry batch setup; the finding depends on it.
    batch_ops = [o["operation_id"] for o in doc["operations"] if o["setup_per_batch"]]
    _fail(errors, batch_ops == ["OP-4100"], f"unexpected batch-setup operations: {batch_ops}")

    # 11. SEPARATION, PROVEN RATHER THAN ASSERTED.
    #     The strategic back-calculation is allowed to carry retail and channel
    #     vocabulary because it infers a third party's cost from their shelf
    #     price. The condition attached to that exemption is that it must never
    #     feed the shop's own make-cost arithmetic. Asserting that in a comment
    #     is worthless, so it is demonstrated: perturb every number in the
    #     section and require that not one make-or-buy value moves.
    poisoned = copy.deepcopy(doc)
    bc = poisoned["back_calculation"]
    bc["anchor"]["retail_price"] = float(bc["anchor"]["retail_price"]) * 3 + 17
    bc["anchor"]["list_price_before_discount"] = 9999.0
    for raw in bc["channel_scenarios"]:
        raw["retail_margin"] = 0.11
        raw["distributor_margin"] = 0.07
        raw["manufacturer_margin"] = 0.13
    for key in ("material_cost", "machine_minutes", "labour_minutes"):
        bc["shop_position"][key] = float(bc["shop_position"][key]) * 2 + 5

    after = build(poisoned)
    for section in MAKE_OR_BUY_SECTIONS:
        _fail(
            errors,
            after[section] == stored[section],
            f"back_calculation leaks into make-cost arithmetic: perturbing it changed "
            f"{section!r}. The strategic analysis is separately classified and may "
            f"inform judgement, but it may not be an input to a make-or-buy number.",
        )
    _fail(
        errors,
        after["back_calculation"] != stored["back_calculation"],
        "perturbing the back-calculation changed nothing in it either, so the "
        "separation test above proves nothing; the test itself is broken",
    )

    # 12. B1-B4 must be complete, mapped like-for-like, and honest about supply.
    states = stored["buy_completion_states"]
    ids = [b["state_id"] for b in states]
    _fail(errors, ids == list(BUY_STATES), f"buy states are {ids}, expected {list(BUY_STATES)}")
    _fail(errors, len(set(ids)) == len(ids), "duplicate buy completion state")
    for b in states:
        _fail(
            errors,
            BUY_TO_MAKE.get(b["state_id"]) == b["make_equivalent"],
            f"{b['state_id']} maps to {b['make_equivalent']}, not "
            f"{BUY_TO_MAKE.get(b['state_id'])}: a buy state may only be compared with "
            f"the make state of the same completion",
        )
        # No supplier of a headless clamp-nut neck has been identified at any
        # state. If that ever changes it must arrive with a price, not as a bare
        # claim, which is what the paired assertion enforces.
        if not b["compatible_supplier_identified"]:
            _fail(
                errors,
                b["purchase_price_status"] == "unresolved",
                f"{b['state_id']} has no compatible supplier but claims a resolved price",
            )
        _fail(
            errors,
            b["retained_shop_operations"] and b["retained_minutes"] > 0,
            f"{b['state_id']} retains no shop work at all; receiving inspection and "
            f"fit verification survive every purchase",
        )
        recomputed_minutes = sum(o["minutes"] for o in b["retained_shop_operations"])
        _fail(
            errors,
            abs(b["retained_minutes"] - recomputed_minutes) < 0.01,
            f"{b['state_id']} retained minutes {b['retained_minutes']} != "
            f"{recomputed_minutes}",
        )
        _fail(
            errors,
            abs(b["retained_completion_cost"] - recomputed_minutes / 60 * lab_rate) < 0.01,
            f"{b['state_id']} retained cost is not retained minutes x the loaded rate",
        )
    # Every buy reference in the record is a conventional headstock neck, so none
    # may be attached to a buy state as though it were a substitute.
    _fail(
        errors,
        all(not b["compatible_supplier_identified"] for b in states),
        "a buy state claims an identified compatible supplier. The instrument is "
        "headless with a locking clamp nut at 628.65 mm and every reference on "
        "record is a conventional headstock neck.",
    )

    # 12b. The purchase ceiling is reported in exactly ONE place. It is make cost
    #      LESS the retained buy-side work, so a make scenario cannot state one:
    #      it does not know which buy state it is being compared with. This
    #      record carried `max_competitive_purchase_price` on every make scenario,
    #      returning the bare in-house cost under the name of the very number the
    #      sprint exists to report — $12.94 to $16.77 too generous, and at M2,
    #      where the whole margin is $3.53, wrong by four times the answer.
    #      The schema now refuses that exact key; this catches a revival under
    #      any other spelling.
    ceiling_like = re.compile(r"competitive|ceiling|max.*price|price.*max")
    for s in stored["make_scenarios"]:
        offenders = sorted(k for k in s if ceiling_like.search(k))
        _fail(
            errors,
            not offenders,
            f"make_scenarios states a purchase ceiling {offenders}. A ceiling needs "
            f"both sides of the comparison and belongs in threshold_findings.ceilings "
            f"as maximum_compatible_delivered_purchase_price.",
        )

    # 13. Thresholds must recompute, and the sign convention must hold.
    tf = stored["threshold_findings"]
    retained_by_state = {b["state_id"]: b["retained_completion_cost"] for b in states}
    make_by_state = {
        s["completion_state"]: s["cost_per_saleable"]
        for s in stored["make_scenarios"]
        if s["construction"] == tf["basis"]["construction"]
        and s["quantity"] == tf["basis"]["quantity"]
    }
    expected_prices = [float(v) for v in doc["purchase_price_thresholds"]["values"]]
    seen_pairs: set[tuple[str, str, float]] = set()
    for c in tf["comparisons"]:
        # Not named `key`: check 11 above binds that to a str, and reusing it here
        # made this membership test compare a str against a set of tuples. It
        # happened to work by rebinding order, but a duplicate check that mypy
        # reads as never-true is one edit away from silently passing everything.
        row_key = (c["make_state"], c["buy_state"], c["threshold_price"])
        _fail(errors, row_key not in seen_pairs, f"duplicate threshold comparison {row_key}")
        seen_pairs.add(row_key)
        _fail(
            errors,
            BUY_TO_MAKE[c["buy_state"]] == c["make_state"],
            f"cross-state comparison {c['make_state']} vs {c['buy_state']}",
        )
        _fail(
            errors,
            c["threshold_price"] in expected_prices,
            f"threshold {c['threshold_price']} is not in the governed set {expected_prices}",
        )
        make = make_by_state[c["make_state"]]
        retained = retained_by_state[c["buy_state"]]
        ceiling = round(make - retained, 2)
        _fail(
            errors,
            abs(c["maximum_compatible_delivered_purchase_price"] - ceiling) < 0.02,
            f"{c['make_state']}/{c['buy_state']}@{c['threshold_price']}: ceiling "
            f"{c['maximum_compatible_delivered_purchase_price']} != {ceiling}",
        )
        diff = round(c["threshold_price"] - ceiling, 2)
        _fail(
            errors,
            abs(c["difference_versus_threshold"] - diff) < 0.02,
            f"{c['make_state']}/{c['buy_state']}@{c['threshold_price']}: difference "
            f"{c['difference_versus_threshold']} != {diff}",
        )
        if abs(diff) < 0.005:
            expected_verdict = "break_even"
        else:
            expected_verdict = "make_lower_cost" if diff > 0 else "buy_lower_cost"
        _fail(
            errors,
            c["result"] == expected_verdict,
            f"{c['make_state']}@{c['threshold_price']}: verdict {c['result']!r} "
            f"disagrees with a difference of {diff}",
        )
        # The arithmetic landing on "make is cheaper" must never be reported as
        # something the shop can act on while no compatible source exists.
        supplier_exists = next(
            b["compatible_supplier_identified"] for b in states if b["state_id"] == c["buy_state"]
        )
        _fail(
            errors,
            c["commercially_actionable"] is supplier_exists,
            f"{c['make_state']}@{c['threshold_price']}: reported actionable="
            f"{c['commercially_actionable']} while compatible supplier="
            f"{supplier_exists}. A threshold is not an offer.",
        )
        if not c["commercially_actionable"]:
            _fail(
                errors,
                c["reason"] == "no compatible purchased-neck source identified",
                f"{c['make_state']}@{c['threshold_price']}: inactionable row gives no reason",
            )
    _fail(
        errors,
        len(tf["comparisons"]) == len(BUY_STATES) * len(expected_prices),
        f"expected {len(BUY_STATES) * len(expected_prices)} comparisons, "
        f"got {len(tf['comparisons'])}",
    )
    _fail(
        errors,
        tf["commercially_actionable_rows"]
        == sum(1 for c in tf["comparisons"] if c["commercially_actionable"]),
        "actionable row count disagrees with the rows",
    )

    # 14. Matrices must be well-formed and must cover the two required pairs.
    matrices = {m["matrix_id"]: m for m in stored["sensitivity"]["matrices"]}
    for required in ("FRETWORK_X_YIELD_QTY20_M4", "RUNTIME_X_YIELD_QTY20_M4"):
        _fail(errors, required in matrices, f"required matrix {required} is missing")
    for mid, m in matrices.items():
        for axis_name in ("row_axis", "column_axis"):
            axis = m[axis_name]
            values = axis["values"]
            _fail(
                errors,
                len(set(values)) == len(values),
                f"{mid} {axis_name} has duplicate values, so two cells claim one coordinate",
            )
            _fail(
                errors,
                values == sorted(values),
                f"{mid} {axis_name} is not sorted ascending",
            )
        rows, cols = m["row_axis"]["values"], m["column_axis"]["values"]
        _fail(
            errors,
            len(m["cells"]) == len(rows) * len(cols),
            f"{mid} has {len(m['cells'])} cells for a {len(rows)}x{len(cols)} grid",
        )
        coords = {(c["row"], c["column"]) for c in m["cells"]}
        _fail(
            errors,
            coords == {(r, c) for r in rows for c in cols},
            f"{mid} cell coordinates do not cover the axes exactly",
        )
        _fail(errors, m["quantity"] == 20, f"{mid} is not at quantity 20")
        _fail(
            errors,
            bool(m["fixed_assumptions"]),
            f"{mid} records no fixed assumptions, so its cells cannot be recomputed",
        )
        axis_names = {m["row_axis"]["name"], m["column_axis"]["name"]}
        _fail(
            errors,
            not (axis_names & set(m["fixed_assumptions"])),
            f"{mid} both sweeps and fixes {axis_names & set(m['fixed_assumptions'])}",
        )

    # 15. The runtime grid must bracket the baseline on BOTH sides. It previously
    #     only descended from 52 unverified minutes, which let the model show
    #     that number proving favourable and never proving costly.
    sweep = next(s for s in stored["sensitivity"]["sweeps"] if s["sweep_id"].startswith("MACHINE"))
    values = sweep["axis"]["values"]
    baseline = sweep["baseline_value"]
    _fail(errors, baseline in values, f"runtime baseline {baseline} is not on its own axis")
    _fail(
        errors,
        any(v > baseline for v in values),
        f"runtime sweep never exceeds the unverified {baseline}-minute baseline, so it "
        f"can only show that assumption proving favourable",
    )
    _fail(errors, any(v < baseline for v in values), "runtime sweep never falls below baseline")
    costs = [p["cost_per_saleable"] for p in sweep["points"]]
    _fail(errors, costs == sorted(costs), "runtime sensitivity is not monotonic in runtime")
    for point in sweep["points"]:
        mm = point["machine_minutes_per_neck"]
        expected_rel = (
            "baseline" if mm == baseline else "better" if mm < baseline else "worse"
        )
        _fail(
            errors,
            point["relative_to_baseline"] == expected_rel,
            f"runtime {mm} is labelled {point['relative_to_baseline']!r}, expected "
            f"{expected_rel!r}",
        )

    if errors:
        for e in errors:
            print(e)
        return 1

    be = stored["batching_effect"]
    print(f"PASS {INPUT.relative_to(ROOT).as_posix()}")
    print(f"PASS {RESULT.relative_to(ROOT).as_posix()}")
    print(f"  {len(stored['make_scenarios'])} make scenarios recomputed")
    print(f"  V2 baseline hashes unchanged ({len(IMMUTABLE)} fixtures)")
    print(f"  batching worth {be['saving_qty_1_to_40']} per neck, ceiling "
          f"{be['ceiling_at_infinite_quantity']}")
    print("  both artifacts validate against their governed schemas")
    print(f"  {len(stored['buy_completion_states'])} buy states, all mapped like-for-like, "
          f"none claiming a compatible supplier")
    print(f"  {len(stored['threshold_findings']['comparisons'])} threshold comparisons "
          f"recomputed, {stored['threshold_findings']['commercially_actionable_rows']} "
          f"commercially actionable")
    print(f"  {len(stored['sensitivity']['matrices'])} matrices, axes unique and sorted; "
          f"runtime grid brackets the {sweep['baseline_value']}-minute baseline")
    print("  back_calculation perturbed: no make-or-buy value moved")
    print("PASS recomputation, immutability, governance, separation, and yield allocation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
