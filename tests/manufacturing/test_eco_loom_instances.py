"""Tests for Eco-Loom draft instance fixtures and their provenance.

Dev Order: ECOLOOM-CYCLETIME-1

Governed capture only: these tests prove that the draft_001 instances validate
against their schemas, that provenance exists for every captured field, and
that the draft-sprint governance rules hold (everything is draft; no value is
attributed to a machinist until one signs off). No quote, no bid.
"""

from scripts.validate_eco_loom_fixture import (
    INSTANCE_DIR,
    load_json,
    validate_eco_loom_instances,
)

COST_INPUTS = INSTANCE_DIR / "eco_loom_cost_inputs_draft_001.json"
MANUFACTURING = INSTANCE_DIR / "eco_loom_manufacturing_fixture_draft_001.json"
COST_INPUTS_PROV = INSTANCE_DIR / "eco_loom_cost_inputs_draft_001.provenance.json"
MANUFACTURING_PROV = INSTANCE_DIR / "eco_loom_manufacturing_fixture_draft_001.provenance.json"

VALUE_INSTANCES = [COST_INPUTS, MANUFACTURING]
PROVENANCE_FILES = [COST_INPUTS_PROV, MANUFACTURING_PROV]


# ---------------------------------------------------------------------------
# Instances validate against their schemas
# ---------------------------------------------------------------------------


class TestDraft001InstancesValidate:
    def test_all_instances_pass(self):
        """Validator discovers and passes every instance + provenance file."""
        results = validate_eco_loom_instances()
        assert len(results) == 4, [r.label for r in results]
        for result in results:
            assert result.ok, f"{result.label} failed: {result.errors}"

    def test_cost_inputs_instance_validates(self):
        labels = {r.label: r for r in validate_eco_loom_instances()}
        assert labels[COST_INPUTS.name].ok

    def test_manufacturing_instance_validates(self):
        labels = {r.label: r for r in validate_eco_loom_instances()}
        assert labels[MANUFACTURING.name].ok

    def test_provenance_sidecars_validate(self):
        labels = {r.label: r for r in validate_eco_loom_instances()}
        assert labels[COST_INPUTS_PROV.name].ok
        assert labels[MANUFACTURING_PROV.name].ok


# ---------------------------------------------------------------------------
# Draft-sprint governance
# ---------------------------------------------------------------------------


class TestDraftGovernance:
    def test_manufacturing_fixture_confidence_is_draft(self):
        assert load_json(MANUFACTURING)["confidence"] == "draft"

    def test_provenance_top_level_confidence_is_draft(self):
        for path in PROVENANCE_FILES:
            assert load_json(path)["confidence"] == "draft", path.name

    def test_all_provenance_entries_are_draft(self):
        for path in PROVENANCE_FILES:
            for entry in load_json(path)["entries"]:
                assert entry["confidence"] == "draft", (path.name, entry["field"])

    def test_no_machinist_measured_in_draft(self):
        """No draft value may be attributed to a machinist until one signs off."""
        for path in PROVENANCE_FILES:
            for entry in load_json(path)["entries"]:
                assert entry["source"] != "machinist_measured", (path.name, entry["field"])

    def test_sources_are_known(self):
        allowed = {
            "engineering_estimate",
            "autocad_designer_estimate",
            "shop_estimate",
            "machinist_measured",
        }
        for path in PROVENANCE_FILES:
            for entry in load_json(path)["entries"]:
                assert entry["source"] in allowed, (path.name, entry["source"])

    def test_provenance_instance_matches_fixture(self):
        assert load_json(COST_INPUTS_PROV)["instance"] == COST_INPUTS.name
        assert load_json(MANUFACTURING_PROV)["instance"] == MANUFACTURING.name


# ---------------------------------------------------------------------------
# Shop-level values are the documented kernel values (honest hybrid)
# ---------------------------------------------------------------------------


class TestShopValuesMatchDocumentedKernel:
    """The populated shop-level rates must match established repo values."""

    def test_cost_inputs_shop_values(self):
        data = load_json(COST_INPUTS)
        assert data["operator_rate"] == 23.0
        assert data["payroll_burden_pct"] == 25.0
        assert data["machine_burden_rate"] == 19.0
        assert data["electricity_rate_per_hour"] == 1.97
        assert data["tooling_rate_per_hour"] == 8.0
        assert data["target_margin_pct"] == 30.0

    def test_product_specific_values_remain_provisional(self):
        """Product-specific fields stay blank/zero (no fabricated specs)."""
        cost = load_json(COST_INPUTS)
        assert cost["material_cost"] == 0
        assert cost["machine_runtime_minutes"] == 0
        assert cost["setup_cost"] == 0
        mfg = load_json(MANUFACTURING)
        assert mfg["material"] == ""
        assert mfg["stock_size"] == ""
        assert mfg["machine"] == ""
        assert mfg["tooling"] == []
        assert mfg["operations"] == []
        assert mfg["cycle_time_minutes"] == 0


# ---------------------------------------------------------------------------
# Provenance completeness: every captured field is accounted for
# ---------------------------------------------------------------------------


class TestProvenanceCompleteness:
    def test_every_cost_field_has_provenance(self):
        fields = set(load_json(COST_INPUTS).keys())
        recorded = {e["field"] for e in load_json(COST_INPUTS_PROV)["entries"]}
        assert fields <= recorded, fields - recorded

    def test_every_manufacturing_value_field_has_provenance(self):
        # 'confidence' is record metadata, not a captured value.
        fields = set(load_json(MANUFACTURING).keys()) - {"confidence"}
        recorded = {e["field"] for e in load_json(MANUFACTURING_PROV)["entries"]}
        assert fields <= recorded, fields - recorded
