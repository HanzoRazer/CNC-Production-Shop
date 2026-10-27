"""Thin-skin quote packets: oracles, replay, privacy, and publication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from business.bids.models_v2 import BidV2
from business.calculators.machine_cost_basis import money_equal
from business.workflows.loading import load_job_quote, validate_instance
from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError
from business.workflows.quote_pipeline import build_job_quote_packet, run_job_quote
from tests.workflows.conftest import (
    ESTIMATE_A,
    JOB_A,
    JOB_B,
    OUTPUT_A,
    OUTPUT_B,
    copy_thin_skin_workspace,
    thin_skin_source_rels,
)

CANARY_INTERNAL = "CANARY-INTERNAL-002-PRIVATE"
CANARY_ESTIMATE = "CANARY-ESTIMATE-002-PRIVATE"
CANARY_AUDIT = "CANARY-AUDIT-002-PRIVATE"
SHARED = {
    "machine_time_cost": 46.35,
    "equipment_occupancy_cost": 12.13,
    "setup_cost": 36.89,
    "finishing_cost": 75.23,
    "finishing_material_cost": 53.50,
    "cnc_minutes": 96.0,
    "occupancy_minutes": 3050.0,
}


def _read(packet: Path, rel: str) -> dict:
    return json.loads((packet / rel).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    (
        "variant",
        "job",
        "output",
        "cost",
        "price",
        "material",
        "labor",
        "reserve",
        "labor_min",
        "wait",
    ),
    [
        ("a", JOB_A, OUTPUT_A, 700.89, 1001.27, 234.40, 201.25, 41.14, 654.0, 315.0),
        ("b", JOB_B, OUTPUT_B, 730.59, 1043.70, 247.56, 215.15, 43.78, 683.0, 555.0),
    ],
)
def test_variant_round_trip_matches_recomputed_oracles(
    tmp_path: Path,
    variant: str,
    job: str,
    output: str,
    cost: float,
    price: float,
    material: float,
    labor: float,
    reserve: float,
    labor_min: float,
    wait: float,
) -> None:
    workspace = copy_thin_skin_workspace(tmp_path / variant, variant)
    before = {rel: (workspace / rel).read_bytes() for rel in thin_skin_source_rels(variant)}
    result = run_job_quote(root=workspace, job=job, output_dir=output)
    packet = result.output_dir
    assert result.status == "draft"
    assert result.direct_manufacturing_cost == cost
    assert result.quote_price == price
    assert {rel: (workspace / rel).read_bytes() for rel in thin_skin_source_rels(variant)} == before

    estimate = _read(packet, "internal/estimate.json")
    bid = _read(packet, "internal/bid.json")
    summary = _read(packet, "internal/bid_summary.json")
    proposal = _read(packet, "customer/proposal.json")
    manifest = _read(packet, "manifest.json")
    for payload, schema, label in (
        (estimate, "estimates/thin_skin_build_estimate_v2.schema.json", "estimate"),
        (bid, "bids/bid_v2.schema.json", "bid"),
        (summary, "bids/bid_summary_v1.schema.json", "summary"),
        (proposal, "proposals/proposal_v1.schema.json", "proposal"),
        (manifest, "workflows/job_quote_manifest_v2.schema.json", "manifest"),
    ):
        validate_instance(payload, schema, label=label)
    with pytest.raises(JobQuoteRefusalError):
        validate_instance(bid, "bids/bid_v1.schema.json", label="bid")

    basis = bid["cost_basis"]
    assert basis["direct_material_cost"] == material
    assert basis["direct_labor_cost"] == labor
    assert basis["machine_time_cost"] == SHARED["machine_time_cost"]
    assert basis["equipment_occupancy_cost"] == SHARED["equipment_occupancy_cost"]
    assert basis["setup_cost"] == SHARED["setup_cost"]
    assert basis["finishing_cost"] == SHARED["finishing_cost"]
    assert basis["finishing_material_cost"] == SHARED["finishing_material_cost"]
    assert basis["process_rework_and_yield_reserve"] == reserve
    assert basis["tooling_cost"] == 0
    assert basis["engineering_cost"] == 0
    assert basis["base_manufacturing_cost"] == cost
    assert bid["pricing"]["risked_cost"] == cost
    assert bid["pricing"]["quote_price"] == price
    assert bid["pricing"]["price_per_unit"] == price
    for field in (
        "tool_wear_pct",
        "manufacturing_contingency_pct",
        "business_overhead_pct",
        "engineering_recovery_pct",
    ):
        assert bid["pricing"][field] == 0
    categories = [item["category"] for item in bid["line_items"]]
    assert len(categories) == 17 and len(set(categories)) == 17
    assert categories.count("material_scrap_allowance") == 1
    assert categories.count("process_rework_and_yield_reserve") == 1
    assert "total_direct_manufacturing_cost" not in categories
    assert summary["canonical_quote_price"] == price
    assert [item["category"] for item in summary["line_items"]] == categories
    assert proposal["pricing"]["total_price"] == price
    assert proposal["status"] == "draft"
    assert estimate["status"] == "draft"
    assert estimate["provenance"]["confidence"] == "draft"
    times = estimate["time_summary"]
    assert times["total_labor_minutes"] == labor_min
    assert times["total_machine_runtime_minutes"] == SHARED["cnc_minutes"]
    assert times["total_equipment_occupancy_minutes"] == SHARED["occupancy_minutes"]
    assert times["total_elapsed_wait_minutes"] == wait
    assert len(bid["equipment_costing"]) == 3
    assert manifest["workflow_version"] == "2.0.0"
    assert manifest["mapping_version"] == "2.0.0"
    assert manifest["calculator_id"] == "thin_skin_build_estimate_v2"
    assert manifest["bid_contract"] == "bid_v2"
    assert manifest["category_mapping"]["rounding_reconciliation"]["difference"] == 0
    assert len(manifest["sources"]) == 11
    assert all(entry["path"] != "manifest.json" for entry in manifest["artifacts"])
    assert money_equal(
        manifest["category_mapping"]["rounding_reconciliation"]["equipment_record_total"],
        SHARED["equipment_occupancy_cost"],
    )


def test_replay_is_byte_identical_and_digests_match(tmp_path: Path) -> None:
    left_root = copy_thin_skin_workspace(tmp_path / "left", "a")
    right_root = copy_thin_skin_workspace(tmp_path / "right", "a")
    left = run_job_quote(root=left_root, job=JOB_A, output_dir=OUTPUT_A).output_dir
    right = run_job_quote(root=right_root, job=JOB_A, output_dir=OUTPUT_A).output_dir
    left_files = sorted(
        path.relative_to(left).as_posix() for path in left.rglob("*") if path.is_file()
    )
    right_files = sorted(
        path.relative_to(right).as_posix() for path in right.rglob("*") if path.is_file()
    )
    assert left_files == right_files
    for rel in left_files:
        assert (left / rel).read_bytes() == (right / rel).read_bytes()
    manifest = _read(left, "manifest.json")
    for source in manifest["sources"]:
        copied = (left / source["snapshot_ref"]).read_bytes()
        original = (left_root / source["original_ref"]).read_bytes()
        assert copied == original
        assert hashlib.sha256(copied).hexdigest() == source["sha256"]
    for artifact in manifest["artifacts"]:
        raw = (left / artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]


def test_calculation_uses_captured_equipment_bytes(thin_skin_workspace: Path) -> None:
    loaded = load_job_quote(thin_skin_workspace, JOB_A)
    basis_rel = "fixtures/equipment/cost_basis/vacuum_press_cost_basis_v1.json"
    basis_path = thin_skin_workspace / basis_rel
    original = basis_path.read_bytes()
    payload = json.loads(original)
    payload["equipment_hour_rate"] = 50
    payload["notes"].append("MUTATED-AFTER-SNAPSHOT")
    basis_path.write_text(json.dumps(payload), encoding="utf-8")
    packet = build_job_quote_packet(loaded)
    snapshot_rel = f"internal/sources/{basis_rel}"
    assert packet.files[snapshot_rel] == original
    assert b"MUTATED-AFTER-SNAPSHOT" not in packet.files["internal/estimate.json"]
    assert packet.direct_manufacturing_cost == 700.89
    bid = json.loads(packet.files["internal/bid.json"])
    assert bid["cost_basis"]["equipment_occupancy_cost"] == 12.13


def test_changed_equipment_bytes_change_only_that_digest(tmp_path: Path) -> None:
    original = copy_thin_skin_workspace(tmp_path / "original", "b")
    changed = copy_thin_skin_workspace(tmp_path / "changed", "b")
    rel = "fixtures/equipment/cure_rack_v1.json"
    payload = json.loads((changed / rel).read_text(encoding="utf-8"))
    payload["notes"].append("digest-change-only")
    (changed / rel).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    left = _read(
        run_job_quote(root=original, job=JOB_B, output_dir=OUTPUT_B).output_dir, "manifest.json"
    )
    right = _read(
        run_job_quote(root=changed, job=JOB_B, output_dir=OUTPUT_B).output_dir, "manifest.json"
    )
    left_rack = next(item for item in left["sources"] if item["original_ref"] == rel)
    right_rack = next(item for item in right["sources"] if item["original_ref"] == rel)
    assert left_rack["sha256"] != right_rack["sha256"]
    unchanged = [
        item["original_ref"]
        for item in left["sources"]
        if item["sha256"]
        == next(
            other["sha256"]
            for other in right["sources"]
            if other["original_ref"] == item["original_ref"]
        )
    ]
    assert rel not in unchanged
    assert len(unchanged) == 10


def test_customer_outputs_hide_internal_canaries(
    thin_skin_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    estimate = json.loads((thin_skin_workspace / ESTIMATE_A).read_text(encoding="utf-8"))
    estimate["notes"].append(CANARY_ESTIMATE)
    (thin_skin_workspace / ESTIMATE_A).write_text(
        json.dumps(estimate, indent=2) + "\n", encoding="utf-8"
    )
    job = json.loads((thin_skin_workspace / JOB_A).read_text(encoding="utf-8"))
    job["internal_notes"].append(CANARY_INTERNAL)
    (thin_skin_workspace / JOB_A).write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    def with_audit_canary(*args, **kwargs):
        from business.workflows.estimate_to_bid_v2 import build_bid_from_thin_skin_estimate

        result = build_bid_from_thin_skin_estimate(*args, **kwargs)
        result.bid.line_items[0] = replace(result.bid.line_items[0], note=CANARY_AUDIT)
        return result

    monkeypatch.setattr(
        "business.workflows.quote_pipeline.build_bid_from_thin_skin_estimate",
        with_audit_canary,
    )
    packet = run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A).output_dir
    customer = (packet / "customer/proposal.json").read_text(encoding="utf-8")
    customer += "\n" + (packet / "customer/proposal.md").read_text(encoding="utf-8")
    internal = "\n".join(
        (packet / rel).read_text(encoding="utf-8")
        for rel in ("internal/bid.json", "internal/estimate.json", "internal/cost_report.md")
    )
    for canary in (CANARY_INTERNAL, CANARY_ESTIMATE, CANARY_AUDIT):
        assert canary in internal
        assert canary not in customer
    for private in (
        "28.97",
        "target_margin",
        "equipment_hour_rate",
        "machine_hour_rate",
        "process_rework",
        "fixtures/equipment",
        "fixtures/estimates",
        "Packaging for safe transport",
        "Authorized Signature",
        "Direct-cost-based preliminary pricing",
    ):
        assert private not in customer
    proposal = json.loads((packet / "customer/proposal.json").read_text(encoding="utf-8"))
    assert proposal["source_summary_ref"] is None
    assert proposal["project_ref"] is None
    assert proposal["exclusions"] == job["customer_exclusions"]
    deliverables = next(
        section for section in proposal["sections"] if section["title"] == "Deliverables"
    )
    assert deliverables["bullets"] == job["customer_deliverables"]
    assert "1,001.27" in customer
    assert "separate price approval" in " ".join(proposal["next_steps"])
    assert "separate manufacturing release" in " ".join(proposal["next_steps"])


def test_approved_input_does_not_approve_the_price(thin_skin_workspace: Path) -> None:
    estimate = json.loads((thin_skin_workspace / ESTIMATE_A).read_text(encoding="utf-8"))
    estimate["status"] = "approved"
    estimate["provenance"]["confidence"] = "approved"
    (thin_skin_workspace / ESTIMATE_A).write_text(
        json.dumps(estimate, indent=2) + "\n", encoding="utf-8"
    )
    packet = run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A).output_dir
    produced = _read(packet, "internal/estimate.json")
    assert produced["status"] == "draft"
    assert produced["provenance"]["confidence"] == "approved"
    assert _read(packet, "internal/bid.json")["status"] == "draft"
    assert _read(packet, "customer/proposal.json")["status"] == "draft"


def test_quoting_does_not_open_a_socket_or_subprocess(
    thin_skin_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args, **_kwargs):
        pytest.fail("quoting must not open connections or launch an external command")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    result = run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    assert result.status == "draft"


def test_existing_destination_is_not_replaced(thin_skin_workspace: Path) -> None:
    destination = thin_skin_workspace / OUTPUT_A
    destination.mkdir(parents=True)
    marker = destination / "keep.txt"
    marker.write_bytes(b"unchanged-marker")
    with pytest.raises(JobQuoteRefusalError):
        run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    assert marker.read_bytes() == b"unchanged-marker"


@pytest.mark.parametrize("kind", ["empty_directory", "file", "symlink"])
def test_destination_created_during_publication_is_not_replaced(
    thin_skin_workspace: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from business.workflows import reporting

    real_rename = reporting._rename_without_replacement
    destination = thin_skin_workspace / OUTPUT_A
    identity = []

    def raced_rename(source: Path, target: Path) -> None:
        if kind == "empty_directory":
            target.mkdir()
        elif kind == "file":
            target.write_bytes(b"concurrently created file")
        else:
            target.symlink_to(thin_skin_workspace / "other-target")
        identity.append(target.lstat())
        real_rename(source, target)

    monkeypatch.setattr(reporting, "_rename_without_replacement", raced_rename)
    with pytest.raises(JobQuoteRefusalError, match="already exists"):
        run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    assert destination.lstat().st_ino == identity[0].st_ino
    assert list(destination.parent.glob(".job-quote-*")) == []


def test_unavailable_exclusive_rename_fails_without_a_partial_packet(
    thin_skin_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from business.workflows import reporting

    if reporting.os.name == "nt":
        pytest.skip("Windows os.rename already provides no-replacement semantics")
    monkeypatch.setattr(reporting.ctypes, "CDLL", lambda *_args, **_kwargs: object())
    with pytest.raises(JobQuoteFailureError, match="exclusive directory rename is unavailable"):
        run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    destination = thin_skin_workspace / OUTPUT_A
    assert not destination.exists()
    assert list(destination.parent.glob(".job-quote-*")) == []


def test_validation_and_render_failures_publish_nothing(
    thin_skin_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from business.workflows import reporting_v2

    original = reporting_v2.bid_payload_v2

    def broken(bid: BidV2):
        payload = original(bid)
        del payload["bid_id"]
        return payload

    monkeypatch.setattr(reporting_v2, "bid_payload_v2", broken)
    with pytest.raises(JobQuoteFailureError):
        run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    assert not (thin_skin_workspace / OUTPUT_A).exists()

    def boom(*_args, **_kwargs):
        raise OSError("simulated render failure")

    monkeypatch.setattr(reporting_v2, "bid_payload_v2", original)
    monkeypatch.setattr(reporting_v2, "render_internal_cost_report_v2", boom)
    with pytest.raises(OSError, match="simulated render failure"):
        run_job_quote(root=thin_skin_workspace, job=JOB_A, output_dir=OUTPUT_A)
    assert not (thin_skin_workspace / OUTPUT_A).exists()
    parent = thin_skin_workspace / "exports" / "jobs"
    if parent.exists():
        assert list(parent.glob(".job-quote-*")) == []
