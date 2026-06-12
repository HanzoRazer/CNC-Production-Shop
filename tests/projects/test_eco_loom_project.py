"""Tests for Eco-Loom project capture governance.

Dev Order: ECO-LOOM-PROJECT-CAPTURE-1

Tests verify:
1. Current fixtures validate against schemas
2. Schema rejects invalid data
3. Validator CLI works correctly
"""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent / "projects" / "eco_loom"
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "projects"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test 1-3: Current fixtures validate
# ---------------------------------------------------------------------------


class TestCurrentFixturesValidate:
    """Verify current project fixtures validate against schemas."""

    def test_project_capture_validates(self):
        """Current project capture validates against schema."""
        fixture = load_json(PROJECT_DIR / "eco_loom_project_capture_v1.json")
        schema = load_json(SCHEMA_DIR / "project_capture_v1.schema.json")
        jsonschema.validate(fixture, schema)

    def test_assumption_register_validates(self):
        """Current assumption register validates against schema."""
        fixture = load_json(PROJECT_DIR / "eco_loom_assumption_register_v1.json")
        schema = load_json(SCHEMA_DIR / "assumption_register_v1.schema.json")
        jsonschema.validate(fixture, schema)

    def test_open_questions_validates(self):
        """Current open questions validates against schema."""
        fixture = load_json(PROJECT_DIR / "eco_loom_open_questions_v1.json")
        schema = load_json(SCHEMA_DIR / "open_questions_v1.schema.json")
        jsonschema.validate(fixture, schema)


# ---------------------------------------------------------------------------
# Test 4: Missing project_name fails
# ---------------------------------------------------------------------------


class TestSchemaRejectsInvalidData:
    """Verify schemas reject invalid data."""

    def test_missing_project_name_fails(self):
        """Project capture without project_name fails validation."""
        schema = load_json(SCHEMA_DIR / "project_capture_v1.schema.json")

        invalid = {
            "status": "draft",
            "known_facts": [],
            "estimated_facts": [],
            "unknown_items": [],
            "open_questions": [],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_invalid_confidence_fails(self):
        """Assumption with invalid confidence fails validation."""
        schema = load_json(SCHEMA_DIR / "assumption_register_v1.schema.json")

        invalid = {
            "project_name": "test",
            "version": "v1",
            "status": "draft",
            "assumptions": [
                {
                    "field": "material",
                    "value": "wood",
                    "source": "guess",
                    "confidence": "very_high",  # Invalid
                    "captured_by": "test",
                    "capture_date": "2026-06-04",
                }
            ],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_invalid_question_status_fails(self):
        """Question with invalid status fails validation."""
        schema = load_json(SCHEMA_DIR / "open_questions_v1.schema.json")

        invalid = {
            "project_name": "test",
            "version": "v1",
            "status": "draft",
            "questions": [
                {
                    "id": "Q001",
                    "question": "Test?",
                    "status": "pending",  # Invalid - must be open/answered/closed
                }
            ],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_invalid_question_id_format_fails(self):
        """Question with invalid ID format fails validation."""
        schema = load_json(SCHEMA_DIR / "open_questions_v1.schema.json")

        invalid = {
            "project_name": "test",
            "version": "v1",
            "status": "draft",
            "questions": [
                {
                    "id": "question1",  # Invalid - must be Q001 format
                    "question": "Test?",
                    "status": "open",
                }
            ],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


# ---------------------------------------------------------------------------
# Test 7: Validator CLI returns success
# ---------------------------------------------------------------------------


class TestValidatorCLI:
    """Verify validator CLI works correctly."""

    def test_validator_returns_success(self):
        """Validator CLI returns exit code 0 for valid fixtures."""
        result = subprocess.run(
            [sys.executable, "scripts/validate_eco_loom_project.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "RESULT: PASS" in result.stdout


# ---------------------------------------------------------------------------
# Test: Project structure is draft
# ---------------------------------------------------------------------------


class TestProjectStructure:
    """Verify project structure follows governance rules."""

    def test_project_status_is_draft(self):
        """Project capture status is draft (awaiting customer info)."""
        fixture = load_json(PROJECT_DIR / "eco_loom_project_capture_v1.json")
        assert fixture["status"] == "draft"

    def test_known_facts_have_source(self):
        """All known facts have a source (no invented information)."""
        fixture = load_json(PROJECT_DIR / "eco_loom_project_capture_v1.json")
        for fact in fixture["known_facts"]:
            assert "source" in fact, f"Fact {fact['field']} missing source"
            assert fact["source"], f"Fact {fact['field']} has empty source"

    def test_estimated_facts_is_empty(self):
        """Estimated facts is empty (no unsubstantiated estimates)."""
        fixture = load_json(PROJECT_DIR / "eco_loom_project_capture_v1.json")
        assert fixture["estimated_facts"] == []

    def test_assumptions_have_required_fields(self):
        """All assumptions have required fields."""
        fixture = load_json(PROJECT_DIR / "eco_loom_assumption_register_v1.json")
        for assumption in fixture["assumptions"]:
            assert "field" in assumption
            assert "value" in assumption
            assert "source" in assumption
            assert "confidence" in assumption
            assert "captured_by" in assumption
            assert "capture_date" in assumption

    def test_open_questions_exist(self):
        """Open questions have been captured."""
        fixture = load_json(PROJECT_DIR / "eco_loom_open_questions_v1.json")
        assert len(fixture["questions"]) >= 5

    def test_questions_have_valid_status(self):
        """All questions have valid status (open, answered, or closed)."""
        fixture = load_json(PROJECT_DIR / "eco_loom_open_questions_v1.json")
        valid_statuses = {"open", "answered", "closed"}
        for q in fixture["questions"]:
            assert q["status"] in valid_statuses, f"Q{q['id']} has invalid status"

    def test_answered_questions_have_answers(self):
        """Answered questions have non-null answer field."""
        fixture = load_json(PROJECT_DIR / "eco_loom_open_questions_v1.json")
        for q in fixture["questions"]:
            if q["status"] == "answered":
                assert q["answer"] is not None, f"{q['id']} is answered but has no answer"
