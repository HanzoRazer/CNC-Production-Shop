"""Tests for the two Smart Guitar product lines.

Split on 2026-07-27 from a single record that conflated a hollow thin-skin
practice instrument with a solid-body performance instrument. These tests
guard the distinctions that were conflated, because each one drives a
different cost model downstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "products" / "instrument_product_v2.schema.json"
SMART = ROOT / "fixtures" / "products" / "smart_guitar_v1.json"
KHAYA = ROOT / "fixtures" / "products" / "khaya_solidbody_v1.json"


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def smart() -> dict:
    return load(SMART)


@pytest.fixture(scope="module")
def khaya() -> dict:
    return load(KHAYA)


@pytest.mark.parametrize("path", [SMART, KHAYA])
def test_fixtures_match_schema(path):
    jsonschema.validate(load(path), load(SCHEMA))


def test_the_two_lines_are_distinct_products(smart, khaya):
    assert smart["product_id"] != khaya["product_id"]
    assert smart["product_role"] == "practice_instrument"
    assert khaya["product_role"] == "performance_instrument"
    assert smart["construction"]["body_type"] == "hollow_thin_skin_box"
    assert khaya["construction"]["body_type"] == "solid_body"


def test_smart_guitar_is_headless_only(smart):
    """The headed variant belongs to the Khaya line, not this one.

    Conflating them is what the split fixed: the budget model is headless
    only, so a headed series appearing here would silently widen its scope.
    """
    series = smart["series"]
    assert len(series) == 1
    assert series[0]["headstock"] == "none_headless"


def test_khaya_carries_both_headstock_series(khaya):
    heads = {s["headstock"] for s in khaya["series"]}
    assert heads == {"none_headless", "flying_v_inline_6"}
    primary = [s for s in khaya["series"] if s["status"] == "primary_build_target"]
    assert len(primary) == 1
    assert primary[0]["headstock"] == "none_headless"


def test_onboard_audio_is_the_functional_difference(smart, khaya):
    """The HAT is what separates the packages, and it tracks the use case.

    A practice instrument is played through headphones, so it needs the I2S
    HAT. A performance instrument goes to an amp through the dry jack, so it
    does not. Same compute host in both.
    """
    assert smart["electronics_package"]["onboard_audio_output"] is True
    assert khaya["electronics_package"]["onboard_audio_output"] is False
    assert (
        smart["electronics_package"]["compute_host"]
        == khaya["electronics_package"]["compute_host"]
    )
    assert any("HiFiBerry" in c for c in smart["electronics_package"]["components"])
    assert not any("HiFiBerry" in c for c in khaya["electronics_package"]["components"])


def test_both_lines_are_concept_not_draft(smart, khaya):
    """Neither instrument has been measured. The status must not overstate it."""
    for product in (smart, khaya):
        assert product["status"] == "concept"
        assert product["provenance"]["confidence"] == "draft"
    assert "AI-generated" in " ".join(smart["notes"])
    assert "AI-generated" in " ".join(khaya["notes"])


def test_khaya_packing_failure_supersedes_the_area_claim(khaya):
    """An area budget said it fits; a real packing test says it does not.

    Both are recorded, because the superseded figure is why the line was
    taken self-contained in the first place.
    """
    notes = " ".join(khaya["notes"])
    assert "PACKING DOES NOT CLOSE" in notes
    assert "123 cm2 spare" in notes and "supersedes" in notes
    assert "cannot coexist" in notes
    q = khaya["electronics_package"]["open_question"]
    assert "WHETHER THIS LINE CARRIES ONBOARD COMPUTE AT ALL" in q
    assert "product decision, not an engineering one" in q


def test_khaya_records_why_the_hat_was_dropped_not_just_that_it_was(khaya):
    """A ruling that records only its outcome invites the same question again.

    The HAT left this line 25 cm2 short, closing only on a margin change. That
    borderline result is the reason for the decision, so it stays recorded
    alongside the comfortable configuration that replaced it.
    """
    notes = " ".join(khaya["notes"])
    assert "123 cm2 spare" in notes
    assert "25 cm2 short" in notes and "96 cm2 short" in notes
    assert "45 mm tall in a 47 mm blank" in notes


def test_m2_is_recorded_as_external_with_its_dimensional_reason(khaya):
    """External is a conclusion, not a preference, and must carry its evidence."""
    ep = khaya["electronics_package"]
    assert ep["onboard_audio_output"] is False
    assert any("EXTERNAL" in c for c in ep["components"])
    reason = ep["external_components_note"]
    assert "190.5 x 108 x 45" in reason
    assert "99%" in reason


def test_no_embedded_third_party_consumer_products(smart, khaya):
    """A finished retail product may not be designed in as an internal part.

    This is a policy, not a rejection of one candidate: it rules out every
    retail interface regardless of whether it physically fits, and it is the
    reason the front end became a custom subassembly. External peripherals are
    deliberately exempt — shipping an interface is resale, not embedding.
    """
    for product in (smart, khaya):
        notes = " ".join(product["notes"])
        assert "NO EMBEDDED THIRD-PARTY CONSUMER PRODUCTS" in notes
        assert "iRig HD 2" in notes and "MOTU M2" in notes
        assert "EXTERNAL peripherals are NOT affected" in notes


def test_front_end_is_scoped_as_custom_with_its_cost_class(smart, khaya):
    """NRE and certification are not unit cost, and must not be folded into it."""
    q = smart["electronics_package"]["open_question"]
    assert "CUSTOM SUBASSEMBLY" in q
    assert "non-recurring engineering" in q
    assert "EMC certification" in q
    assert "separate lines rather than folding them into unit cost" in q


def test_smart_guitar_audio_front_end_is_open(smart):
    """The interface question is unresolved and must not read as settled.

    A HiFiBerry alone does not replace an interface: the guitar-specific
    analog work — Hi-Z stage, preamp, gain, headphone amp, protection,
    filtering — is what a USB interface already solves.
    """
    q = smart["electronics_package"]["open_question"]
    assert "UNRESOLVED" in q
    assert "Hi-Z input impedance" in q and "headphone amplifier" in q
    # The envelope stopped being the binding constraint once the answer became
    # a bare board rather than a boxed product.
    assert "Physical envelope is not the constraint" in q
    assert "campfire" in q


def test_void_edge_cost_is_carried_on_the_thin_skin_line(smart):
    """The visual identity has a measured price; keep it attached to the product."""
    notes = " ".join(smart["notes"])
    assert "3.01 m" in notes
    assert "deliberately NOT reduced" in notes


def test_no_cost_fields_in_a_product_record(smart, khaya):
    forbidden = {"cost", "unit_cost", "price", "margin", "markup", "msrp"}

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in forbidden, key
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(smart)
    scan(khaya)
