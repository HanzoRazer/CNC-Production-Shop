"""Tests for the neck make-or-buy model.

Dev Order: NECK-MAKE-OR-BUY-BATCH-COSTING-1

The sprint exists because a router that holds twenty necks looked like it might
overturn a make-or-buy result. It does not, and the tests that matter are the
ones pinning WHY: only one operation carries setup, batch cost divides by
saleable units rather than units started, and the accepted V2 baseline does not
move when a new field is added to the time model.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from business.estimates.models_v2 import (
    SETUP_SCOPE_PER_BATCH,
    SETUP_SCOPE_PER_UNIT,
    OperationTimeModelV2,
)
from business.estimates.neck_costing import (
    COMPLETION_STATES,
    BuyReference,
    ChannelScenario,
    NeckMaterial,
    NeckOperation,
    YieldPolicy,
    back_calculate_target,
    build_make_scenario,
    fretwork_threshold,
)

ROOT = Path(__file__).resolve().parents[2]
NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_make_or_buy_input_v1.json"
RESULT = NECK / "neck_make_or_buy_result_v1.json"
VALIDATOR = ROOT / "scripts" / "validate_neck_make_or_buy.py"

LAB, MACH = 28.75, 28.97


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def result() -> dict:
    return load(RESULT)


@pytest.fixture(scope="module")
def spec() -> dict:
    return load(INPUT)


# ---------------------------------------------------------------- time model


def test_setup_scope_defaults_to_per_unit():
    """Every record written before this field existed meant per_unit."""
    assert OperationTimeModelV2().setup_scope == SETUP_SCOPE_PER_UNIT


def test_setup_scope_rejects_unknown_values():
    with pytest.raises(ValueError, match="setup_scope"):
        OperationTimeModelV2(setup_scope="per_moon_phase")


def test_the_two_scopes_agree_at_quantity_one():
    """This is what makes the change safe for the accepted baseline."""
    per_unit = OperationTimeModelV2(setup_minutes=18, operator_touch_minutes=12)
    per_batch = OperationTimeModelV2(
        setup_minutes=18, operator_touch_minutes=12, setup_scope=SETUP_SCOPE_PER_BATCH
    )
    assert per_unit.labor_minutes_for(1) == per_batch.labor_minutes_for(1) == 30.0


def test_the_two_scopes_diverge_above_quantity_one():
    per_unit = OperationTimeModelV2(setup_minutes=18, operator_touch_minutes=12)
    per_batch = OperationTimeModelV2(
        setup_minutes=18, operator_touch_minutes=12, setup_scope=SETUP_SCOPE_PER_BATCH
    )
    # 20 setups vs one, plus 20 lots of touch either way.
    assert per_unit.labor_minutes_for(20) == 18 * 20 + 12 * 20
    assert per_batch.labor_minutes_for(20) == 18 + 12 * 20


def test_labor_minutes_property_is_unchanged_by_scope():
    """The per-unit reading every existing caller depends on."""
    batch = OperationTimeModelV2(
        setup_minutes=18, operator_touch_minutes=12, setup_scope=SETUP_SCOPE_PER_BATCH
    )
    assert batch.labor_minutes == 30.0


# --------------------------------------------------------- baseline immunity


def test_accepted_v2_fixtures_are_byte_identical():
    """Adding setup_scope must not have disturbed the accepted baseline.

    Hashes rather than totals: a total can coincide, a hash cannot.
    """
    expected = {
        "thin_skin_variant_a_input_v1.json": "0adf1d90b304ada8",
        "thin_skin_variant_a_estimate_v1.json": "a7f8ff63331d3eef",
        "thin_skin_variant_b_input_v1.json": "1d53aa725d0180ea",
        "thin_skin_variant_b_estimate_v1.json": "78bfafd58439aa93",
    }
    for name, prefix in expected.items():
        path = ROOT / "fixtures" / "estimates" / "guitar" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest()[:16] == prefix, name


def test_accepted_v2_totals_are_unchanged():
    a = load(ROOT / "fixtures/estimates/guitar/thin_skin_variant_a_estimate_v1.json")
    b = load(ROOT / "fixtures/estimates/guitar/thin_skin_variant_b_estimate_v1.json")
    assert a["cost_summary"]["total_direct_manufacturing_cost"] == 700.89
    assert b["cost_summary"]["total_direct_manufacturing_cost"] == 730.59


# ------------------------------------------------------------ yield handling


def _ops() -> tuple[NeckOperation, ...]:
    return (
        NeckOperation("OP-4100", "cnc", setup_minutes=18, touch_minutes=12,
                      machine_minutes=52, setup_per_batch=True, from_state="M1"),
        NeckOperation("OP-4200", "fretwork", touch_minutes=78, from_state="M3"),
    )


def _mats() -> tuple[NeckMaterial, ...]:
    return (NeckMaterial("MAT", "stock", 60.0, "M1"),)


def test_batch_setup_divides_by_saleable_not_by_started():
    """A rejected neck consumed its share of setup; survivors carry it."""
    perfect = build_make_scenario(
        completion_state="M3", quantity=20, operations=_ops(), materials=_mats(),
        yield_policy=YieldPolicy(1.0, "none"), loaded_labour_rate=LAB, machine_rate=MACH,
    )
    lossy = build_make_scenario(
        completion_state="M3", quantity=20, operations=_ops(), materials=_mats(),
        yield_policy=YieldPolicy(0.9, "18 of 20"), loaded_labour_rate=LAB, machine_rate=MACH,
    )
    assert lossy.saleable == 18.0
    assert lossy.setup_cost > perfect.setup_cost
    assert lossy.cost_per_saleable > lossy.cost_per_started


def test_yield_loss_is_reported_not_absorbed():
    s = build_make_scenario(
        completion_state="M3", quantity=20, operations=_ops(), materials=_mats(),
        yield_policy=YieldPolicy(0.9, "18 of 20"), loaded_labour_rate=LAB, machine_rate=MACH,
    )
    assert s.yield_loss_per_saleable == pytest.approx(
        s.cost_per_saleable - s.cost_per_started, abs=0.01
    )
    assert s.yield_loss_per_saleable > 0


def test_impossible_yields_are_rejected():
    with pytest.raises(ValueError, match="yield rate"):
        YieldPolicy(0.0, "nothing survives")
    with pytest.raises(ValueError, match="yield rate"):
        YieldPolicy(1.2, "more out than in")


def test_saleable_cannot_exceed_started():
    op = NeckOperation("OP", "x", setup_minutes=10)
    with pytest.raises(ValueError, match="cannot exceed"):
        op.labour_minutes(quantity=10, saleable=12)


# ------------------------------------------------------------ batching truth


def test_only_one_operation_carries_setup(spec):
    """The whole finding rests on this. If it changes, the finding changes."""
    batch = [o["operation_id"] for o in spec["operations"] if o["setup_per_batch"]]
    assert batch == ["OP-4100"]
    carrying = [o["operation_id"] for o in spec["operations"] if o["setup_minutes"] > 0]
    assert carrying == ["OP-4100"]


def test_batching_benefit_is_bounded_and_small(result):
    be = result["batching_effect"]
    assert be["operations_carrying_setup"] == ["OP-4100"]
    # Ceiling is the whole setup cost, gross of yield. Nothing beats it.
    assert be["saving_qty_1_to_40"] < be["ceiling_at_infinite_quantity"]
    assert be["ceiling_at_infinite_quantity"] < 12.0


def test_construction_choice_beats_batching(result):
    """The headstock-angle decision is worth more than the router."""
    def pick(construction: str) -> float:
        return next(
            s["cost_per_saleable"]
            for s in result["make_scenarios"]
            if s["construction"] == construction
            and s["completion_state"] == "M4"
            and s["quantity"] == 20
        )

    spread = pick("ONE_PIECE") - pick("SCARF_JOINT")
    assert spread > result["batching_effect"]["ceiling_at_infinite_quantity"]


# ----------------------------------------------------------------- buy side


def test_unknown_landed_costs_do_not_produce_a_number():
    ref = BuyReference(
        reference_id="BUY-X", description="import", completion_state="M4",
        catalog_price=45.0, source="owner_research", confidence="draft",
    )
    assert ref.is_fully_landed is False
    assert ref.landed_cost_per_good(LAB) is None


def test_landed_cost_computes_when_every_field_is_known():
    ref = BuyReference(
        reference_id="BUY-X", description="import", completion_state="M4",
        catalog_price=45.0, source="owner_research", confidence="draft",
        freight_per_unit=6.0, duty_percent=7.5, incoming_inspection_minutes=8,
        corrective_work_minutes=15, reject_percent=10,
    )
    assert ref.is_fully_landed is True
    landed = ref.landed_cost_per_good(LAB)
    assert landed is not None
    # Catalog is not cost: duty, freight, inspection and rejects roughly half again.
    assert landed > ref.catalog_price * 1.5


def test_total_rejection_is_refused():
    ref = BuyReference(
        reference_id="BUY-X", description="x", completion_state="M4",
        catalog_price=45.0, source="s", confidence="draft",
        freight_per_unit=0, duty_percent=0, incoming_inspection_minutes=0,
        corrective_work_minutes=0, reject_percent=100,
    )
    with pytest.raises(ValueError, match="reject_percent"):
        ref.landed_cost_per_good(LAB)


def test_buy_references_report_what_they_do_not_know(result):
    for ref in result["buy_references"]:
        if not ref["is_fully_landed"]:
            assert ref["landed_cost_per_good"] is None
            assert ref["unknown_fields"]


def test_the_import_is_marked_not_comparable(result):
    """It has a composite board against AAA ebony; comparing them is the error."""
    imp = next(r for r in result["buy_references"] if r["reference_id"] == "BUY-IMPORT-BUDGET")
    joined = " ".join(imp["notes"]).upper()
    assert "NOT A LIKE-FOR-LIKE SUBSTITUTE" in joined
    assert "EVERY LANDED-COST FIELD IS UNKNOWN" in joined


# ---------------------------------------------------------------- thresholds


def test_threshold_is_none_when_materials_already_exceed_the_target():
    """Honest unreachability beats a negative number."""
    dear = (NeckMaterial("MAT", "dear stock", 200.0, "M1"),)
    t = fretwork_threshold(
        target_price=45.0, completion_state="M3", quantity=20, operations=_ops(),
        materials=dear, yield_policy=YieldPolicy(0.9, "x"),
        loaded_labour_rate=LAB, machine_rate=MACH, fretwork_operation_id="OP-4200",
    )
    assert t is None


def test_threshold_solves_to_the_target_price():
    mats = _mats()
    target = 150.0
    t = fretwork_threshold(
        target_price=target, completion_state="M3", quantity=20, operations=_ops(),
        materials=mats, yield_policy=YieldPolicy(0.9, "x"),
        loaded_labour_rate=LAB, machine_rate=MACH, fretwork_operation_id="OP-4200",
    )
    assert t is not None
    from dataclasses import replace

    tuned = tuple(
        replace(o, touch_minutes=t) if o.operation_id == "OP-4200" else o for o in _ops()
    )
    s = build_make_scenario(
        completion_state="M3", quantity=20, operations=tuned, materials=mats,
        yield_policy=YieldPolicy(0.9, "x"), loaded_labour_rate=LAB, machine_rate=MACH,
    )
    assert s.cost_per_saleable == pytest.approx(target, abs=0.02)


def test_boutique_target_is_unreachable_at_a_complete_neck(result):
    """The finding that overturned an earlier, incomplete hand-calculation.

    A table produced before OP-4150 and OP-4500 existed showed a cheap
    fretboard plus a 31% fretwork cut beating the boutique price. It was wrong
    for exactly the reason this sprint was called: it costed an UNFINISHED neck
    against a FINISHED purchased one. With fretboard installation, neck
    finishing and a 90% yield all present, no fretboard price reaches the
    target at any fretwork time.
    """
    rows = result["thresholds"]["BUY-BOUTIQUE"]["rows"]
    assert rows, "thresholds were not computed"
    # After the elapsed-wait fix a single combination reaches it, and only by
    # demanding an 87% fretwork cut on the cheapest board stock. Anything less
    # extreme misses, which is the honest shape of the result.
    reachable = [r for r in rows if r["reachable"]]
    assert len(reachable) == 1
    assert reachable[0]["fretboard_price"] == 5
    assert reachable[0]["reduction_percent"] > 80


def test_even_a_free_board_and_zero_fretwork_misses_the_target():
    """Proves the unreachability above is structural, not a swept-range artefact.

    Both levers at their physical limit still leaves in-house above the
    boutique price. Materials, machine time and the remaining operations
    account for the rest, and none of them is a lever this sprint identified.
    """
    ops = (
        NeckOperation("OP-1300", "staging", touch_minutes=10, from_state="M1"),
        NeckOperation("OP-4100", "cnc", setup_minutes=18, touch_minutes=12,
                      machine_minutes=52, setup_per_batch=True, from_state="M1"),
        NeckOperation("OP-4150", "fretboard install", touch_minutes=22, from_state="M2"),
        NeckOperation("OP-4200", "fretwork", touch_minutes=0.0, from_state="M3"),
        NeckOperation("OP-4300", "nut", touch_minutes=32, from_state="M4"),
        NeckOperation("OP-4400", "setup", touch_minutes=14, from_state="M4"),
        NeckOperation("OP-4500", "finishing", touch_minutes=32, from_state="M4"),
    )
    free_board = (
        NeckMaterial("MAT-NECK-MAHOGANY", "scarf stock", 0.995 * 8.00, "M1"),
        NeckMaterial("MAT-FRETBOARD", "free", 0.0, "M2"),
        NeckMaterial("CMP-TRUSS-ROD", "rod", 12.50, "M2"),
        NeckMaterial("CMP-FRETWIRE", "wire", 7.50, "M3"),
        NeckMaterial("CMP-NUT-BLANK", "nut", 3.25, "M4"),
    )
    floor = build_make_scenario(
        completion_state="M4", quantity=20, operations=ops, materials=free_board,
        yield_policy=YieldPolicy(0.9, "18 of 20"), loaded_labour_rate=LAB, machine_rate=MACH,
    )
    assert floor.cost_per_saleable > 125.0


# ------------------------------------------------------- completion states


def test_completion_states_are_cumulative(result):
    """M4 cannot cost less than M1; each state adds work."""
    for construction in ("SCARF_JOINT", "ONE_PIECE"):
        costs = [
            next(
                s["cost_per_saleable"]
                for s in result["make_scenarios"]
                if s["construction"] == construction
                and s["completion_state"] == state
                and s["quantity"] == 20
            )
            for state in COMPLETION_STATES
        ]
        assert costs == sorted(costs), f"{construction} states are not monotonic"


def test_draft_additions_are_flagged(spec):
    """Two operations here have never existed, let alone been measured."""
    drafts = {o["operation_id"] for o in spec["operations"] if o["is_draft_addition"]}
    assert drafts == {"OP-4150", "OP-4500"}
    finishing = next(o for o in spec["operations"] if o["operation_id"] == "OP-4500")
    assert "ENTIRE accepted product model" in finishing["note"]


def test_op_1300_impurity_is_recorded(spec):
    """Ruled neck-specific though it also stages body hardware."""
    op = next(o for o in spec["operations"] if o["operation_id"] == "OP-1300")
    assert "CLASSIFICATION IMPURITY" in op["note"]
    assert "overstates neck cost" in op["note"]


# ------------------------------------------------------- back-calculation


def _channel(**kw):
    base = dict(
        scenario_id="TEST",
        description="test route",
        retail_margin=0.40,
        distributor_margin=0.0,
        manufacturer_margin=0.30,
    )
    base.update(kw)
    return ChannelScenario(**base)


def test_channel_margins_compound_rather_than_add():
    """A 40% then 30% cut leaves 42% of the shelf price, not 30%.

    Adding margins is the classic error here and it inflates the derived
    manufacturing cost, which would flatter the make case.
    """
    assert _channel().manufacturing_cost(100.0) == pytest.approx(42.0)


def test_channel_margin_must_be_a_fraction_below_one():
    """A margin of 1.0 implies a zero-cost product; reject it at the boundary."""
    for bad in (1.0, 1.5, -0.1):
        with pytest.raises(ValueError):
            _channel(retail_margin=bad)
    with pytest.raises(ValueError):
        _channel().manufacturing_cost(0.0)


def test_deeper_channel_implies_a_lower_manufacturing_cost():
    shallow = _channel(retail_margin=0.35, manufacturer_margin=0.25)
    deep = _channel(retail_margin=0.50, distributor_margin=0.20, manufacturer_margin=0.35)
    assert deep.manufacturing_cost(200.0) < shallow.manufacturing_cost(200.0)


def _target(**kw):
    base = dict(
        scenario=_channel(),
        retail_price=200.0,
        shop_material_cost=40.0,
        shop_machine_minutes=60.0,
        shop_labour_minutes=180.0,
        loaded_labour_rate=28.75,
        machine_rate=28.97,
    )
    base.update(kw)
    return back_calculate_target(**base)


def test_back_calculation_reports_minutes_and_rate_as_one_constraint():
    """Both figures must spend exactly the same labour budget.

    Minutes-at-current-rate and rate-at-current-minutes are two views of one
    number. If they ever disagree, one of them is telling the shop the gap is
    smaller than it is.
    """
    t = _target()
    assert t.reachable is True
    from_minutes = t.labour_minutes_affordable / 60.0 * 28.75
    from_rate = t.implied_labour_rate * (180.0 / 60.0)
    assert from_minutes == pytest.approx(t.budget_for_labour, abs=0.05)
    assert from_rate == pytest.approx(t.budget_for_labour, abs=0.05)


def test_unreachable_target_reports_no_labour_figure_at_all():
    """Materials plus machine exceeding the target is not a labour problem.

    Emitting a negative labour budget would invite someone to read it as a
    number to close; there is no shop-floor change that reaches it.
    """
    t = _target(shop_material_cost=200.0)
    assert t.reachable is False
    assert t.budget_for_labour < 0
    assert t.labour_minutes_affordable is None
    assert t.implied_labour_rate is None
    assert "exceed the manufacturing cost" in t.note


def test_zero_labour_budget_is_unreachable_not_free():
    """Exactly zero budget must not be reported as a reachable zero-minute build."""
    mfg = _channel().manufacturing_cost(200.0)
    t = _target(shop_material_cost=mfg, shop_machine_minutes=0.0)
    assert t.budget_for_labour == 0.0
    assert t.reachable is False
    assert t.labour_minutes_affordable is None


def test_committed_back_calculation_brackets_rather_than_asserts(result):
    """The published answer must be a spread across routes, not one number."""
    bc = result["back_calculation"]
    assert len(bc["scenarios"]) >= 3
    assert bc["manufacturing_cost_low"] < bc["manufacturing_cost_high"]
    low = min(s["manufacturing_cost"] for s in bc["scenarios"])
    high = max(s["manufacturing_cost"] for s in bc["scenarios"])
    assert bc["manufacturing_cost_low"] == pytest.approx(low)
    assert bc["manufacturing_cost_high"] == pytest.approx(high)


def test_committed_anchor_is_not_claimed_to_be_comparable(spec):
    """The anchor is a headstock neck; the instrument is headless.

    It anchors channel arithmetic only. Letting it pass as a comparable product
    is the category error this whole section was built to correct.
    """
    anchor = spec["back_calculation"]["anchor"]
    assert anchor["is_comparable_product"] is False
    assert anchor["confidence"] == "confirmed"


def test_committed_back_calculation_says_the_gap_is_rate_times_content(result):
    """The shop's own labour must be far outside every reachable target."""
    bc = result["back_calculation"]
    assert bc["tightest_labour_minutes"] < 60
    assert bc["lowest_implied_labour_rate"] < 10
    assert bc["scenarios_unreachable_on_materials_and_machine"] >= 1


def test_report_quotes_the_committed_back_calculation(result):
    """The prose must carry the fixture's numbers, not a stale earlier draft.

    Every headline figure in this report has been wrong at least once during
    the sprint. A doc that drifts from the fixture it claims to summarise is
    the same defect as a fixture that does not recompute.
    """
    report = (ROOT / "docs" / "estimates" / "NECK_MAKE_OR_BUY_V1.md").read_text(
        encoding="utf-8"
    )
    bc = result["back_calculation"]
    for value in (
        bc["manufacturing_cost_low"],
        bc["manufacturing_cost_high"],
        bc["manufacturing_cost_midpoint"],
        bc["shop_current_cost"],
        bc["anchor_retail_price"],
        bc["tightest_labour_minutes"],
        bc["lowest_implied_labour_rate"],
    ):
        assert f"{value:,.2f}" in report or f"{value:g}" in report, (
            f"{value} is in the fixture but not in the report"
        )
    for row in bc["scenarios"]:
        assert f"{row['manufacturing_cost']:.2f}" in report, row["scenario_id"]
    assert "unreachable" in report


# ------------------------------------------------------------- governance


def test_nothing_authorises_a_decision(result):
    assert result["decision_authorized"] is False
    assert result["status"] == "draft"
    for f in result["findings"]:
        assert f["decision_authorized"] is False
        assert f["confidence"] == "draft"


def test_validator_passes_on_the_committed_fixtures():
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR)], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_validator_rejects_a_tampered_result(tmp_path):
    """Recomputation is the guard; a hand-edited total must not survive it."""
    spec_mod = importlib.util.spec_from_file_location("v", VALIDATOR)
    assert spec_mod is not None and spec_mod.loader is not None
    module = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(module)

    original = RESULT.read_text(encoding="utf-8")
    doc = json.loads(original)
    doc["make_scenarios"][0]["cost_per_saleable"] = 1.23
    RESULT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        assert module.main() == 1
    finally:
        RESULT.write_text(original, encoding="utf-8")
