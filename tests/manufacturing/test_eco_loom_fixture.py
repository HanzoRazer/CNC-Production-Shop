"""Tests for Eco-Loom manufacturing fixture validation.

Dev Order: ECOLOOM-GOVERNANCE-1

Structure validation only. These tests exercise the executable governance
layer: that shipped fixtures conform to their schemas, and that the schemas
reject missing required fields, out-of-bound numbers, and unknown keys, while
keeping the confidence field permissive.

They do NOT bridge into the cost engine (no cost_inputs -> SimpleJobCostInput
adapter, no quote calculation) -- that is intentionally a later sprint, because
the cost-input mapping is documented but incomplete.
"""

from scripts.validate_eco_loom_fixture import (
    load_schema,
    validate_eco_loom_pairs,
    validate_instance,
)

# ---------------------------------------------------------------------------
# Valid baseline instances (built only from known schema keys)
# ---------------------------------------------------------------------------


def valid_cost_inputs() -> dict:
    """Minimal cost-inputs instance satisfying the schema's required fields."""
    return {
        "material_cost": 0,
        "machine_runtime_minutes": 0,
        "target_margin_pct": 30.0,
    }


def valid_manufacturing_fixture() -> dict:
    """Minimal manufacturing-fixture instance satisfying required fields."""
    return {
        "material": "hard maple",
        "machine": "3-axis CNC router",
        "operations": [],
        "cycle_time_minutes": 0,
        "confidence": "draft",
    }


# ---------------------------------------------------------------------------
# Shipped on-disk fixtures conform
# ---------------------------------------------------------------------------


class TestShippedFixturesValidate:
    """The fixtures committed in ECOLOOM-MFG-READINESS-1 must validate."""

    def test_all_eco_loom_pairs_pass(self):
        """Every shipped (fixture, schema) pair validates structurally."""
        results = validate_eco_loom_pairs()
        assert results, "expected at least one eco_loom pair"
        for result in results:
            assert result.ok, f"{result.label} failed: {result.errors}"

    def test_current_cost_fixture_validates(self):
        """The shipped cost-inputs fixture conforms to its schema."""
        by_label = {r.label: r for r in validate_eco_loom_pairs()}
        result = by_label["eco_loom_cost_inputs_v1.json"]
        assert result.ok, result.errors

    def test_current_manufacturing_fixture_validates(self):
        """The shipped manufacturing fixture conforms to its schema."""
        by_label = {r.label: r for r in validate_eco_loom_pairs()}
        result = by_label["eco_loom_manufacturing_fixture_v1.json"]
        assert result.ok, result.errors


# ---------------------------------------------------------------------------
# Manufacturing fixture schema
# ---------------------------------------------------------------------------


class TestManufacturingFixtureSchema:
    """Required fields, numeric bounds, unknown keys, permissive confidence."""

    def setup_method(self):
        self.schema = load_schema("manufacturing_fixture_v1.schema.json")

    def test_valid_instance_passes(self):
        result = validate_instance(valid_manufacturing_fixture(), self.schema)
        assert result.ok, result.errors

    def test_missing_material_fails(self):
        instance = valid_manufacturing_fixture()
        del instance["material"]
        result = validate_instance(instance, self.schema)
        assert not result.ok
        assert any("material" in message for message in result.errors)

    def test_negative_cycle_time_fails(self):
        instance = valid_manufacturing_fixture()
        instance["cycle_time_minutes"] = -1
        result = validate_instance(instance, self.schema)
        assert not result.ok
        assert any("cycle_time_minutes" in message for message in result.errors)

    def test_unknown_key_fails(self):
        """additionalProperties=false: stray keys are rejected."""
        instance = valid_manufacturing_fixture()
        instance["unexpected_field"] = "oops"
        result = validate_instance(instance, self.schema)
        assert not result.ok

    def test_arbitrary_confidence_string_passes(self):
        """confidence is a plain string: future review states are not blocked."""
        instance = valid_manufacturing_fixture()
        instance["confidence"] = "machinist-reviewed"
        result = validate_instance(instance, self.schema)
        assert result.ok, result.errors

    def test_blank_strings_and_zero_allowed(self):
        """Draft placeholders (blank strings, zeros) remain structurally valid."""
        instance = {
            "material": "",
            "stock_size": "",
            "machine": "",
            "workholding": "",
            "tooling": [],
            "operations": [],
            "cycle_time_minutes": 0,
            "confidence": "draft",
        }
        result = validate_instance(instance, self.schema)
        assert result.ok, result.errors


# ---------------------------------------------------------------------------
# Cost inputs schema
# ---------------------------------------------------------------------------


class TestCostInputsSchema:
    """Required fields and the target-margin bound."""

    def setup_method(self):
        self.schema = load_schema("cost_inputs_v1.schema.json")

    def test_valid_instance_passes(self):
        result = validate_instance(valid_cost_inputs(), self.schema)
        assert result.ok, result.errors

    def test_target_margin_at_100_fails(self):
        """target_margin_pct must be < 100 (exclusiveMaximum)."""
        instance = valid_cost_inputs()
        instance["target_margin_pct"] = 100
        result = validate_instance(instance, self.schema)
        assert not result.ok
        assert any("target_margin_pct" in message for message in result.errors)

    def test_target_margin_over_100_fails(self):
        instance = valid_cost_inputs()
        instance["target_margin_pct"] = 150
        result = validate_instance(instance, self.schema)
        assert not result.ok

    def test_negative_machine_runtime_fails(self):
        instance = valid_cost_inputs()
        instance["machine_runtime_minutes"] = -5
        result = validate_instance(instance, self.schema)
        assert not result.ok
        assert any("machine_runtime_minutes" in message for message in result.errors)

    def test_missing_required_field_fails(self):
        instance = valid_cost_inputs()
        del instance["material_cost"]
        result = validate_instance(instance, self.schema)
        assert not result.ok

    def test_unknown_key_fails(self):
        instance = valid_cost_inputs()
        instance["mystery_rate"] = 1.23
        result = validate_instance(instance, self.schema)
        assert not result.ok
