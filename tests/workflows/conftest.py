"""Shared fixtures for the job quote workflow tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JOB_REL = "fixtures/jobs/cnc_job_quote_demo_v1.json"
OUTPUT_REL = "exports/jobs/cnc-job-quote-demo-001"
SOURCE_RELS = (
    JOB_REL,
    "fixtures/estimates/guitar/cnc_electric_guitar_baseline_input_v1.json",
    "fixtures/products/cnc_electric_guitar_baseline_v1.json",
    "fixtures/machines/bcm_2030ca_atc_v1.json",
    "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json",
)


def copy_demo_workspace(dest: Path) -> Path:
    """Copy the synthetic demo inputs, preserving their workspace-relative paths."""
    for rel in SOURCE_RELS:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return dest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return copy_demo_workspace(tmp_path / "ws")
