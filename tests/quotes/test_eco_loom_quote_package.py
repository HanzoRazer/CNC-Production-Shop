"""Tests for Eco-Loom quote package and revision fixtures.

Dev Order: CNC-QUOTE-PACKAGE-1

Tests verify:
1. Eco-Loom package and revision validate against schemas
2. Cross-references are correct
3. All referenced artifacts exist
4. Options are modeled correctly (not as revisions)
5. Validator CLI works
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "quotes"
ROOT_DIR = Path(__file__).parent.parent.parent


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


class TestEcoLoomPackageValidates:
    """Verify Eco-Loom package validates against schema."""

    @pytest.fixture
    def package(self):
        """Load Eco-Loom production package."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_package_v1.json")

    @pytest.fixture
    def package_schema(self):
        """Load package schema."""
        return load_json(SCHEMA_DIR / "quote_package_v1.schema.json")

    def test_package_validates(self, package, package_schema):
        """Package validates against schema."""
        jsonschema.validate(package, package_schema)

    def test_package_id_format(self, package):
        """Package ID follows expected format."""
        assert package["package_id"] == "QP-ECOLOOM-PROD-2026-001"

    def test_package_status_is_active(self, package):
        """Package status is active."""
        assert package["status"] == "active"

    def test_package_has_one_revision(self, package):
        """Package contains exactly one revision."""
        assert len(package["revisions"]) == 1

    def test_package_references_project(self, package):
        """Package references project capture."""
        assert package["project_ref"] == "projects/eco_loom/eco_loom_project_capture_v1.json"


class TestEcoLoomRevisionValidates:
    """Verify Eco-Loom revision validates against schema."""

    @pytest.fixture
    def revision(self):
        """Load Eco-Loom production revision A."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_revision_a_v1.json")

    @pytest.fixture
    def revision_schema(self):
        """Load revision schema."""
        return load_json(SCHEMA_DIR / "quote_revision_v1.schema.json")

    def test_revision_validates(self, revision, revision_schema):
        """Revision validates against schema."""
        jsonschema.validate(revision, revision_schema)

    def test_revision_id_format(self, revision):
        """Revision ID follows expected format."""
        assert revision["revision_id"] == "QR-ECOLOOM-PROD-2026-001-A"

    def test_revision_letter_is_a(self, revision):
        """Revision letter is A."""
        assert revision["revision_letter"] == "A"

    def test_revision_status_is_active(self, revision):
        """Revision status is active."""
        assert revision["status"] == "active"

    def test_revision_has_three_options(self, revision):
        """Revision contains three quantity options."""
        assert len(revision["options"]) == 3

    def test_revision_references_package(self, revision):
        """Revision references parent package."""
        assert revision["package_ref"] == "projects/eco_loom/eco_loom_production_quote_package_v1.json"


class TestCrossReferences:
    """Verify package and revision cross-reference each other."""

    @pytest.fixture
    def package(self):
        """Load package."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_package_v1.json")

    @pytest.fixture
    def revision(self):
        """Load revision."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_revision_a_v1.json")

    def test_revision_in_package_revisions(self, package, revision):
        """Revision is listed in package revisions."""
        revision_ids = [r["revision_id"] for r in package["revisions"]]
        assert revision["revision_id"] in revision_ids

    def test_package_ref_matches_package(self, package, revision):
        """Revision package_ref points to package file."""
        package_ref = revision["package_ref"]
        assert package_ref == "projects/eco_loom/eco_loom_production_quote_package_v1.json"


class TestOptionsAreNotRevisions:
    """Verify quantity tiers are modeled as options, not revisions."""

    @pytest.fixture
    def revision(self):
        """Load revision."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_revision_a_v1.json")

    def test_options_have_different_quantities(self, revision):
        """Options represent different quantity tiers."""
        quantities = [opt["quantity"] for opt in revision["options"]]
        assert sorted(quantities) == [100, 250, 500]

    def test_options_are_concurrent(self, revision):
        """All options are active (concurrent, not superseded)."""
        statuses = [opt["status"] for opt in revision["options"]]
        assert all(s == "active" for s in statuses)

    def test_options_are_not_revisions(self, revision):
        """Options do not have revision-like fields."""
        for option in revision["options"]:
            assert "supersedes" not in option
            assert "revision_letter" not in option


class TestReferencedArtifactsExist:
    """Verify all referenced artifacts exist."""

    @pytest.fixture
    def revision(self):
        """Load revision."""
        return load_json(PROJECT_DIR / "eco_loom_production_quote_revision_a_v1.json")

    def test_workbook_exists(self, revision):
        """Workbook reference exists."""
        workbook_ref = revision.get("workbook_ref")
        if workbook_ref:
            assert (ROOT_DIR / workbook_ref).exists()

    @pytest.mark.parametrize("quantity", [100, 250, 500])
    def test_bid_exists(self, revision, quantity):
        """Bid reference exists."""
        option = next(o for o in revision["options"] if o["quantity"] == quantity)
        assert (ROOT_DIR / option["bid_ref"]).exists()

    @pytest.mark.parametrize("quantity", [100, 250, 500])
    def test_bid_summary_exists(self, revision, quantity):
        """Bid summary reference exists."""
        option = next(o for o in revision["options"] if o["quantity"] == quantity)
        assert (ROOT_DIR / option["bid_summary_ref"]).exists()

    @pytest.mark.parametrize("quantity", [100, 250, 500])
    def test_proposal_exists(self, revision, quantity):
        """Proposal reference exists."""
        option = next(o for o in revision["options"] if o["quantity"] == quantity)
        assert (ROOT_DIR / option["proposal_ref"]).exists()

    @pytest.mark.parametrize("quantity", [100, 250, 500])
    def test_markdown_exists(self, revision, quantity):
        """Markdown reference exists."""
        option = next(o for o in revision["options"] if o["quantity"] == quantity)
        markdown_ref = option.get("markdown_ref")
        if markdown_ref:
            assert (ROOT_DIR / markdown_ref).exists()


class TestValidatorCLI:
    """Verify validator CLI works correctly."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_quote_packages.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "RESULT: PASS" in result.stdout
