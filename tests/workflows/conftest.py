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
JOB_A = "fixtures/jobs/cnc_job_quote_thin_skin_a_v2.json"
JOB_B = "fixtures/jobs/cnc_job_quote_thin_skin_b_v2.json"
OUTPUT_A = "exports/jobs/thin-skin-a-quote-001"
OUTPUT_B = "exports/jobs/thin-skin-b-quote-001"
ESTIMATE_A = "fixtures/estimates/guitar/thin_skin_variant_a_input_v1.json"
ESTIMATE_B = "fixtures/estimates/guitar/thin_skin_variant_b_input_v1.json"
THIN_SKIN_COMMON = (
    "fixtures/products/thin_skin_electric_guitar_baseline_v1.json",
    "fixtures/machines/bcm_2030ca_atc_v1.json",
    "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json",
    "fixtures/equipment/cure_rack_v1.json",
    "fixtures/equipment/spray_booth_v1.json",
    "fixtures/equipment/vacuum_press_v1.json",
    "fixtures/equipment/cost_basis/cure_rack_cost_basis_v1.json",
    "fixtures/equipment/cost_basis/spray_booth_cost_basis_v1.json",
    "fixtures/equipment/cost_basis/vacuum_press_cost_basis_v1.json",
)


def _copy_rels(dest: Path, rels: tuple[str, ...]) -> Path:
    for rel in rels:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return dest


def copy_demo_workspace(dest: Path) -> Path:
    """Copy the synthetic demo inputs, preserving their workspace-relative paths."""
    return _copy_rels(dest, SOURCE_RELS)


def thin_skin_source_rels(variant: str) -> tuple[str, ...]:
    """Job, estimate input, and the shared product, machine, and equipment records."""
    if variant == "a":
        return (JOB_A, ESTIMATE_A, *THIN_SKIN_COMMON)
    if variant == "b":
        return (JOB_B, ESTIMATE_B, *THIN_SKIN_COMMON)
    raise ValueError(f"unknown thin-skin variant: {variant}")


def copy_thin_skin_workspace(dest: Path, variant: str) -> Path:
    """Copy one thin-skin variant and every governed dependency it names."""
    return _copy_rels(dest, thin_skin_source_rels(variant))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return copy_demo_workspace(tmp_path / "ws")


@pytest.fixture
def thin_skin_workspace(tmp_path: Path) -> Path:
    return copy_thin_skin_workspace(tmp_path / "ws", "a")
