"""Tests for the neck defect-mode taxonomy.

Dev Order: NECK-QUALITY-TAXONOMY-1

The cost model beside this one spent a sprint comparing a $35 basswood neck to
a $187.88 khaya one as though they were prices on the same object. These tests
pin the three distinctions that stop it happening again: preventing a defect is
not the same as repairing one, a defect nobody can fix is not a cost, and a
check nobody can run is not a pass.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from business.estimates.neck_quality import (
    DISPOSITION_ACCEPT,
    DISPOSITION_REWORK,
    DISPOSITION_SCRAP,
    ELIMINATION_LABOUR,
    ELIMINATION_PROCESS,
    ELIMINATION_SPECIFICATION,
    VISIBILITY_AT_RECEIPT,
    VISIBILITY_LATENT,
    AcceptanceCriterion,
    DefectMode,
    NeckSource,
    compare_coverage,
    disposition_for,
    profile_source,
    verifiability_profile,
)

ROOT = Path(__file__).resolve().parents[2]
NECK = ROOT / "fixtures" / "estimates" / "neck"
INPUT = NECK / "neck_defect_taxonomy_v1.json"
RESULT = NECK / "neck_defect_taxonomy_result_v1.json"
VALIDATOR = ROOT / "scripts" / "validate_neck_quality.py"
RATE = 28.75


@pytest.fixture
def spec():
    return json.loads(INPUT.read_text(encoding="utf-8"))


@pytest.fixture
def result():
    return json.loads(RESULT.read_text(encoding="utf-8"))


# ------------------------------------------------------------- defect modes


def _mode(**kw):
    base = dict(
        defect_id="DEF-TEST",
        description="test mode",
        elimination=ELIMINATION_LABOUR,
        visibility=VISIBILITY_AT_RECEIPT,
        remediable=True,
        labour_minutes=10.0,
        remediation_minutes=10.0,
    )
    base.update(kw)
    return DefectMode(**base)


def test_a_process_mode_may_not_cost_anything_to_prevent():
    """The central claim: machine precision is quality an hourly rate cannot erode.

    If a PROCESS mode ever acquires a prevention cost the claim is silently
    false, so the class refuses to be constructed that way.
    """
    with pytest.raises(ValueError, match="costs nothing marginal"):
        _mode(elimination=ELIMINATION_PROCESS, labour_minutes=5.0, remediation_minutes=5.0)
    with pytest.raises(ValueError, match="costs nothing marginal"):
        _mode(elimination=ELIMINATION_PROCESS, labour_minutes=0.0, material_cost=3.0,
              remediation_minutes=5.0)


def test_prevention_and_repair_are_separate_prices():
    """Free to prevent is not free to fix, and conflating them flatters buying."""
    mode = _mode(
        elimination=ELIMINATION_PROCESS,
        labour_minutes=0.0,
        remediation_minutes=45.0,
        remediation_material=4.0,
    )
    assert mode.cost(RATE) == 0.0
    assert mode.repair_cost(RATE) == pytest.approx(45.0 / 60 * RATE + 4.0, abs=0.01)


def test_irremediable_modes_carry_no_repair_price():
    with pytest.raises(ValueError, match="carries a repair price"):
        _mode(
            elimination=ELIMINATION_SPECIFICATION,
            remediable=False,
            labour_minutes=0.0,
            material_cost=8.0,
            remediation_minutes=30.0,
        )
    mode = _mode(
        elimination=ELIMINATION_SPECIFICATION,
        remediable=False,
        labour_minutes=0.0,
        material_cost=8.0,
        remediation_minutes=0.0,
    )
    assert mode.repair_cost(RATE) is None


def test_nothing_is_repaired_for_free():
    with pytest.raises(ValueError, match="remediable at no cost"):
        _mode(remediable=True, remediation_minutes=0.0, remediation_material=0.0)


def test_labour_defects_cannot_be_declared_irremediable():
    """Marking handwork unfixable hides a material failure behind labour."""
    with pytest.raises(ValueError, match="remediable by"):
        _mode(elimination=ELIMINATION_LABOUR, remediable=False, remediation_minutes=0.0)


# ------------------------------------------------------- the comparison gate


def _taxonomy():
    return (
        _mode(defect_id="D-FIXABLE", remediation_minutes=20.0),
        _mode(
            defect_id="D-FATAL",
            elimination=ELIMINATION_SPECIFICATION,
            remediable=False,
            labour_minutes=0.0,
            material_cost=9.0,
            remediation_minutes=0.0,
            visibility=VISIBILITY_LATENT,
        ),
    )


def _src(sid, addresses, arrival="MATERIAL_RECEIPT"):
    return NeckSource(
        source_id=sid,
        description=sid,
        addresses=frozenset(addresses),
        evidence="assumed",
        arrival_stage=arrival,
    )


def test_an_unfixable_gap_makes_the_comparison_void_not_expensive():
    """The refusal. A price here would say parity is purchasable."""
    cmp = compare_coverage(
        source=_src("POOR", []),
        against=_src("GOOD", ["D-FIXABLE", "D-FATAL"]),
        taxonomy=_taxonomy(),
        labour_rate=RATE,
    )
    assert cmp.comparable is False
    assert cmp.blocking_modes == ("D-FATAL",)
    assert cmp.remediation_cost is None
    assert cmp.remediation_minutes is None
    assert "NOT COMPARABLE" in cmp.verdict


def test_a_closable_gap_is_priced_at_repair_cost_not_prevention_cost():
    cmp = compare_coverage(
        source=_src("POOR", []),
        against=_src("GOOD", ["D-FIXABLE"]),
        taxonomy=(_taxonomy()[0],),
        labour_rate=RATE,
    )
    assert cmp.comparable is True
    assert cmp.remediation_minutes == 20.0
    assert cmp.remediation_cost == pytest.approx(20.0 / 60 * RATE, abs=0.01)


def test_matching_coverage_compares_directly():
    tax = (_taxonomy()[0],)
    cmp = compare_coverage(
        source=_src("A", ["D-FIXABLE"]),
        against=_src("B", ["D-FIXABLE"]),
        taxonomy=tax,
        labour_rate=RATE,
    )
    assert cmp.comparable is True and cmp.missing_modes == ()
    assert "may be compared on cost directly" in cmp.verdict


def test_a_source_cannot_claim_coverage_of_a_mode_that_does_not_exist():
    with pytest.raises(ValueError, match="unknown modes"):
        compare_coverage(
            source=_src("A", ["D-IMAGINARY"]),
            against=_src("B", []),
            taxonomy=_taxonomy(),
            labour_rate=RATE,
        )


def test_free_process_coverage_is_counted_separately(spec):
    src = _src("SHOP", ["D-FIXABLE", "D-FATAL"])
    p = profile_source(source=src, taxonomy=_taxonomy(), labour_rate=RATE)
    assert p.process_cost == 0.0
    assert p.specification_cost == 9.0
    assert p.labour_minutes == 10.0
    assert p.modes_open == 0


# --------------------------------------------------------- the buy-vs-build gate


def _criterion(defect_id, stage):
    return AcceptanceCriterion(
        defect_id=defect_id,
        stage=stage,
        method="measure it",
        pass_criterion="within tolerance",
    )


def test_a_criterion_without_a_method_is_not_a_gate():
    with pytest.raises(ValueError, match="not a gate"):
        AcceptanceCriterion(
            defect_id="D", stage="M1", method="   ", pass_criterion="within tolerance"
        )
    with pytest.raises(ValueError, match="nothing decides"):
        AcceptanceCriterion(defect_id="D", stage="M1", method="measure", pass_criterion="")


def test_a_draft_threshold_cannot_be_marked_owner_confirmed():
    with pytest.raises(ValueError, match="still a draft proposal"):
        AcceptanceCriterion(
            defect_id="D",
            stage="M1",
            method="measure",
            pass_criterion="within tolerance",
            threshold=0.4,
            owner_confirmed=True,
        )


def test_buying_finished_means_the_early_checks_cannot_be_run():
    """The build-versus-buy result: what differs is not score but verifiability.

    A neck arriving at M4 cannot be judged against a criterion describing the
    blank it was cut from. That is not a failure — it is an absence of evidence,
    and it must never be recorded as a pass.
    """
    criteria = (_criterion("D-FATAL", "MATERIAL_RECEIPT"), _criterion("D-FIXABLE", "M4"))
    built = verifiability_profile(
        source=_src("SHOP", [], "MATERIAL_RECEIPT"), criteria=criteria, taxonomy=_taxonomy()
    )
    bought = verifiability_profile(
        source=_src("IMPORT", [], "M4"), criteria=criteria, taxonomy=_taxonomy()
    )
    assert built.verifiable_fraction == 1.0
    assert bought.verifiable == ("D-FIXABLE",)
    assert bought.unverifiable == ("D-FATAL",)
    # The pointed number: cannot be checked on arrival AND cannot be fixed after.
    assert bought.unverifiable_and_irrecoverable == ("D-FATAL",)


def test_verifiability_never_reports_a_buried_check_as_a_pass():
    criteria = (_criterion("D-FATAL", "M1"), _criterion("D-FIXABLE", "M2"))
    v = verifiability_profile(
        source=_src("IMPORT", [], "M4"), criteria=criteria, taxonomy=_taxonomy()
    )
    assert v.verifiable == ()
    assert len(v.unverifiable) == 2
    assert v.verifiable_fraction == 0.0


# ------------------------------------------------------------- disposition


def test_disposition_is_derived_from_remediability_not_chosen():
    tax = _taxonomy()
    clean = disposition_for(failed_modes=(), taxonomy=tax, labour_rate=RATE, value_at_risk=50.0)
    assert clean.verdict == DISPOSITION_ACCEPT

    rework = disposition_for(
        failed_modes=("D-FIXABLE",), taxonomy=tax, labour_rate=RATE, value_at_risk=150.0
    )
    assert rework.verdict == DISPOSITION_REWORK
    assert rework.rework_minutes == 20.0

    scrap = disposition_for(
        failed_modes=("D-FIXABLE", "D-FATAL"), taxonomy=tax, labour_rate=RATE, value_at_risk=150.0
    )
    assert scrap.verdict == DISPOSITION_SCRAP
    assert scrap.unrecoverable_modes == ("D-FATAL",)


def test_scrap_carries_no_rework_budget_to_hide_the_loss_in():
    scrap = disposition_for(
        failed_modes=("D-FATAL",), taxonomy=_taxonomy(), labour_rate=RATE, value_at_risk=187.88
    )
    assert scrap.rework_cost == 0.0 and scrap.rework_minutes == 0.0
    assert scrap.loss_if_scrapped == 187.88


def test_rework_costing_more_than_the_part_says_so():
    """A rework budget above the part's value is scrap wearing a different label."""
    d = disposition_for(
        failed_modes=("D-FIXABLE",), taxonomy=_taxonomy(), labour_rate=RATE, value_at_risk=2.0
    )
    assert d.verdict == DISPOSITION_REWORK
    assert "scrap is cheaper" in d.reason


def test_where_you_gate_sets_the_loss():
    """Same unrecoverable fault, caught at two stages. The verdict is identical."""
    early = disposition_for(
        failed_modes=("D-FATAL",), taxonomy=_taxonomy(), labour_rate=RATE, value_at_risk=48.93
    )
    late = disposition_for(
        failed_modes=("D-FATAL",), taxonomy=_taxonomy(), labour_rate=RATE, value_at_risk=187.88
    )
    assert early.verdict == late.verdict == DISPOSITION_SCRAP
    assert late.loss_if_scrapped > early.loss_if_scrapped * 3


def test_disposition_rejects_a_mode_outside_the_taxonomy():
    with pytest.raises(ValueError, match="not in the taxonomy"):
        disposition_for(
            failed_modes=("D-GHOST",), taxonomy=_taxonomy(), labour_rate=RATE, value_at_risk=1.0
        )


# ------------------------------------------------------ the committed fixtures


def test_every_mode_can_be_judged_on_both_sides(result):
    """A mode with no criterion is invisible to the gate on either side."""
    assert result["acceptance_gate"]["modes_without_criterion"] == []


def test_no_threshold_has_been_set_by_the_owner_yet(result, spec):
    """The gate is a structure awaiting numbers, and must not pose as a spec."""
    assert result["acceptance_gate"]["owner_confirmed_thresholds"] == 0
    assert all(a["threshold_source"] == "proposed_draft" for a in spec["acceptance"])


def test_the_committed_verifiability_gap_is_the_headline(result):
    shop = next(v for v in result["verifiability"] if v["source_id"] == "SRC-SHOP-CNC")
    buy = next(v for v in result["verifiability"] if v["source_id"] != "SRC-SHOP-CNC")
    assert shop["verifiable_fraction"] == 1.0
    assert buy["verifiable_count"] < shop["verifiable_count"]
    assert buy["unverifiable_and_irrecoverable"]


def test_the_observed_import_comparison_is_refused(result):
    cmp = result["comparisons"][0]
    assert cmp["comparable"] is False
    assert cmp["remediation_cost"] is None
    assert len(cmp["blocking_modes"]) > 0


def test_quality_labour_is_a_subset_of_the_cost_model_not_an_addition(result):
    """These are the same minutes seen by purpose, so they cannot exceed the total."""
    cost = json.loads((NECK / "neck_make_or_buy_result_v1.json").read_text(encoding="utf-8"))
    m4 = next(
        s
        for s in cost["make_scenarios"]
        if s["completion_state"] == "M4"
        and s["quantity"] == 20
        and s["construction"] == "SCARF_JOINT"
    )
    shop = next(p for p in result["source_profiles"] if p["source_id"] == "SRC-SHOP-CNC")
    assert 0 < shop["labour_minutes"] <= m4["labour_minutes"]


def test_uncharacterised_sources_get_no_coverage(spec):
    """A source nobody has handled must not acquire a score by being listed."""
    characterised = {s["source_id"] for s in spec["sources"]}
    for u in spec["uncharacterised_sources"]:
        assert u["source_id"] not in characterised
        assert u["why"]


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


def test_validator_rejects_a_purchase_credited_with_checks_nobody_ran():
    """The failure this whole module exists to prevent."""
    spec_mod = importlib.util.spec_from_file_location("vq", VALIDATOR)
    assert spec_mod is not None and spec_mod.loader is not None
    module = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(module)

    original = RESULT.read_text(encoding="utf-8")
    doc = json.loads(original)
    buy = next(v for v in doc["verifiability"] if v["source_id"] != "SRC-SHOP-CNC")
    buy["verifiable"] = sorted(set(buy["verifiable"]) | {buy["unverifiable"][0]})
    buy["verifiable_count"] = len(buy["verifiable"])
    RESULT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        assert module.main() == 1
    finally:
        RESULT.write_text(original, encoding="utf-8")
