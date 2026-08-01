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

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_neck_make_or_buy import build  # noqa: E402

NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_make_or_buy_input_v1.json"
RESULT = NECK / "neck_make_or_buy_result_v1.json"

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


def main() -> int:
    errors: list[str] = []
    doc = json.loads(INPUT.read_text(encoding="utf-8"))
    stored = json.loads(RESULT.read_text(encoding="utf-8"))

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
    print("PASS recomputation, immutability, governance, and yield allocation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
