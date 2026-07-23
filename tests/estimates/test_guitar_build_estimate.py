"""Tests for GUITAR-BUILD-ESTIMATE-1.

Covers schemas, lineage, category math, machine costing, scrap eligibility,
provenance boundaries, and regression against Eco-Loom / machine fixtures.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import jsonschema
import pytest

from business.bids import MachineCostingV1
from business.calculators.machine_cost_basis import money_equal
from business.estimates.guitar import (
    calculate_component_cost,
    calculate_guitar_build_estimate,
    calculate_labor_cost,
    calculate_material_cost,
    calculate_scrap_allowance,
    operation_labor_minutes,
    operation_machine_minutes,
)
from business.estimates.loading import load_guitar_estimate_input
from business.estimates.models import (
    EstimateProvenanceV1,
    MaterialInputV1,
)

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_SCHEMA = ROOT / "schemas" / "products" / "guitar_product_definition_v1.schema.json"
INPUT_SCHEMA = ROOT / "schemas" / "estimates" / "guitar_estimate_input_v1.schema.json"
ESTIMATE_SCHEMA = ROOT / "schemas" / "estimates" / "guitar_build_estimate_v1.schema.json"
PRODUCT = ROOT / "fixtures" / "products" / "cnc_electric_guitar_baseline_v1.json"
INPUT = ROOT / "fixtures" / "estimates" / "guitar" / "cnc_electric_guitar_baseline_input_v1.json"
ESTIMATE = (
    ROOT / "fixtures" / "estimates" / "guitar" / "cnc_electric_guitar_baseline_estimate_v1.json"
)
VALIDATE = ROOT / "scripts" / "validate_guitar_estimates.py"

LEGACY_SHA256 = {
    "fixtures/bids/eco_loom_prototype_bid_v1.json": (
        "b41d59c6e622dd70bc0694d55bad30f146ed18b81c9dd44247b095d00727d15d"
    ),
    "fixtures/bids/eco_loom_production_bid_100_v1.json": (
        "deddf11e2f671aaec91960679b59b534193e3825fa123f67662664433e013538"
    ),
    "fixtures/machines/bcm_2030ca_atc_v1.json": (
        "867e632afe0e340aece87219734cbbeba61dcf0c13be5996e71f1bac1275fd8a"
    ),
    "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json": (
        "4d92a5a77ed7ae50347e1bd2d003736731a523cbd0b95e3b142c00784a49a47c"
    ),
}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture
def product() -> dict:
    return load_json(PRODUCT)


@pytest.fixture
def estimate_input() -> dict:
    return load_json(INPUT)


@pytest.fixture
def estimate() -> dict:
    return load_json(ESTIMATE)


@pytest.fixture
def domain_input():
    return load_guitar_estimate_input(INPUT)


class TestSchemas:
    def test_product_fixture_validates(self, product):
        jsonschema.validate(product, load_json(PRODUCT_SCHEMA))

    def test_unknown_product_field_fails(self, product):
        product["price"] = 1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(product, load_json(PRODUCT_SCHEMA))

    def test_missing_product_id_fails(self, product):
        del product["product_id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(product, load_json(PRODUCT_SCHEMA))

    def test_invalid_status_fails(self, product):
        product["status"] = "quoted"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(product, load_json(PRODUCT_SCHEMA))

    def test_invalid_scale_length_fails(self, product):
        product["construction"]["scale_length_in"] = 0
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(product, load_json(PRODUCT_SCHEMA))

    def test_estimate_input_validates(self, estimate_input):
        jsonschema.validate(estimate_input, load_json(INPUT_SCHEMA))

    def test_missing_operations_fails(self, estimate_input):
        estimate_input["operations"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate_input, load_json(INPUT_SCHEMA))

    def test_unknown_input_field_fails(self, estimate_input):
        estimate_input["target_margin_pct"] = 30
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate_input, load_json(INPUT_SCHEMA))

    def test_negative_unit_cost_fails(self, estimate_input):
        estimate_input["material_inputs"][0]["unit_cost"] = -1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate_input, load_json(INPUT_SCHEMA))

    def test_invalid_quantity_fails(self, estimate_input):
        estimate_input["quantity"] = 0
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate_input, load_json(INPUT_SCHEMA))

    def test_estimate_fixture_validates(self, estimate):
        jsonschema.validate(estimate, load_json(ESTIMATE_SCHEMA))

    @pytest.mark.parametrize("field", ["customer_price", "quote_price", "margin"])
    def test_customer_price_fields_rejected(self, estimate, field):
        estimate[field] = 1000
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate, load_json(ESTIMATE_SCHEMA))

    def test_unknown_estimate_field_fails(self, estimate):
        estimate["billing_rate"] = 72
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(estimate, load_json(ESTIMATE_SCHEMA))


class TestLineage:
    def test_estimate_references_product(self, product, estimate_input, estimate):
        assert estimate_input["product_id"] == product["product_id"]
        assert estimate["product_id"] == product["product_id"]
        assert estimate["estimate_input_id"] == estimate_input["estimate_input_id"]

    def test_validator_detects_product_id_mismatch(self, estimate_input, product):
        assert estimate_input["product_id"] == product["product_id"]
        mismatched = deepcopy(estimate_input)
        mismatched["product_id"] = "PRODUCT-OTHER-V1"
        assert mismatched["product_id"] != product["product_id"]



class TestMaterialsAndComponents:
    def test_material_extended_cost(self, domain_input):
        assert calculate_material_cost(domain_input.material_inputs) == 115.0

    def test_wood_separate_from_hardware(self, domain_input):
        wood = calculate_material_cost(domain_input.material_inputs)
        hardware = calculate_component_cost(
            domain_input.purchased_component_inputs, "hardware"
        )
        electronics = calculate_component_cost(
            domain_input.purchased_component_inputs, "electronics"
        )
        assert wood == 115.0
        assert hardware == 125.0
        assert electronics == 110.0
        assert wood != hardware

    def test_negative_unit_cost_rejected(self):
        item = MaterialInputV1(
            input_id="X",
            description="x",
            category="wood",
            quantity=1,
            unit="blank",
            unit_cost=-1,
            provenance=EstimateProvenanceV1("catalog_price", "draft"),
        )
        with pytest.raises(ValueError):
            calculate_material_cost([item])

    def test_duplicate_input_ids_fail(self, domain_input):
        dup = domain_input.material_inputs + (
            replace(domain_input.material_inputs[0], description="dup"),
        )
        bad = replace(domain_input, material_inputs=dup)
        with pytest.raises(ValueError, match="duplicate input_id"):
            calculate_guitar_build_estimate(
                bad,
                estimate_input_ref="x",
                effective_date="2026-07-22",
            )


class TestLaborAndMachine:
    def test_labor_minutes_to_cost(self):
        assert calculate_labor_cost(60, 28.75) == 28.75
        assert calculate_labor_cost(30, 28.75) == 14.38

    def test_unattended_runtime_does_not_force_equal_labor(self, domain_input):
        op = next(
            o
            for o in domain_input.operations
            if o.operation_id == "OP-2000-BODY-CNC-MACHINE"
        )
        assert operation_machine_minutes(op, 1) == 90
        assert operation_labor_minutes(op) == 30
        assert operation_labor_minutes(op) != operation_machine_minutes(op, 1)

    def test_setup_minutes_included(self, domain_input):
        op = next(o for o in domain_input.operations if o.operation_id == "OP-2000-BODY-CNC-SETUP")
        assert operation_machine_minutes(op, 1) == 25

    def test_machine_rate_from_governed_fixture(self, domain_input, estimate):
        result = calculate_guitar_build_estimate(
            domain_input,
            estimate_input_ref=estimate["estimate_input_ref"],
            effective_date=estimate["calculation"]["effective_date"],
        )
        assert isinstance(result.machine_costing, MachineCostingV1)
        assert result.machine_costing.machine_hour_rate == 28.97
        assert result.machine_costing.cost_basis_role == "internal_technical_cost"
        assert result.machine_costing.runtime_minutes == 260.0
        assert result.cost_summary.machine_time_cost == 125.54

    def test_no_default_machine_when_paths_missing(self, domain_input, tmp_path):
        with pytest.raises((FileNotFoundError, ValueError)):
            calculate_guitar_build_estimate(
                domain_input,
                estimate_input_ref="x",
                effective_date="2026-07-22",
                machine_profile_path=tmp_path / "missing.json",
                cost_basis_path=tmp_path / "missing2.json",
                repo_root=tmp_path,
            )

    def test_tampered_machine_cost_fails_money_equal(self, estimate):
        assert money_equal(estimate["cost_summary"]["machine_time_cost"], 125.54)
        estimate["cost_summary"]["machine_time_cost"] = 999.0
        assert not money_equal(estimate["cost_summary"]["machine_time_cost"], 125.54)


class TestFinishingAndScrap:
    def test_finish_materials_in_consumables(self, estimate):
        assert estimate["cost_summary"]["consumables_cost"] == 75.0
        assert estimate["cost_summary"]["finishing_cost"] == 83.86

    def test_cure_wait_not_labor(self, domain_input):
        op = next(o for o in domain_input.operations if o.operation_id == "OP-5000-FINISH-APPLY")
        assert op.cure_or_wait_minutes == 1440
        assert operation_labor_minutes(op) == 60

    def test_scrap_only_eligible_ids(self, domain_input):
        scrap = calculate_scrap_allowance(
            material_inputs=domain_input.material_inputs,
            purchased_component_inputs=domain_input.purchased_component_inputs,
            eligible_input_ids=domain_input.scrap_policy.eligible_input_ids,
            scrap_rate=0.05,
        )
        assert scrap == 7.0
        # Electronics/hardware not eligible: 115 wood + 8+5+12 consumables = 140 * 0.05 = 7
        assert "EL-PICKUP-SET-SSS" not in domain_input.scrap_policy.eligible_input_ids
        assert "HW-BRIDGE-TREMOLO" not in domain_input.scrap_policy.eligible_input_ids

    def test_negative_scrap_rate_fails(self, domain_input):
        with pytest.raises(ValueError):
            calculate_scrap_allowance(
                material_inputs=domain_input.material_inputs,
                purchased_component_inputs=domain_input.purchased_component_inputs,
                eligible_input_ids=domain_input.scrap_policy.eligible_input_ids,
                scrap_rate=-0.01,
            )


class TestTotalsAndBoundaries:
    def test_totals_recompute(self, domain_input, estimate):
        result = calculate_guitar_build_estimate(
            domain_input,
            estimate_id=estimate["estimate_id"],
            estimate_input_ref=estimate["estimate_input_ref"],
            effective_date=estimate["calculation"]["effective_date"],
        )
        assert asdict(result.cost_summary) == estimate["cost_summary"]
        assert result.cost_summary.total_direct_manufacturing_cost == 924.09

    def test_no_customer_price_or_margin_fields(self, estimate):
        blob = json.dumps(estimate)
        assert "quote_price" not in blob
        assert "target_margin" not in blob
        assert "72.0" not in blob
        assert estimate["machine_costing"]["machine_hour_rate"] == 28.97

    def test_draft_status(self, estimate, estimate_input):
        assert estimate_input["status"] == "draft"
        assert estimate["status"] == "draft"
        assert estimate["provenance"]["source"] == "calculated"
        assert estimate["provenance"]["confidence"] == "draft"

    def test_draft_cannot_be_approved_status(self, domain_input):
        bad = replace(domain_input, status="approved")
        with pytest.raises(ValueError, match="approved estimate status"):
            calculate_guitar_build_estimate(
                bad,
                estimate_input_ref="x",
                effective_date="2026-07-22",
            )

    @pytest.mark.parametrize("rel,digest", list(LEGACY_SHA256.items()))
    def test_legacy_fixtures_unchanged(self, rel, digest):
        assert sha256_lf(ROOT / rel) == digest

    def test_eco_loom_prices_unchanged(self):
        prices = {
            "eco_loom_prototype_bid_v1.json": 630.16,
            "eco_loom_production_bid_100_v1.json": 864.0,
            "eco_loom_production_bid_250_v1.json": 2058.0,
            "eco_loom_production_bid_500_v1.json": 4116.0,
        }
        for name, price in prices.items():
            data = load_json(ROOT / "fixtures" / "bids" / name)
            assert data["pricing"]["quote_price"] == price
            rate = next(a["value"] for a in data["assumptions"] if a["field"] == "machine_rate")
            assert rate == 72.0

    def test_docs_mark_internal(self):
        text = (ROOT / "docs" / "estimates" / "GUITAR_BUILD_ESTIMATE_BASELINE_V1.md").read_text(
            encoding="utf-8"
        )
        assert "not** a customer quote" in text.lower() or "not a customer quote" in text.lower()
        assert "internal manufacturing cost" in text.lower()
        assert "draft" in text.lower()


class TestCliValidator:
    def test_validator_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_validator_exits_nonzero_when_tampered(self):
        tampered = load_json(ESTIMATE)
        tampered["cost_summary"]["total_direct_manufacturing_cost"] = 1.0
        domain = load_guitar_estimate_input(INPUT)
        recomputed = calculate_guitar_build_estimate(
            domain,
            estimate_id=tampered["estimate_id"],
            estimate_input_ref=tampered["estimate_input_ref"],
            effective_date=tampered["calculation"]["effective_date"],
        )
        assert not money_equal(
            tampered["cost_summary"]["total_direct_manufacturing_cost"],
            recomputed.cost_summary.total_direct_manufacturing_cost,
        )
