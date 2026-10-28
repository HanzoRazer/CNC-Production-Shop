"""Shared fixtures for the job quote workflow tests."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from business.workflows.verification import verify_job_quote_packet
from business.workflows.verification_models import JobQuoteVerification

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


def generate_job_packet(tmp_path: Path, variant: str) -> Path:
    """Generate one fresh V1, A, or B packet under a temporary workspace."""
    from business.workflows.quote_pipeline import run_job_quote

    workspace = tmp_path / f"workspace-{variant}"
    if variant == "v1":
        copy_demo_workspace(workspace)
        job, output = JOB_REL, OUTPUT_REL
    elif variant == "a":
        copy_thin_skin_workspace(workspace, "a")
        job, output = JOB_A, OUTPUT_A
    elif variant == "b":
        copy_thin_skin_workspace(workspace, "b")
        job, output = JOB_B, OUTPUT_B
    else:
        raise ValueError(f"unknown packet variant: {variant}")
    return run_job_quote(root=workspace, job=job, output_dir=output).output_dir


def packet_fingerprint(packet: Path) -> dict[str, tuple[object, ...]]:
    """File digests, inodes, and mtimes, plus directory mtimes. Symlinks stay unfollowed."""
    observed: dict[str, tuple[object, ...]] = {}
    for path in sorted(packet.rglob("*")):
        relative = path.relative_to(packet).as_posix()
        info = path.lstat()
        if path.is_symlink():
            observed[relative] = ("symlink", info.st_mtime_ns, info.st_ino)
        elif path.is_dir():
            observed[relative] = ("dir", info.st_mtime_ns, info.st_ino)
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            observed[relative] = ("file", digest, info.st_mtime_ns, info.st_ino)
        else:
            observed[relative] = ("other", info.st_mode, info.st_mtime_ns, info.st_ino)
    return observed


def copy_saved_packet(template: Path, dest: Path) -> Path:
    """Copy a generated packet without following links inside it."""
    shutil.copytree(template, dest, symlinks=True)
    return dest


@pytest.fixture(scope="session")
def generated_packets(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One pristine V1, A, and B packet reused only as a copy source."""
    root = tmp_path_factory.mktemp("generated-packets")
    return {variant: generate_job_packet(root, variant) for variant in ("v1", "a", "b")}


_PHASES = ("inventory", "schemas", "hashes", "source_closure", "replay")


def assert_rejected(
    result: JobQuoteVerification,
    code: str,
    member: str | None,
    phase: str,
) -> None:
    """The first failed phase matches, and every later phase did not run."""
    assert result.result == "invalid"
    assert [(error.code, error.member) for error in result.errors] == [(code, member)]
    if phase == "":
        assert [check.status for check in result.checks] == ["not_run"] * len(_PHASES)
        return
    failed_at = _PHASES.index(phase)
    expected = [
        "pass" if index < failed_at else "fail" if index == failed_at else "not_run"
        for index in range(len(_PHASES))
    ]
    assert [check.status for check in result.checks] == expected


def pristine_copy(generated_packets: dict[str, Path], tmp_path: Path, variant: str) -> Path:
    """Copy one generated packet and require the copy to verify before a mutation."""
    packet = copy_saved_packet(generated_packets[variant], tmp_path / f"packet-{variant}")
    verified = verify_job_quote_packet(packet)
    assert verified.result == "valid"
    assert verified.economic_status == "draft"
    return packet
