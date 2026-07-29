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
IMMUTABLE = {
    "thin_skin_variant_a_input_v1.json": "0adf1d90b304ada8",
    "thin_skin_variant_a_estimate_v1.json": "a7f8ff63331d3eef",
    "thin_skin_variant_b_input_v1.json": "1d53aa725d0180ea",
    "thin_skin_variant_b_estimate_v1.json": "78bfafd58439aa93",
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
        actual = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        _fail(errors, actual == prefix, f"{name} changed: {actual} != {prefix}")

    # 3. Nothing commercial may appear anywhere. Matched on WORD BOUNDARIES:
    #    a substring test flags "marginal" and would flag a machining margin
    #    too, which are both legitimate and neither of which is a price.
    blob = json.dumps(doc).lower() + json.dumps(stored).lower()
    for term in FORBIDDEN:
        pattern = r"\b" + re.escape(term) + r"\b"
        hit = re.search(pattern, blob)
        _fail(errors, hit is None, f"commercial term {term!r} present")

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

    # 6. Draft additions must be flagged, because they have never been measured.
    drafts = [o["operation_id"] for o in doc["operations"] if o["is_draft_addition"]]
    _fail(errors, set(drafts) == {"OP-4150", "OP-4500"}, f"unexpected draft additions: {drafts}")

    # 7. Unknown buy-side fields must be reported, not silently defaulted.
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

    # 8. Only one operation may carry batch setup; the finding depends on it.
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
