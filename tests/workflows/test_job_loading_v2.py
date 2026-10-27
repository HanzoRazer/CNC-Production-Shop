"""Strict refusals for thin-skin job quote admission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from business.workflows.loading import load_job_quote
from business.workflows.models import JobQuoteRefusalError, JobQuoteRequestV1, JobQuoteRequestV2
from business.workflows.quote_pipeline import run_job_quote
from tests.workflows.conftest import (
    ESTIMATE_A,
    JOB_A,
    JOB_REL,
    OUTPUT_A,
    ROOT,
    copy_demo_workspace,
    copy_thin_skin_workspace,
)

PROFILE = "fixtures/equipment/vacuum_press_v1.json"
BASIS = "fixtures/equipment/cost_basis/vacuum_press_cost_basis_v1.json"
MACHINE_BASIS = "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json"


def _job(workspace: Path) -> dict:
    return json.loads((workspace / JOB_A).read_text(encoding="utf-8"))


def _write(workspace: Path, rel: str, payload: dict) -> None:
    (workspace / rel).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _estimate(workspace: Path) -> dict:
    return json.loads((workspace / ESTIMATE_A).read_text(encoding="utf-8"))


def _assert_no_packet(workspace: Path, job: str = JOB_A) -> None:
    destination = workspace / OUTPUT_A
    with pytest.raises(JobQuoteRefusalError):
        run_job_quote(root=workspace, job=job, output_dir=OUTPUT_A)
    assert not destination.exists()


def test_variant_a_loads_eleven_sources_in_equipment_id_order(thin_skin_workspace: Path) -> None:
    loaded = load_job_quote(thin_skin_workspace, JOB_A)
    assert isinstance(loaded.request, JobQuoteRequestV2)
    assert loaded.request.effective_date == "2026-10-26"
    assert loaded.request.estimate_input_contract == "thin_skin_estimate_input_v2"
    assert [source.role for source in loaded.sources] == [
        "job_request",
        "estimate_input",
        "product",
        "machine_profile",
        "machine_cost_basis",
        "equipment_profile",
        "equipment_cost_basis",
        "equipment_profile",
        "equipment_cost_basis",
        "equipment_profile",
        "equipment_cost_basis",
    ]
    assert [source.record_id for source in loaded.sources[5::2]] == [
        "EQUIPMENT-CURE-RACK-V1",
        "EQUIPMENT-SPRAY-BOOTH-V1",
        "EQUIPMENT-VACUUM-PRESS-V1",
    ]


def test_fixture_suffix_does_not_select_the_contract(tmp_path: Path) -> None:
    v2_workspace = copy_thin_skin_workspace(tmp_path / "v2", "a")
    renamed = "fixtures/jobs/renamed_input_v1.json"
    (v2_workspace / renamed).write_bytes((v2_workspace / JOB_A).read_bytes())
    loaded = load_job_quote(v2_workspace, renamed)
    assert isinstance(loaded.request, JobQuoteRequestV2)

    v1_workspace = copy_demo_workspace(tmp_path / "v1")
    v1_renamed = "fixtures/jobs/renamed_request_v2.json"
    (v1_workspace / v1_renamed).write_bytes((v1_workspace / JOB_REL).read_bytes())
    v1_loaded = load_job_quote(v1_workspace, v1_renamed)
    assert isinstance(v1_loaded.request, JobQuoteRequestV1)
    assert v1_loaded.request.estimate_input_contract == "guitar_estimate_input_v1"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update({"record_version": "1.0.0"}),
        lambda payload: payload.update({"record_version": "9.0.0"}),
        lambda payload: payload.update({"estimate_input_contract": "guitar_estimate_input_v1"}),
        lambda payload: payload.update({"estimate_input_contract": "unknown_contract"}),
        lambda payload: payload.update({"quantity": 0}),
        lambda payload: payload.update({"quantity": 2}),
        lambda payload: payload.update({"currency": "EUR"}),
        lambda payload: payload.update({"extra_field": "no"}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": True}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": -1}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": 100}),
        lambda payload: payload.update({"created_at": "2026-10-26T16:00:00+00:00"}),
        lambda payload: payload.update({"estimate_id": "GUITAR-BUILD-ESTIMATE-DEMO-001"}),
    ],
)
def test_request_pair_and_shape_are_refused(thin_skin_workspace: Path, mutator) -> None:
    payload = _job(thin_skin_workspace)
    mutator(payload)
    _write(thin_skin_workspace, JOB_A, payload)
    _assert_no_packet(thin_skin_workspace)


def test_duplicate_key_boolean_and_nonfinite_json_are_refused(thin_skin_workspace: Path) -> None:
    text = (thin_skin_workspace / JOB_A).read_text(encoding="utf-8")
    duplicated = text.replace(
        '"job_id": "JOB-THIN-SKIN-A-DEMO-001"',
        '"job_id": "JOB-THIN-SKIN-A-DEMO-001", "job_id": "JOB-OTHER"',
        1,
    )
    (thin_skin_workspace / JOB_A).write_text(duplicated, encoding="utf-8")
    _assert_no_packet(thin_skin_workspace)

    restored = json.loads(text)
    _write(thin_skin_workspace, JOB_A, restored)
    nan = text.replace('"target_margin_pct": 30', '"target_margin_pct": NaN', 1)
    (thin_skin_workspace / JOB_A).write_text(nan, encoding="utf-8")
    _assert_no_packet(thin_skin_workspace)

    basis = json.loads((thin_skin_workspace / BASIS).read_text(encoding="utf-8"))
    basis["equipment_hour_rate"] = True
    _write(thin_skin_workspace, BASIS, basis)
    (thin_skin_workspace / JOB_A).write_text(text, encoding="utf-8")
    _assert_no_packet(thin_skin_workspace)


def test_quantity_currency_and_identity_mismatches_are_refused(thin_skin_workspace: Path) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["quantity"] = 2
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    estimate["quantity"] = 1
    estimate["currency"] = "EUR"
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    estimate["currency"] = "USD"
    estimate["operations"][1]["operation_id"] = estimate["operations"][0]["operation_id"]
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_duplicate_and_undeclared_equipment_are_refused(thin_skin_workspace: Path) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["equipment_refs"].append(dict(estimate["equipment_refs"][0]))
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    estimate = _estimate(thin_skin_workspace)
    estimate["operations"][0]["equipment_id"] = "EQUIPMENT-NOT-DECLARED-V1"
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    estimate = _estimate(thin_skin_workspace)
    occupied = next(
        operation
        for operation in estimate["operations"]
        if operation["time_model"]["equipment_occupancy_minutes"] > 0
    )
    occupied["equipment_id"] = ""
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_duplicate_input_and_inconsistent_rates_are_refused(thin_skin_workspace: Path) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["material_inputs"][1]["input_id"] = estimate["material_inputs"][0]["input_id"]
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    estimate = _estimate(thin_skin_workspace)
    estimate["labor_rate_inputs"][0]["loaded_rate_per_hour"] = 1.0
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)

    machine = json.loads((thin_skin_workspace / MACHINE_BASIS).read_text(encoding="utf-8"))
    machine["machine_hour_rate"] = 1.0
    _write(thin_skin_workspace, MACHINE_BASIS, machine)
    _assert_no_packet(thin_skin_workspace)

    recorded = json.loads((ROOT / MACHINE_BASIS).read_text(encoding="utf-8"))
    machine["machine_hour_rate"] = recorded["machine_hour_rate"]
    _write(thin_skin_workspace, MACHINE_BASIS, machine)
    basis = json.loads((thin_skin_workspace / BASIS).read_text(encoding="utf-8"))
    basis["equipment_hour_rate"] = 9.99
    _write(thin_skin_workspace, BASIS, basis)
    _assert_no_packet(thin_skin_workspace)

    basis = json.loads((ROOT / BASIS).read_text(encoding="utf-8"))
    basis["electricity"]["electricity_cost_per_hour"] = 5
    _write(thin_skin_workspace, BASIS, basis)
    _assert_no_packet(thin_skin_workspace)

    basis = json.loads((ROOT / BASIS).read_text(encoding="utf-8"))
    basis["currency"] = "EUR"
    _write(thin_skin_workspace, BASIS, basis)
    _assert_no_packet(thin_skin_workspace)

    basis = json.loads((ROOT / BASIS).read_text(encoding="utf-8"))
    _write(thin_skin_workspace, BASIS, basis)
    profile = json.loads((thin_skin_workspace / PROFILE).read_text(encoding="utf-8"))
    profile["connected_load_estimate"]["total_kw"] = 9
    _write(thin_skin_workspace, PROFILE, profile)
    _assert_no_packet(thin_skin_workspace)


@pytest.mark.parametrize(
    "ref",
    ["/etc/passwd", "../secret.json", "https://example.com/equipment.json"],
)
def test_equipment_reference_paths_are_confined(thin_skin_workspace: Path, ref: str) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["equipment_refs"][0]["equipment_profile_ref"] = ref
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_equipment_symlink_escape_is_refused(thin_skin_workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = thin_skin_workspace / "fixtures" / "equipment" / "escaped.json"
    link.symlink_to(outside)
    estimate = _estimate(thin_skin_workspace)
    estimate["equipment_refs"][0]["equipment_profile_ref"] = "fixtures/equipment/escaped.json"
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_one_file_cannot_fill_two_roles(thin_skin_workspace: Path) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["equipment_refs"][0]["equipment_profile_ref"] = estimate["machine_profile_ref"]
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_missing_equipment_file_is_refused_before_a_packet(thin_skin_workspace: Path) -> None:
    estimate = _estimate(thin_skin_workspace)
    estimate["equipment_refs"][0]["equipment_profile_ref"] = "fixtures/equipment/missing.json"
    _write(thin_skin_workspace, ESTIMATE_A, estimate)
    _assert_no_packet(thin_skin_workspace)


def test_refs_resolve_against_root_not_the_job_directory(thin_skin_workspace: Path) -> None:
    nested = thin_skin_workspace / "nested"
    nested.mkdir()
    moved = nested / "request.json"
    moved.write_bytes((thin_skin_workspace / JOB_A).read_bytes())
    loaded = load_job_quote(thin_skin_workspace, "nested/request.json")
    assert loaded.request.estimate_input_ref.startswith("fixtures/")
