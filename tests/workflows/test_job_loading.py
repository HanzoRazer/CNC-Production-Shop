"""Strict refusals for job quote inputs. A refusal publishes no packet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from business.workflows.loading import load_job_quote
from business.workflows.models import JobQuoteRefusalError
from business.workflows.quote_pipeline import run_job_quote
from tests.workflows.conftest import JOB_REL, OUTPUT_REL

ESTIMATE_REL = "fixtures/estimates/guitar/cnc_electric_guitar_baseline_input_v1.json"
PRODUCT_REL = "fixtures/products/cnc_electric_guitar_baseline_v1.json"
BASIS_REL = "fixtures/machines/cost_basis/bcm_2030ca_atc_cost_basis_v1.json"


def _job(workspace: Path) -> dict:
    return json.loads((workspace / JOB_REL).read_text(encoding="utf-8"))


def _write_job(workspace: Path, payload: dict) -> None:
    (workspace / JOB_REL).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_json(workspace: Path, rel: str, payload: dict) -> None:
    (workspace / rel).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _assert_no_packet(workspace: Path) -> None:
    destination = workspace / OUTPUT_REL
    with pytest.raises(JobQuoteRefusalError):
        run_job_quote(root=workspace, job=JOB_REL, output_dir=OUTPUT_REL)
    assert not destination.exists()


def test_demo_request_loads(workspace: Path) -> None:
    loaded = load_job_quote(workspace, JOB_REL)
    assert loaded.request.job_id == "JOB-CNC-QUOTE-DEMO-001"
    assert loaded.request.quantity == 1
    assert loaded.request.currency == "USD"
    assert loaded.request.effective_date == "2026-10-25"
    assert loaded.request.pricing_policy.target_margin_pct == 30.0
    assert [source.role for source in loaded.sources] == [
        "job_request",
        "estimate_input",
        "product",
        "machine_profile",
        "machine_cost_basis",
    ]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("job_id"),
        lambda payload: payload.update({"ship_to": "nowhere"}),
        lambda payload: payload.update({"record_version": "2.0.0"}),
        lambda payload: payload.update({"estimate_input_contract": "thin_skin_estimate_input_v2"}),
        lambda payload: payload.update({"quantity": 0}),
        lambda payload: payload.update({"quantity": 2}),
        lambda payload: payload.update({"quantity": True}),
        lambda payload: payload.update({"currency": "EUR"}),
        lambda payload: payload.update({"job_id": "   "}),
        lambda payload: payload.update({"job_id": "job id"}),
        lambda payload: payload.update({"revision": "   "}),
        lambda payload: payload.update({"created_at": "2026-10-25T16:00:00+00:00"}),
        lambda payload: payload.update({"created_at": "2026-02-31T00:00:00Z"}),
        lambda payload: payload.update({"estimate_input_ref": "/etc/passwd"}),
        lambda payload: payload.update({"estimate_input_ref": "../secret.json"}),
        lambda payload: payload.update({"estimate_input_ref": "https://example.com/job.json"}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": True}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": -1}),
        lambda payload: payload["pricing_policy"].update({"target_margin_pct": 100}),
        lambda payload: payload["pricing_policy"].update({"tool_wear_pct": 5}),
    ],
)
def test_request_shape_is_refused_without_a_packet(workspace: Path, mutator) -> None:
    payload = _job(workspace)
    mutator(payload)
    _write_job(workspace, payload)
    _assert_no_packet(workspace)


def test_malformed_json_is_refused(workspace: Path) -> None:
    (workspace / JOB_REL).write_text("{", encoding="utf-8")
    _assert_no_packet(workspace)


def test_duplicate_json_key_is_refused(workspace: Path) -> None:
    text = (workspace / JOB_REL).read_text(encoding="utf-8")
    text = text.replace('"job_id"', '"job_id"', 1)
    duplicated = text.replace(
        '"job_id": "JOB-CNC-QUOTE-DEMO-001"',
        '"job_id": "JOB-CNC-QUOTE-DEMO-001", "job_id": "JOB-OTHER"',
        1,
    )
    (workspace / JOB_REL).write_text(duplicated, encoding="utf-8")
    _assert_no_packet(workspace)


def test_nonfinite_json_constant_is_refused(workspace: Path) -> None:
    text = (workspace / JOB_REL).read_text(encoding="utf-8")
    text = text.replace('"target_margin_pct": 30', '"target_margin_pct": NaN', 1)
    (workspace / JOB_REL).write_text(text, encoding="utf-8")
    _assert_no_packet(workspace)


def test_infinity_constant_is_refused(workspace: Path) -> None:
    text = (workspace / JOB_REL).read_text(encoding="utf-8")
    text = text.replace('"target_margin_pct": 30', '"target_margin_pct": Infinity', 1)
    (workspace / JOB_REL).write_text(text, encoding="utf-8")
    _assert_no_packet(workspace)


def test_boolean_numeric_in_estimate_input_is_refused(workspace: Path) -> None:
    payload = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    payload["material_inputs"][0]["unit_cost"] = True
    _write_json(workspace, ESTIMATE_REL, payload)
    _assert_no_packet(workspace)


def test_quantity_and_currency_mismatch_are_refused(workspace: Path) -> None:
    payload = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    payload["quantity"] = 2
    _write_json(workspace, ESTIMATE_REL, payload)
    _assert_no_packet(workspace)

    payload["quantity"] = 1
    payload["currency"] = "EUR"
    _write_json(workspace, ESTIMATE_REL, payload)
    _assert_no_packet(workspace)


def test_missing_product_and_mismatched_ids_are_refused(workspace: Path) -> None:
    estimate = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    estimate["product_ref"] = "fixtures/products/missing-product.json"
    _write_json(workspace, ESTIMATE_REL, estimate)
    _assert_no_packet(workspace)

    estimate["product_ref"] = PRODUCT_REL
    _write_json(workspace, ESTIMATE_REL, estimate)
    product = json.loads((workspace / PRODUCT_REL).read_text(encoding="utf-8"))
    product["product_id"] = "PRODUCT-OTHER-V1"
    _write_json(workspace, PRODUCT_REL, product)
    _assert_no_packet(workspace)


def test_inconsistent_labor_rate_is_refused(workspace: Path) -> None:
    estimate = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    estimate["labor_rate_inputs"][0]["loaded_rate_per_hour"] = 1.0
    _write_json(workspace, ESTIMATE_REL, estimate)
    _assert_no_packet(workspace)


def test_inconsistent_machine_hour_rate_is_refused(workspace: Path) -> None:
    basis = json.loads((workspace / BASIS_REL).read_text(encoding="utf-8"))
    basis["machine_hour_rate"] = 72.0
    _write_json(workspace, BASIS_REL, basis)
    _assert_no_packet(workspace)


def test_escaping_symlink_is_refused(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = workspace / "fixtures" / "escaped.json"
    link.symlink_to(outside)
    payload = _job(workspace)
    payload["estimate_input_ref"] = "fixtures/escaped.json"
    _write_job(workspace, payload)
    _assert_no_packet(workspace)


def test_refs_resolve_against_root_not_the_job_directory(workspace: Path) -> None:
    nested = workspace / "nested"
    nested.mkdir()
    moved = nested / "request.json"
    moved.write_bytes((workspace / JOB_REL).read_bytes())
    loaded_from_root = load_job_quote(workspace, "nested/request.json")
    assert loaded_from_root.request.estimate_input_ref.startswith("fixtures/")
