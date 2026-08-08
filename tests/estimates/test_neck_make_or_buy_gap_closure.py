"""Tests for the neck make-or-buy gap closure.

Dev Order: NECK-MAKE-OR-BUY-GAP-CLOSURE-1

The accepted sprint (NECK-MAKE-OR-BUY-BATCH-COSTING-1) is the baseline here and
is not retested; tests/estimates/test_neck_make_or_buy.py covers it. What this
file pins is the five things that sprint left open:

    the records had no governed schema, so shape was unpoliced
    three of four completion states had no buy side at all
    the runtime sweep only ever descended from an unverified baseline
    runtime had no yield axis
    the retail back-calculation's separation from make-cost was a comment

The last of those is the one worth reading twice. The back-calculation is
allowed to carry retail and channel vocabulary because it infers a THIRD
party's manufacturing cost from their shelf price. The condition on that
exemption is that it must never feed the shop's own arithmetic, and a comment
saying so proves nothing — so it is demonstrated by perturbation instead.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from business.estimates.neck_costing import (
    BUY_STATES,
    BUY_TO_MAKE,
    COMPLETION_STATES,
    BuyCompletionState,
    RetainedShopOperation,
    YieldPolicy,
    assert_like_for_like,
    build_make_scenario,
    evaluate_threshold,
    union_sweep,
)

ROOT = Path(__file__).resolve().parents[2]
NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_make_or_buy_input_v1.json"
RESULT = NECK / "neck_make_or_buy_result_v1.json"
SCENARIO_SCHEMA = ROOT / "schemas" / "estimates" / "neck_make_or_buy_scenario_v1.schema.json"
RESULT_SCHEMA = ROOT / "schemas" / "estimates" / "neck_make_or_buy_result_v1.schema.json"
VALIDATOR = ROOT / "scripts" / "validate_neck_make_or_buy.py"
BUILDER = ROOT / "scripts" / "build_neck_make_or_buy.py"

# The commit this sprint branched from. Used to prove the accepted strategic
# back-calculation was not quietly edited while its neighbours were extended.
BASE_COMMIT = "a33c531"

LAB = 28.75

FORBIDDEN_COMMERCIAL = (
    "retail",
    "wholesale",
    "msrp",
    "margin",
    "markup",
    "overhead",
    "dealer",
    "list_price",
)


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def spec() -> dict:
    return load(INPUT)


@pytest.fixture(scope="module")
def result() -> dict:
    return load(RESULT)


@pytest.fixture(scope="module")
def builder():
    mod = importlib.util.spec_from_file_location("neck_builder", BUILDER)
    assert mod is not None and mod.loader is not None
    module = importlib.util.module_from_spec(mod)
    mod.loader.exec_module(module)
    return module


# ------------------------------------------------------------------- schemas


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [(INPUT, SCENARIO_SCHEMA), (RESULT, RESULT_SCHEMA)],
    ids=["scenario", "result"],
)
def test_governed_schemas_are_well_formed_and_the_fixtures_satisfy_them(fixture, schema):
    """Recomputation proves the arithmetic; the schema proves the shape.

    A section can recompute perfectly and still carry a field nobody agreed to,
    which is exactly how a commercial value would get in.
    """
    doc = load(schema)
    jsonschema.Draft202012Validator.check_schema(doc)
    jsonschema.validate(load(fixture), doc)


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [(INPUT, SCENARIO_SCHEMA), (RESULT, RESULT_SCHEMA)],
    ids=["scenario", "result"],
)
def test_both_schemas_are_closed_against_unknown_fields(fixture, schema):
    """additionalProperties: false is the whole point; prove it bites."""
    doc = load(fixture)
    doc["smuggled_field"] = "anything at all"
    with pytest.raises(jsonschema.ValidationError, match="Additional properties"):
        jsonschema.validate(doc, load(schema))


@pytest.mark.parametrize("field", ["retail_price", "wholesale_price", "margin", "msrp"])
def test_new_artifacts_reject_commercial_fields(field):
    """The boundary the Dev Order set, enforced where it applies.

    It applies to the make-or-buy record. It does NOT apply to the separately
    classified back-calculation, which is the subject of the separation tests
    below rather than of a blanket ban.
    """
    doc = load(RESULT)
    doc["threshold_findings"][field] = 100.0
    with pytest.raises(jsonschema.ValidationError, match="Additional properties"):
        jsonschema.validate(doc, load(RESULT_SCHEMA))


def test_no_commercial_vocabulary_in_any_make_or_buy_section(spec, result):
    """Word-boundary matched, so a legitimate 'marginal' or machining margin passes.

    The back_calculation subtree is excluded because channel vocabulary is its
    method. Everything else must be commercially silent.
    """
    import re

    for doc in (spec, result):
        blob = json.dumps({k: v for k, v in doc.items() if k != "back_calculation"}).lower()
        for term in FORBIDDEN_COMMERCIAL:
            assert re.search(rf"\b{re.escape(term)}\b", blob) is None, term


# ------------------------------------------------------- back-calc separation


def test_perturbing_the_back_calculation_moves_no_make_or_buy_number(spec, builder):
    """The exemption's condition, proven rather than asserted.

    If any make-or-buy value moved when a retail figure changed, the strategic
    analysis would be feeding the operational model and the exemption would have
    to be withdrawn.
    """
    baseline = builder.build(spec)

    poisoned = copy.deepcopy(spec)
    bc = poisoned["back_calculation"]
    bc["anchor"]["retail_price"] = float(bc["anchor"]["retail_price"]) * 3 + 17
    for raw in bc["channel_scenarios"]:
        raw["retail_margin"] = 0.11
        raw["distributor_margin"] = 0.07
        raw["manufacturer_margin"] = 0.13
    for key in ("material_cost", "machine_minutes", "labour_minutes"):
        bc["shop_position"][key] = float(bc["shop_position"][key]) * 2 + 5
    after = builder.build(poisoned)

    for section in (
        "make_scenarios",
        "batching_effect",
        "buy_references",
        "buy_completion_states",
        "thresholds",
        "threshold_findings",
        "sensitivity",
    ):
        assert after[section] == baseline[section], section

    # And the perturbation must actually have done something, or the test above
    # is vacuous.
    assert after["back_calculation"] != baseline["back_calculation"]


def test_the_accepted_back_calculation_input_is_unchanged(spec):
    """It was accepted in ae20bf1 and this sprint may extend around it, not edit it."""
    rel = "fixtures/estimates/neck/neck_make_or_buy_input_v1.json"
    try:
        raw = subprocess.run(
            ["git", "show", f"{BASE_COMMIT}:{rel}"],
            capture_output=True, text=True, cwd=ROOT, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"{BASE_COMMIT} not resolvable in this checkout")

    accepted = json.loads(raw)["back_calculation"]
    assert spec["back_calculation"] == accepted, (
        "the strategic back-calculation differs from the accepted baseline"
    )


def test_the_accepted_back_calculation_findings_survive(result):
    """The bracket and the anchor are the sprint's headline result; keep them."""
    bc = result["back_calculation"]
    assert bc["anchor_retail_price"] == 197.31
    assert len(bc["scenarios"]) == 4
    assert bc["manufacturing_cost_low"] == 51.30
    assert bc["manufacturing_cost_high"] == 96.19
    assert bc["scenarios_unreachable_on_materials_and_machine"] == 2


# ----------------------------------------------------------- accepted values


def test_accepted_headline_costs_did_not_move(result):
    """The gap closure is additive. If these moved, it was not additive."""
    m4 = next(
        s for s in result["make_scenarios"]
        if s["construction"] == "SCARF_JOINT"
        and s["completion_state"] == "M4"
        and s["quantity"] == 20
    )
    assert m4["cost_per_saleable"] == 187.88
    assert result["batching_effect"]["saving_qty_1_to_40"] == 9.34
    assert result["batching_effect"]["ceiling_at_infinite_quantity"] == 9.58


def test_accepted_v2_baseline_fixtures_are_still_byte_identical():
    """LF-normalised, so the digest is the same on a CRLF checkout and a LF one."""
    expected = {
        "thin_skin_variant_a_input_v1.json": "75252f00d3637d2c",
        "thin_skin_variant_a_estimate_v1.json": "1c1ff3ff2eefdd07",
        "thin_skin_variant_b_input_v1.json": "913335de59c3b25f",
        "thin_skin_variant_b_estimate_v1.json": "223be312c3ced9cf",
    }
    for name, prefix in expected.items():
        path = ROOT / "fixtures" / "estimates" / "guitar" / name
        normalised = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(normalised).hexdigest()[:16] == prefix, name


# --------------------------------------------------------------- buy states


def test_all_four_buy_states_exist_exactly_once(result):
    ids = [b["state_id"] for b in result["buy_completion_states"]]
    assert ids == list(BUY_STATES)
    assert len(set(ids)) == 4


def test_every_buy_state_maps_to_its_own_make_state(result):
    for b in result["buy_completion_states"]:
        assert b["make_equivalent"] == BUY_TO_MAKE[b["state_id"]]


@pytest.mark.parametrize(
    ("make_state", "buy_state"),
    [("M1", "B4"), ("M4", "B1"), ("M2", "B3"), ("M3", "B2")],
)
def test_cross_state_comparison_is_refused(make_state, buy_state):
    """Comparing a machined shaft with a finished neck is the error the taxonomy exists for."""
    with pytest.raises(ValueError, match="may not be compared"):
        assert_like_for_like(make_state, buy_state)


@pytest.mark.parametrize("state", COMPLETION_STATES)
def test_like_for_like_pairing_is_accepted(state):
    assert_like_for_like(state, next(b for b, m in BUY_TO_MAKE.items() if m == state))


def test_unknown_states_are_refused():
    with pytest.raises(ValueError, match="unknown make state"):
        assert_like_for_like("M9", "B1")
    with pytest.raises(ValueError, match="unknown buy state"):
        assert_like_for_like("M1", "B9")


def test_no_buy_state_claims_a_compatible_supplier(result):
    """The instrument is headless with a clamp nut; every reference has a headstock.

    This is the honesty requirement. The economics may be computed, but the
    record must not imply a source exists.
    """
    for b in result["buy_completion_states"]:
        assert b["compatible_supplier_identified"] is False
        assert b["purchase_price_status"] == "unresolved"


def _buy_state(**kw) -> BuyCompletionState:
    base = dict(
        state_id="B1",
        description="test",
        make_equivalent="M1",
        completion_requirements=("machined",),
        retained_shop_operations=(RetainedShopOperation("receiving", 5.0, "unpack"),),
        inspection_requirements=("heel fit",),
        compatibility_requirements=("headless",),
    )
    base.update(kw)
    return BuyCompletionState(**base)  # type: ignore[arg-type]


def test_a_buy_state_cannot_be_built_with_the_wrong_make_equivalent():
    with pytest.raises(ValueError, match="must map to M1"):
        _buy_state(make_equivalent="M3")


@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("completion_requirements", "completion requirements"),
        ("inspection_requirements", "inspection requirements"),
        ("compatibility_requirements", "compatibility requirements"),
    ],
)
def test_every_requirement_list_must_be_stated(field, match):
    """All three, not two.

    compatibility_requirements was the one list that could be left empty, which
    is backwards: whether a purchased neck FITS this instrument is the binding
    constraint on the entire question — no supplier of a headless clamp-nut neck
    at 628.65 mm has been found at any completion state — and it outranks cost.
    An empty list there would let a buy state look fully specified while saying
    nothing about the only thing that currently decides the answer.
    """
    with pytest.raises(ValueError, match=match):
        _buy_state(**{field: ()})


def test_a_claimed_supplier_must_arrive_with_a_price():
    """Otherwise 'we can buy this' enters the record with nothing behind it."""
    with pytest.raises(ValueError, match="identified compatible supplier"):
        _buy_state(compatible_supplier_identified=True, purchase_price_status="unresolved")
    ok = _buy_state(compatible_supplier_identified=True, purchase_price_status="quoted")
    assert ok.compatible_supplier_identified is True


def test_retained_shop_work_is_charged_at_the_loaded_rate():
    state = _buy_state(
        retained_shop_operations=(
            RetainedShopOperation("receiving", 5.0, "unpack"),
            RetainedShopOperation("verification", 10.0, "measure"),
            RetainedShopOperation("corrective fitting", 15.0, "fit"),
        )
    )
    assert state.retained_minutes == 30.0
    assert state.retained_completion_cost(LAB) == pytest.approx(30 / 60 * LAB, abs=0.01)


def test_negative_retained_minutes_are_refused():
    with pytest.raises(ValueError, match="non-negative"):
        RetainedShopOperation("impossible", -1.0, "no")


def test_buy_side_retains_inspection_and_fit_verification_at_every_state(result):
    """A delivered price is not a delivered cost, at any completion state."""
    for b in result["buy_completion_states"]:
        ops = " ".join(o["operation"] for o in b["retained_shop_operations"]).lower()
        assert "inspection" in ops
        assert any("verification" in o["operation"].lower() for o in b["retained_shop_operations"])
        assert b["retained_minutes"] > 0
        assert b["retained_completion_cost"] > 0


# ---------------------------------------------------------------- thresholds


def test_the_four_governed_thresholds_are_evaluated(spec, result):
    assert spec["purchase_price_thresholds"]["values"] == [90, 100, 120, 140]
    prices = {c["threshold_price"] for c in result["threshold_findings"]["comparisons"]}
    assert prices == {90.0, 100.0, 120.0, 140.0}


def test_every_state_is_judged_against_every_threshold(result):
    comparisons = result["threshold_findings"]["comparisons"]
    assert len(comparisons) == 16
    pairs = {(c["make_state"], c["buy_state"], c["threshold_price"]) for c in comparisons}
    assert len(pairs) == 16, "duplicate comparison"
    for c in comparisons:
        assert BUY_TO_MAKE[c["buy_state"]] == c["make_state"]


def test_ceiling_is_make_cost_less_retained_buy_side_work(result):
    """The Dev Order's break-even equation, checked against the artifact."""
    for c in result["threshold_findings"]["comparisons"]:
        expected = round(
            c["make_cost_per_saleable"] - c["retained_buy_side_completion_cost"], 2
        )
        assert c["maximum_compatible_delivered_purchase_price"] == pytest.approx(
            expected, abs=0.02
        )


def test_the_ceiling_is_reported_in_exactly_one_place(result):
    """A make scenario may not state a purchase ceiling.

    It cannot know one. The ceiling is make cost LESS the shop work the matching
    buy state retains, so it needs both sides. This record carried
    `max_competitive_purchase_price` on all 40 make scenarios, returning the
    bare in-house cost under the name of the number this sprint exists to
    report: $187.88 where the answer is $171.11, and at M2 $100.37 where the
    answer is $86.47 — wrong by four times the entire $3.53 margin that row has.

    Nothing recomputed it and nothing compared it, so it would have stayed
    correct-looking indefinitely. The name is what makes it dangerous, so the
    test bans the shape rather than the spelling.
    """
    ceiling_like = re.compile(r"competitive|ceiling|max.*price|price.*max")
    for s in result["make_scenarios"]:
        assert not [k for k in s if ceiling_like.search(k)], s["completion_state"]

    ceilings = result["threshold_findings"]["ceilings"]
    assert len(ceilings) == 4
    for c in ceilings:
        assert c["maximum_compatible_delivered_purchase_price"] < c["make_cost_per_saleable"]


def test_the_result_schema_now_refuses_a_revived_ceiling_field(result):
    """Removing the field is not enough if the contract still admits it."""
    doc = copy.deepcopy(result)
    doc["make_scenarios"][0]["max_competitive_purchase_price"] = 187.88
    with pytest.raises(jsonschema.ValidationError, match="Additional properties"):
        jsonschema.validate(doc, load(RESULT_SCHEMA))


def test_a_make_scenario_cannot_compute_a_ceiling_on_its_own():
    """The removal is structural, not cosmetic: there is no such attribute."""
    scenario = build_make_scenario(
        completion_state="M4",
        quantity=20,
        operations=(),
        materials=(),
        yield_policy=YieldPolicy(rate=0.9, basis="test"),
        loaded_labour_rate=LAB,
        machine_rate=12.0,
    )
    assert not hasattr(scenario, "max_competitive_purchase_price")


def test_difference_and_verdict_agree_on_every_row(result):
    """A silently flipped sign would read as a perfectly valid answer."""
    for c in result["threshold_findings"]["comparisons"]:
        diff = round(
            c["threshold_price"] - c["maximum_compatible_delivered_purchase_price"], 2
        )
        assert c["difference_versus_threshold"] == pytest.approx(diff, abs=0.02)
        if abs(diff) < 0.005:
            assert c["result"] == "break_even"
        elif diff > 0:
            assert c["result"] == "make_lower_cost"
        else:
            assert c["result"] == "buy_lower_cost"


def _scenario(state: str = "M4", **kw):
    ops = kw.pop("operations", None)
    from business.estimates.neck_costing import NeckMaterial, NeckOperation

    ops = ops or (
        NeckOperation("OP-4100", "cnc", setup_minutes=18, touch_minutes=12,
                      machine_minutes=52, setup_per_batch=True, from_state="M1"),
        NeckOperation("OP-4200", "fretwork", touch_minutes=78, from_state="M3"),
    )
    return build_make_scenario(
        completion_state=state, quantity=20, operations=ops,
        materials=(NeckMaterial("MAT", "stock", 60.0, "M1"),),
        yield_policy=YieldPolicy(0.9, "18 of 20"),
        loaded_labour_rate=LAB, machine_rate=28.97, **kw,
    )


def test_equality_is_reported_as_break_even():
    """Exactly on the ceiling is neither make nor buy, and must say so."""
    scenario = _scenario("M4")
    state = _buy_state(state_id="B4", make_equivalent="M4")
    ceiling = scenario.cost_per_saleable - state.retained_completion_cost(LAB)
    c = evaluate_threshold(
        make_scenario=scenario, buy_state=state,
        threshold_price=round(ceiling, 2), loaded_labour_rate=LAB,
    )
    assert c.result == "break_even"
    assert c.difference_versus_threshold == pytest.approx(0.0, abs=0.01)


def test_a_price_above_the_ceiling_favours_making():
    scenario = _scenario("M4")
    state = _buy_state(state_id="B4", make_equivalent="M4")
    ceiling = scenario.cost_per_saleable - state.retained_completion_cost(LAB)
    assert evaluate_threshold(
        make_scenario=scenario, buy_state=state,
        threshold_price=ceiling + 25, loaded_labour_rate=LAB,
    ).result == "make_lower_cost"


def test_a_price_below_the_ceiling_favours_buying():
    scenario = _scenario("M4")
    state = _buy_state(state_id="B4", make_equivalent="M4")
    ceiling = scenario.cost_per_saleable - state.retained_completion_cost(LAB)
    assert evaluate_threshold(
        make_scenario=scenario, buy_state=state,
        threshold_price=max(ceiling - 25, 1.0), loaded_labour_rate=LAB,
    ).result == "buy_lower_cost"


def test_evaluating_a_threshold_across_states_is_refused():
    with pytest.raises(ValueError, match="may not be compared"):
        evaluate_threshold(
            make_scenario=_scenario("M1"),
            buy_state=_buy_state(state_id="B4", make_equivalent="M4"),
            threshold_price=100.0, loaded_labour_rate=LAB,
        )


def test_a_nonpositive_threshold_is_refused():
    for bad in (0.0, -50.0):
        with pytest.raises(ValueError, match="threshold price"):
            evaluate_threshold(
                make_scenario=_scenario("M1"), buy_state=_buy_state(),
                threshold_price=bad, loaded_labour_rate=LAB,
            )


def test_no_row_is_commercially_actionable_and_each_says_why(result):
    """The finding that matters most: the arithmetic is sound and unusable."""
    tf = result["threshold_findings"]
    assert tf["commercially_actionable_rows"] == 0
    for c in tf["comparisons"]:
        assert c["commercially_actionable"] is False
        assert c["reason"] == "no compatible purchased-neck source identified"
        assert "not a supplier offer" in c["compatibility_caveat"].lower()


def test_an_identified_supplier_makes_a_row_actionable():
    """Proves the caveat tracks the supply position rather than being hardcoded."""
    c = evaluate_threshold(
        make_scenario=_scenario("M1"),
        buy_state=_buy_state(
            compatible_supplier_identified=True, purchase_price_status="quoted"
        ),
        threshold_price=100.0, loaded_labour_rate=LAB,
    )
    assert c.commercially_actionable is True
    assert c.reason == "a compatible purchased-neck source is identified"


def test_thresholds_are_recorded_as_analytical_not_as_offers(spec):
    assert spec["purchase_price_thresholds"]["basis"] == "analytical"
    assert "NOT SUPPLIER OFFERS" in spec["purchase_price_thresholds"]["note"]


# ------------------------------------------------------------------- sweeps


def test_union_sweep_is_sorted_deduplicated_and_lossless():
    out = union_sweep([52, 45, 40, 30, 20], [20, 30, 40, 52, 60, 75, 90])
    assert out == [20, 30, 40, 45, 52, 60, 75, 90]
    assert out == sorted(set(out))


def test_union_sweep_preserves_every_accepted_point():
    """The whole safety property of the union: nothing accepted is dropped."""
    existing = [78, 65, 55, 45, 35, 25]
    out = union_sweep(existing, [20, 30, 40, 50, 60, 78, 90])
    assert set(existing) <= set(out)


def test_accepted_sweep_points_all_survive(spec):
    accepted_runtime = {52, 45, 40, 30, 20}
    accepted_fretwork = {78, 65, 55, 45, 35, 25}
    assert accepted_runtime <= set(spec["sensitivity"]["machine_minutes"])
    assert accepted_fretwork <= set(spec["sensitivity"]["fretwork_minutes"])


def test_the_runtime_sweep_now_brackets_the_unverified_baseline(spec):
    """The gap this closes.

    52 machine minutes is carried from the V2 baseline and has never been
    measured. A grid that only descends from it can only ever show that
    assumption proving favourable.
    """
    grid = spec["sensitivity"]["machine_minutes"]
    baseline = spec["sensitivity"]["baseline_machine_minutes"]
    assert baseline == 52
    assert baseline in grid
    assert [v for v in grid if v > baseline], "grid has no downside case"
    assert [v for v in grid if v < baseline]
    assert {60, 75, 90} <= set(grid)


def test_the_fretwork_sweep_carries_the_expanded_points(spec):
    grid = spec["sensitivity"]["fretwork_minutes"]
    assert spec["sensitivity"]["baseline_fretwork_minutes"] == 78
    assert {20, 30, 40, 50, 60, 78, 90} <= set(grid)
    assert grid == sorted(set(grid))


def test_runtime_sensitivity_is_monotonic_and_labelled(result):
    sweep = result["sensitivity"]["sweeps"][0]
    costs = [p["cost_per_saleable"] for p in sweep["points"]]
    assert costs == sorted(costs)
    baseline = sweep["baseline_value"]
    for p in sweep["points"]:
        mm = p["machine_minutes_per_neck"]
        expected = "baseline" if mm == baseline else "better" if mm < baseline else "worse"
        assert p["relative_to_baseline"] == expected
    assert any(p["relative_to_baseline"] == "worse" for p in sweep["points"])


def test_a_worse_runtime_costs_more_than_the_baseline(result):
    """The case the accepted sweep structurally could not express."""
    points = {
        p["machine_minutes_per_neck"]: p["cost_per_saleable"]
        for p in result["sensitivity"]["sweeps"][0]["points"]
    }
    assert points[90] > points[52] > points[20]


# ----------------------------------------------------------------- matrices


def test_both_required_matrices_exist(result):
    ids = {m["matrix_id"] for m in result["sensitivity"]["matrices"]}
    assert "FRETWORK_X_YIELD_QTY20_M4" in ids
    assert "RUNTIME_X_YIELD_QTY20_M4" in ids


def test_the_accepted_matrix_was_not_deleted(result):
    """Valid analysis is added to, not replaced."""
    ids = {m["matrix_id"] for m in result["sensitivity"]["matrices"]}
    assert "FRETBOARD_X_FRETWORK_QTY20_M4" in ids


def test_every_matrix_axis_is_unique_and_sorted(result):
    for m in result["sensitivity"]["matrices"]:
        for name in ("row_axis", "column_axis"):
            values = m[name]["values"]
            assert len(set(values)) == len(values), f"{m['matrix_id']} {name}"
            assert values == sorted(values), f"{m['matrix_id']} {name}"
            assert m[name]["name"]


def test_every_matrix_is_complete_and_fully_specified(result):
    for m in result["sensitivity"]["matrices"]:
        rows, cols = m["row_axis"]["values"], m["column_axis"]["values"]
        assert len(m["cells"]) == len(rows) * len(cols), m["matrix_id"]
        coords = {(c["row"], c["column"]) for c in m["cells"]}
        assert coords == {(r, c) for r in rows for c in cols}, m["matrix_id"]
        assert m["completion_state"] == "M4"
        assert m["quantity"] == 20
        assert m["fixed_assumptions"]


def test_a_matrix_never_both_sweeps_and_fixes_a_variable(result):
    """A variable on an axis and in fixed_assumptions makes the cell ambiguous."""
    for m in result["sensitivity"]["matrices"]:
        axes = {m["row_axis"]["name"], m["column_axis"]["name"]}
        assert not (axes & set(m["fixed_assumptions"])), m["matrix_id"]


def test_yield_worsens_cost_along_every_matrix_row(result):
    """Losing necks makes the survivors dearer, at every runtime and fretwork time."""
    for mid in ("FRETWORK_X_YIELD_QTY20_M4", "RUNTIME_X_YIELD_QTY20_M4"):
        m = next(x for x in result["sensitivity"]["matrices"] if x["matrix_id"] == mid)
        assert m["row_axis"]["name"] == "yield_rate"
        by_col: dict[float, list[tuple[float, float]]] = {}
        for c in m["cells"]:
            by_col.setdefault(c["column"], []).append((c["row"], c["cost_per_saleable"]))
        for column, pairs in by_col.items():
            costs = [cost for _, cost in sorted(pairs)]
            assert costs == sorted(costs, reverse=True), f"{mid} column {column}"


def test_fretwork_does_not_affect_m1_or_m2():
    """Fretwork lives at M3. If it moved M1, the state taxonomy would be broken."""
    from dataclasses import replace

    from business.estimates.neck_costing import NeckMaterial, NeckOperation

    ops = (
        NeckOperation("OP-4100", "cnc", setup_minutes=18, touch_minutes=12,
                      machine_minutes=52, setup_per_batch=True, from_state="M1"),
        NeckOperation("OP-4150", "board", touch_minutes=10, from_state="M2"),
        NeckOperation("OP-4200", "fretwork", touch_minutes=78, from_state="M3"),
    )
    slower = tuple(
        replace(o, touch_minutes=200.0) if o.operation_id == "OP-4200" else o for o in ops
    )
    mats = (NeckMaterial("MAT", "stock", 60.0, "M1"),)
    kw = dict(
        quantity=20, materials=mats, yield_policy=YieldPolicy(0.9, "x"),
        loaded_labour_rate=LAB, machine_rate=28.97,
    )
    for state in ("M1", "M2"):
        before = build_make_scenario(completion_state=state, operations=ops, **kw)  # type: ignore[arg-type]
        after = build_make_scenario(completion_state=state, operations=slower, **kw)  # type: ignore[arg-type]
        assert before.cost_per_saleable == after.cost_per_saleable, state
    m3_before = build_make_scenario(completion_state="M3", operations=ops, **kw)  # type: ignore[arg-type]
    m3_after = build_make_scenario(completion_state="M3", operations=slower, **kw)  # type: ignore[arg-type]
    assert m3_after.cost_per_saleable > m3_before.cost_per_saleable


# ---------------------------------------------------------------- validator


def _run_validator() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR)], capture_output=True, text=True, cwd=ROOT
    )


def test_validator_passes_on_the_committed_fixtures():
    proc = _run_validator()
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "matrix cell",
            lambda d: d["sensitivity"]["matrices"][2]["cells"][3].update(
                {"cost_per_saleable": 1.23}
            ),
        ),
        (
            "break-even ceiling",
            lambda d: d["threshold_findings"]["comparisons"][0].update(
                {"maximum_compatible_delivered_purchase_price": 999.0}
            ),
        ),
        (
            "verdict",
            lambda d: d["threshold_findings"]["comparisons"][0].update({"result": "break_even"}),
        ),
        (
            "actionability",
            lambda d: d["threshold_findings"]["comparisons"][0].update(
                {"commercially_actionable": True}
            ),
        ),
        (
            "retained minutes",
            lambda d: d["buy_completion_states"][2].update({"retained_minutes": 1.0}),
        ),
        ("a missing buy state", lambda d: d["buy_completion_states"].pop()),
        (
            "cross-state mapping",
            lambda d: d["buy_completion_states"][1].update({"make_equivalent": "M4"}),
        ),
        ("an unknown field", lambda d: d.update({"retail_price_each": 250.0})),
        ("an authorized decision", lambda d: d.update({"decision_authorized": True})),
    ],
)
def test_validator_rejects_a_tampered_result(label, mutate):
    """Every governed value must be recomputed, not trusted."""
    original = RESULT.read_text(encoding="utf-8")
    doc = json.loads(original)
    mutate(doc)
    RESULT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        proc = _run_validator()
        assert proc.returncode != 0, f"tampering with {label} went undetected"
    finally:
        RESULT.write_text(original, encoding="utf-8")


def test_validator_rejects_a_runtime_grid_that_lost_its_upside():
    """Tampering the INPUT and regenerating, so only the policy check can catch it."""
    original = INPUT.read_text(encoding="utf-8")
    original_result = RESULT.read_text(encoding="utf-8")
    doc = json.loads(original)
    doc["sensitivity"]["machine_minutes"] = [20, 30, 40, 45, 52]
    INPUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        gen = subprocess.run(
            [sys.executable, str(BUILDER)], capture_output=True, text=True, cwd=ROOT
        )
        assert gen.returncode == 0, gen.stderr
        proc = _run_validator()
        assert proc.returncode != 0
        assert "never exceeds" in proc.stdout
    finally:
        INPUT.write_text(original, encoding="utf-8")
        RESULT.write_text(original_result, encoding="utf-8")


def test_the_report_quotes_the_committed_fixture(result):
    """A doc that drifts from the fixture it summarises is the same defect as a
    fixture that does not recompute.

    Every headline figure in the accepted sprint's report was wrong at least once
    while it was being written, which is why this guard exists there too.
    """
    report = (
        ROOT / "docs" / "estimates" / "NECK_MAKE_OR_BUY_GAP_CLOSURE_V1.md"
    ).read_text(encoding="utf-8")

    for c in result["threshold_findings"]["ceilings"]:
        assert f"{c['make_cost_per_saleable']:.2f}" in report, c["make_state"]
        assert f"{c['maximum_compatible_delivered_purchase_price']:.2f}" in report, c["buy_state"]
    for b in result["buy_completion_states"]:
        assert f"{b['retained_completion_cost']:.2f}" in report, b["state_id"]
    for p in result["sensitivity"]["sweeps"][0]["points"]:
        assert f"{p['cost_per_saleable']:.2f}" in report, p["machine_minutes_per_neck"]
    for m in result["sensitivity"]["matrices"]:
        assert m["matrix_id"] in report
        assert str(len(m["cells"])) in report

    be = result["batching_effect"]
    assert f"{be['saving_qty_1_to_40']:.2f}" in report
    assert f"{be['ceiling_at_infinite_quantity']:.2f}" in report

    # The disclaimer the Dev Order requires. Whitespace-normalised because it is
    # a wrapped blockquote in the prose and must be allowed to stay readable.
    flat = " ".join(report.replace(">", " ").split())
    assert (
        "This analysis is a draft engineering cost model. It does not authorize neck "
        "production, supplier selection, purchasing, or commercial pricing." in flat
    )


def test_ci_runs_the_validator():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python scripts/validate_neck_make_or_buy.py" in ci


# --------------------------------------------------------------- governance


def test_nothing_in_the_new_sections_authorises_anything(result):
    assert result["decision_authorized"] is False
    assert result["status"] == "draft"
    for b in result["buy_completion_states"]:
        assert b["confidence"] == "draft"
        assert b["source"] == "engineering_estimate"
    for f in result["findings"]:
        assert f["decision_authorized"] is False
        assert f["confidence"] == "draft"


def test_no_supplier_is_selected_and_no_purchase_order_exists(spec, result):
    blob = (json.dumps(spec) + json.dumps(result)).lower()
    for term in ("purchase_order", "po_number", "supplier_selected", "vendor_id", "order_id"):
        assert term not in blob, term
