"""Tests for opt-in governed machine-cost derivation (CNC-MACHINE-COST-WIRING-1).

Covers schema behavior, derivation, cross-reference integrity, backward
compatibility, model round-trip, commercial boundary, and CLI validation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import jsonschema
import pytest

from business.bids import (
    BidAssumptionV1,
    BidCostBasisV1,
    BidLineItemV1,
    BidPricingV1,
    BidV1,
    MachineCostingV1,
    build_machine_costing,
    calculate_bid_price,
    calculate_price_per_unit,
    calculate_risked_cost,
    derive_machine_time_cost,
)
from business.calculators.machine_cost_basis import (
    derive_machine_time_cost as calculator_derive_machine_time_cost,
)

ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = ROOT / "fixtures" / "bids"
PROPOSALS_DIR = ROOT / "fixtures" / "proposals"
SCHEMA_PATH = ROOT / "schemas" / "bids" / "bid_v1.schema.json"
DEMO_FIXTURE = FIXTURES_DIR / "machine_costed_demo_bid_v1.json"
MACHINE_PROFILE = ROOT / "fixtures" / "machines" / "bcm_2030ca_atc_v1.json"
COST_BASIS = (
    ROOT / "fixtures" / "machines" / "cost_basis" / "bcm_2030ca_atc_cost_basis_v1.json"
)
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_bid_fixtures.py"

LEGACY_BID_FIXTURES = [
    "eco_loom_prototype_bid_v1.json",
    "eco_loom_production_bid_100_v1.json",
    "eco_loom_production_bid_250_v1.json",
    "eco_loom_production_bid_500_v1.json",
]

# SHA-256 of legacy bid fixtures at base e477ab2 (byte-unchanged hard gate).
LEGACY_BID_SHA256 = {
    "eco_loom_prototype_bid_v1.json": (
        "d687643ef49ff33fcae7778bc3a06e69cb14ab67ee40e701aa237687ca8c69d9"
    ),
    "eco_loom_production_bid_100_v1.json": (
        "1738f8044d244816fd170800a4e99a6c00f15d9a8d6d6ae9755e155a755e0960"
    ),
    "eco_loom_production_bid_250_v1.json": (
        "ecdf2ce8f826af245958aa52210c22084012db2b61d30b31335dfcc033299305"
    ),
    "eco_loom_production_bid_500_v1.json": (
        "5d46f459b44d95fed9b4984dfb5057edabd7ec85f471489b6db9e00adee2f956"
    ),
}

ECO_LOOM_QUOTE_PRICES = {
    "eco_loom_prototype_bid_v1.json": 630.16,
    "eco_loom_production_bid_100_v1.json": 864.00,
    "eco_loom_production_bid_250_v1.json": 2058.00,
    "eco_loom_production_bid_500_v1.json": 4116.00,
}


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def file_sha256(path: Path) -> str:
    """Return lowercase hex SHA-256 of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _minimal_bid_dict(machine_costing: dict | None = None) -> dict:
    """Build a minimal schema-valid bid, optionally with machine_costing."""
    bid = {
        "bid_id": "BID-TEST-MACHINE-COSTING",
        "project_name": "Schema Probe",
        "customer_name": "INTERNAL-DEMO",
        "revision": "Draft 1",
        "status": "draft",
        "created_at": "2026-06-22T12:00:00Z",
        "updated_at": "2026-06-22T12:00:00Z",
        "assumptions": [],
        "line_items": [],
        "cost_basis": {
            "direct_material_cost": 0,
            "direct_labor_cost": 0,
            "machine_time_cost": 57.94,
            "tooling_cost": 0,
            "setup_cost": 0,
            "finishing_cost": 0,
            "finishing_material_cost": 0,
            "engineering_cost": 0,
            "base_manufacturing_cost": 57.94,
        },
        "pricing": {
            "tool_wear_pct": 0,
            "manufacturing_contingency_pct": 0,
            "business_overhead_pct": 0,
            "engineering_recovery_pct": 0,
            "target_margin_pct": 30.0,
            "risked_cost": 57.94,
            "quote_price": 82.77,
            "quantity": 1,
            "price_per_unit": 82.77,
        },
        "notes": ["schema probe"],
    }
    if machine_costing is not None:
        bid["machine_costing"] = machine_costing
    return bid


def _valid_machine_costing(**overrides) -> dict:
    """Return a valid machine_costing block with optional overrides."""
    block = {
        "machine_id": "MACHINE-BCM2030CA-ATC-V1",
        "machine_profile_ref": "fixtures/machines/bcm_2030ca_atc_v1.json",
        "cost_basis_id": "MACHINE-COST-BASIS-BCM2030CA-ATC-V1",
        "cost_basis_ref": (
            "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json"
        ),
        "cost_basis_role": "internal_technical_cost",
        "runtime_minutes": 120,
        "machine_hour_rate": 28.97,
        "derived_machine_time_cost": 57.94,
        "derivation": "machine_hour_rate * runtime_minutes / 60",
        "provenance_status": "draft",
    }
    block.update(overrides)
    return block


@pytest.fixture
def schema() -> dict:
    """Load the bid schema."""
    return load_json(SCHEMA_PATH)


@pytest.fixture
def demo() -> dict:
    """Load the demo bid fixture."""
    return load_json(DEMO_FIXTURE)


class TestSchemaBehavior:
    """Schema acceptance and rejection for machine_costing."""

    def test_bid_without_machine_costing_validates(self, schema):
        jsonschema.validate(_minimal_bid_dict(), schema)

    def test_bid_with_valid_machine_costing_validates(self, schema):
        jsonschema.validate(_minimal_bid_dict(_valid_machine_costing()), schema)

    def test_unknown_fields_in_machine_costing_fail(self, schema):
        invalid = _minimal_bid_dict(
            _valid_machine_costing(billing_rate=72.0)
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_missing_required_nested_fields_fail(self, schema):
        block = _valid_machine_costing()
        del block["cost_basis_ref"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_minimal_bid_dict(block), schema)

    @pytest.mark.parametrize("runtime", [0, -1, -120])
    def test_zero_or_negative_runtime_fails(self, schema, runtime):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _minimal_bid_dict(_valid_machine_costing(runtime_minutes=runtime)),
                schema,
            )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("machine_hour_rate", -0.01),
            ("derived_machine_time_cost", -1),
        ],
    )
    def test_negative_cost_or_rate_fails(self, schema, field, value):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _minimal_bid_dict(_valid_machine_costing(**{field: value})),
                schema,
            )

    def test_invalid_cost_basis_role_fails(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _minimal_bid_dict(
                    _valid_machine_costing(cost_basis_role="commercial_rate")
                ),
                schema,
            )

    def test_schema_rejects_unknown_top_level_fields(self, schema, demo):
        invalid = deepcopy(demo)
        invalid["secret_field"] = "should fail"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


class TestCalculation:
    """Derivation and money-rounding behavior."""

    def test_rate_times_runtime_equals_57_94(self):
        assert derive_machine_time_cost(28.97, 120) == 57.94

    def test_rounding_follows_calculator_convention(self):
        # Bid wrapper must match calculator money rounding (2 dp).
        assert derive_machine_time_cost(28.97, 1) == calculator_derive_machine_time_cost(
            28.97, 1
        )
        assert derive_machine_time_cost(28.97, 1) == 0.48

    def test_demo_derived_cost_equals_line_item(self, demo):
        mc = demo["machine_costing"]
        assert mc["derived_machine_time_cost"] == demo["cost_basis"]["machine_time_cost"]
        assert mc["derived_machine_time_cost"] == derive_machine_time_cost(
            mc["machine_hour_rate"], mc["runtime_minutes"]
        )

    def test_build_machine_costing_matches_demo_inputs(self):
        mc = build_machine_costing(
            machine_id="MACHINE-BCM2030CA-ATC-V1",
            runtime_minutes=120,
            machine_profile_path=Path("fixtures/machines/bcm_2030ca_atc_v1.json"),
            cost_basis_path=Path(
                "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json"
            ),
        )
        assert mc.machine_hour_rate == 28.97
        assert mc.derived_machine_time_cost == 57.94
        assert mc.cost_basis_role == "internal_technical_cost"
        assert mc.provenance_status == "draft"
        assert mc.derivation == "machine_hour_rate * runtime_minutes / 60"

    def test_tampered_derived_cost_fails_validator_logic(self, demo):
        from scripts.validate_bid_fixtures import validate_machine_costing

        tampered = deepcopy(demo)
        tampered["machine_costing"]["derived_machine_time_cost"] = 99.99
        errors = validate_machine_costing(tampered, DEMO_FIXTURE)
        assert errors

    def test_tampered_machine_hour_rate_fails_validator_logic(self, demo):
        from scripts.validate_bid_fixtures import validate_machine_costing

        tampered = deepcopy(demo)
        tampered["machine_costing"]["machine_hour_rate"] = 72.0
        errors = validate_machine_costing(tampered, DEMO_FIXTURE)
        assert errors


class TestCrossReferenceIntegrity:
    """Path and ID agreement checks."""

    def test_missing_machine_profile_fails(self, tmp_path):
        missing = tmp_path / "missing_profile.json"
        with pytest.raises(FileNotFoundError):
            build_machine_costing(
                machine_id="MACHINE-BCM2030CA-ATC-V1",
                runtime_minutes=120,
                machine_profile_path=missing,
                cost_basis_path=COST_BASIS,
            )

    def test_missing_cost_basis_fails(self, tmp_path):
        missing = tmp_path / "missing_cost_basis.json"
        with pytest.raises(FileNotFoundError):
            build_machine_costing(
                machine_id="MACHINE-BCM2030CA-ATC-V1",
                runtime_minutes=120,
                machine_profile_path=MACHINE_PROFILE,
                cost_basis_path=missing,
            )

    def test_machine_id_mismatch_fails(self, tmp_path):
        profile = load_json(MACHINE_PROFILE)
        profile["machine_id"] = "MACHINE-OTHER-V1"
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        with pytest.raises(ValueError, match="machine profile machine_id"):
            build_machine_costing(
                machine_id="MACHINE-BCM2030CA-ATC-V1",
                runtime_minutes=120,
                machine_profile_path=path,
                cost_basis_path=COST_BASIS,
            )

    def test_cost_basis_id_mismatch_detected_by_validator(self, demo):
        from scripts.validate_bid_fixtures import validate_machine_costing

        tampered = deepcopy(demo)
        tampered["machine_costing"]["cost_basis_id"] = "MACHINE-COST-BASIS-OTHER-V1"
        errors = validate_machine_costing(tampered, DEMO_FIXTURE)
        assert any("cost_basis_id mismatch" in e for e in errors)

    def test_cost_basis_referencing_other_machine_fails(self, tmp_path):
        basis = load_json(COST_BASIS)
        basis["machine_id"] = "MACHINE-OTHER-V1"
        path = tmp_path / "cost_basis.json"
        path.write_text(json.dumps(basis), encoding="utf-8")
        with pytest.raises(ValueError, match="cost basis machine_id"):
            build_machine_costing(
                machine_id="MACHINE-BCM2030CA-ATC-V1",
                runtime_minutes=120,
                machine_profile_path=MACHINE_PROFILE,
                cost_basis_path=path,
            )

    def test_draft_provenance_cannot_be_represented_as_approved(self, demo):
        from scripts.validate_bid_fixtures import validate_machine_costing

        tampered = deepcopy(demo)
        tampered["machine_costing"]["provenance_status"] = "approved"
        errors = validate_machine_costing(tampered, DEMO_FIXTURE)
        assert any("overstates" in e for e in errors)


class TestBackwardCompatibility:
    """Legacy bids remain valid and byte-unchanged."""

    @pytest.mark.parametrize("name", LEGACY_BID_FIXTURES)
    def test_legacy_fixture_has_no_machine_costing(self, name):
        fixture = load_json(FIXTURES_DIR / name)
        assert "machine_costing" not in fixture

    @pytest.mark.parametrize("name", LEGACY_BID_FIXTURES)
    def test_legacy_fixture_still_validates(self, name, schema):
        jsonschema.validate(load_json(FIXTURES_DIR / name), schema)

    @pytest.mark.parametrize("name", LEGACY_BID_FIXTURES)
    def test_legacy_fixture_bytes_unchanged(self, name):
        assert file_sha256(FIXTURES_DIR / name) == LEGACY_BID_SHA256[name]

    def test_legacy_bidv1_construction_still_works(self):
        bid = BidV1(
            bid_id="BID-LEGACY",
            project_name="Legacy",
            customer_name="Customer",
            revision="1",
            status="draft",
            created_at="2026-06-08T12:00:00Z",
            updated_at="2026-06-08T12:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=BidCostBasisV1(0, 0, 72.0, 0, 0, 0, 0, 0),
            pricing=BidPricingV1(0, 0, 0, 0, 30, 72.0, 102.86, 1, 102.86),
        )
        assert bid.machine_costing is None

    def test_existing_bid_calculations_unchanged(self):
        assert calculate_risked_cost(1000, 5, 10, 10, 15) == 1400.0
        assert calculate_bid_price(1000, 30.0) == 1428.57
        assert calculate_price_per_unit(1428.57, 10) == 142.86


class TestModelRoundTrip:
    """MachineCostingV1 / BidV1 serialization conventions."""

    def test_machine_costing_round_trip(self):
        mc = build_machine_costing(
            machine_id="MACHINE-BCM2030CA-ATC-V1",
            runtime_minutes=120,
            machine_profile_path=MACHINE_PROFILE,
            cost_basis_path=COST_BASIS,
        )
        payload = asdict(mc)
        restored = MachineCostingV1(**payload)
        assert restored == mc

    def test_optional_none_matches_convention(self):
        bid = BidV1(
            bid_id="BID-NONE",
            project_name="None Case",
            customer_name="INTERNAL",
            revision="1",
            status="draft",
            created_at="2026-06-22T12:00:00Z",
            updated_at="2026-06-22T12:00:00Z",
            assumptions=[],
            line_items=[],
            cost_basis=BidCostBasisV1(0, 0, 0, 0, 0, 0, 0, 0),
            pricing=BidPricingV1(0, 0, 0, 0, 30, 0, 0, 1, 0),
        )
        assert bid.machine_costing is None
        assert bid.project_ref is None

    def test_complete_bid_round_trip_preserves_machine_costing(self, demo):
        mc = demo["machine_costing"]
        bid = BidV1(
            bid_id=demo["bid_id"],
            project_name=demo["project_name"],
            customer_name=demo["customer_name"],
            revision=demo["revision"],
            status=demo["status"],
            created_at=demo["created_at"],
            updated_at=demo["updated_at"],
            assumptions=[BidAssumptionV1(**a) for a in demo["assumptions"]],
            line_items=[BidLineItemV1(**li) for li in demo["line_items"]],
            cost_basis=BidCostBasisV1(
                **{
                    k: v
                    for k, v in demo["cost_basis"].items()
                    if k != "base_manufacturing_cost"
                }
            ),
            pricing=BidPricingV1(**demo["pricing"]),
            notes=list(demo["notes"]),
            project_ref=demo["project_ref"],
            manufacturing_ref=demo["manufacturing_ref"],
            scenario_ref=demo["scenario_ref"],
            machine_costing=MachineCostingV1(**mc),
        )
        assert asdict(bid.machine_costing) == mc


class TestCommercialBoundary:
    """Technical cost wiring must not alter commercial Eco-Loom artifacts."""

    @pytest.mark.parametrize("name,price", list(ECO_LOOM_QUOTE_PRICES.items()))
    def test_eco_loom_prices_unchanged(self, name, price):
        fixture = load_json(FIXTURES_DIR / name)
        assert fixture["pricing"]["quote_price"] == price
        machine_rate = next(
            a["value"] for a in fixture["assumptions"] if a["field"] == "machine_rate"
        )
        assert machine_rate == 72.0

    def test_no_proposal_gains_machine_costing(self):
        for path in sorted(PROPOSALS_DIR.glob("*.json")):
            data = load_json(path)
            assert "machine_costing" not in data
            assert "machine_hour_rate" not in json.dumps(data)

    def test_no_markdown_customer_artifact_exposes_technical_rate(self):
        markdown_dirs = [
            ROOT / "fixtures" / "proposals",
            ROOT / "exports",
            ROOT / "docs",
        ]
        for directory in markdown_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                assert "28.97" not in text
                assert "internal_technical_cost" not in text

    def test_demo_is_internal_not_production_quote(self, demo):
        notes = " ".join(demo["notes"]).lower()
        assert "internal" in notes
        assert "demo" in notes
        assert "not an eco-loom" in notes or "not a formal" in notes
        assert demo["machine_costing"]["provenance_status"] == "draft"
        assert demo["machine_costing"]["cost_basis_role"] == "internal_technical_cost"
        assert demo["customer_name"] == "INTERNAL-DEMO"


class TestDemoFixtureConsistency:
    """Demo fixture remains internally consistent with calculators."""

    def test_fixture_validates(self, demo, schema):
        jsonschema.validate(demo, schema)

    def test_pricing_matches_calculators(self, demo):
        cb = demo["cost_basis"]
        pricing = demo["pricing"]
        risked = calculate_risked_cost(
            base_cost=cb["base_manufacturing_cost"],
            tool_wear_pct=pricing["tool_wear_pct"],
            manufacturing_contingency_pct=pricing["manufacturing_contingency_pct"],
            business_overhead_pct=pricing["business_overhead_pct"],
            engineering_recovery_pct=pricing["engineering_recovery_pct"],
        )
        assert pricing["risked_cost"] == risked
        quote = calculate_bid_price(risked, pricing["target_margin_pct"])
        assert pricing["quote_price"] == quote
        assert pricing["price_per_unit"] == calculate_price_per_unit(
            quote, pricing["quantity"]
        )


class TestCliValidator:
    """scripts/validate_bid_fixtures.py exit behavior."""

    def test_validator_exits_zero_with_demo_fixture(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS machine_costed_demo_bid_v1.json" in result.stdout

    def test_validator_exits_nonzero_for_tampered_temp_fixture(self, tmp_path):
        from scripts.validate_bid_fixtures import validate_fixture

        schema = load_json(SCHEMA_PATH)
        tampered = load_json(DEMO_FIXTURE)
        tampered["machine_costing"]["derived_machine_time_cost"] = 12.34
        tampered["cost_basis"]["machine_time_cost"] = 12.34
        path = tmp_path / "tampered_bid.json"
        path.write_text(json.dumps(tampered), encoding="utf-8")
        passed, messages = validate_fixture(path, schema)
        assert not passed
        assert any("derived_machine_time_cost" in m for m in messages)
