"""Round trip, replay, publication, and public-projection tests."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from business.bids.models import BidV1
from business.calculators.machine_cost_basis import as_money, money_equal
from business.workflows.loading import load_job_quote, validate_instance
from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError
from business.workflows.quote_pipeline import build_job_quote_packet, run_job_quote
from tests.workflows.conftest import JOB_REL, OUTPUT_REL, ROOT, SOURCE_RELS, copy_demo_workspace

SENTINEL = "SENTINEL-INTERNAL-PLANT-7f77-PRIVATE"
ESTIMATE_REL = "fixtures/estimates/guitar/cnc_electric_guitar_baseline_input_v1.json"
PRODUCT_REL = "fixtures/products/cnc_electric_guitar_baseline_v1.json"


def _run(workspace: Path, output_rel: str = OUTPUT_REL):
    return run_job_quote(root=workspace, job=JOB_REL, output_dir=output_rel)


def _read(packet: Path, rel: str) -> dict:
    return json.loads((packet / rel).read_text(encoding="utf-8"))


def test_baseline_round_trip_matches_the_governed_totals(workspace: Path) -> None:
    before = {rel: (workspace / rel).read_bytes() for rel in SOURCE_RELS}
    result = _run(workspace)
    packet = result.output_dir
    assert result.status == "draft"
    assert result.direct_manufacturing_cost == 924.09
    assert result.quote_price == 1320.13
    assert {rel: (workspace / rel).read_bytes() for rel in SOURCE_RELS} == before

    estimate = _read(packet, "internal/estimate.json")
    bid = _read(packet, "internal/bid.json")
    summary = _read(packet, "internal/bid_summary.json")
    proposal = _read(packet, "customer/proposal.json")
    manifest = _read(packet, "manifest.json")
    for payload, schema, label in (
        (estimate, "estimates/guitar_build_estimate_v1.schema.json", "estimate"),
        (bid, "bids/bid_v1.schema.json", "bid"),
        (summary, "bids/bid_summary_v1.schema.json", "summary"),
        (proposal, "proposals/proposal_v1.schema.json", "proposal"),
        (manifest, "workflows/job_quote_manifest_v1.schema.json", "manifest"),
    ):
        validate_instance(payload, schema, label=label)

    costs = estimate["cost_summary"]
    assert costs["total_direct_manufacturing_cost"] == 924.09
    material = (
        costs["wood_material_cost"]
        + costs["hardware_cost"]
        + costs["electronics_cost"]
        + costs["consumables_cost"]
        + costs["scrap_allowance"]
    )
    assert material == 432.0
    assert costs["wood_material_cost"] == 115.0
    assert costs["hardware_cost"] == 125.0
    assert costs["electronics_cost"] == 110.0
    assert costs["consumables_cost"] == 75.0
    assert costs["scrap_allowance"] == 7.0
    base = (
        bid["cost_basis"]["direct_material_cost"]
        + bid["cost_basis"]["direct_labor_cost"]
        + bid["cost_basis"]["machine_time_cost"]
        + bid["cost_basis"]["setup_cost"]
        + bid["cost_basis"]["finishing_cost"]
    )
    assert as_money(base) == 924.09
    assert bid["cost_basis"]["base_manufacturing_cost"] == 924.09
    assert bid["cost_basis"]["direct_material_cost"] == 432.0
    assert bid["cost_basis"]["direct_labor_cost"] == 251.55
    assert bid["cost_basis"]["machine_time_cost"] == 125.54
    assert bid["cost_basis"]["setup_cost"] == 31.14
    assert bid["cost_basis"]["finishing_cost"] == 83.86
    for field in ("tooling_cost", "finishing_material_cost", "engineering_cost"):
        assert bid["cost_basis"][field] == 0.0
    for field in (
        "tool_wear_pct",
        "manufacturing_contingency_pct",
        "business_overhead_pct",
        "engineering_recovery_pct",
    ):
        assert bid["pricing"][field] == 0.0
    assert bid["pricing"]["risked_cost"] == 924.09
    assert bid["pricing"]["quote_price"] == 1320.13
    assert bid["pricing"]["price_per_unit"] == 1320.13
    assert bid["pricing"]["quantity"] == 1
    machine = bid["machine_costing"]
    assert machine["runtime_minutes"] == 260.0
    assert machine["machine_hour_rate"] == 28.97
    assert machine["derived_machine_time_cost"] == 125.54
    assert money_equal(machine["derived_machine_time_cost"], bid["cost_basis"]["machine_time_cost"])
    assert summary["canonical_quote_price"] == 1320.13
    assert proposal["pricing"]["total_price"] == 1320.13
    assert proposal["status"] == "draft"
    assert estimate["status"] == "draft"
    assert bid["status"] == "draft"
    assert manifest["status"] == "draft"
    assert bid["manufacturing_ref"] == "internal/estimate.json"
    assert manifest["reference_namespaces"]["packet_refs"]["manufacturing_ref"] == (
        "internal/estimate.json"
    )
    assert manifest["reference_namespaces"]["source_refs"]["snapshot_root"] == "internal/sources"
    assert all(entry["path"] != "manifest.json" for entry in manifest["artifacts"])


def test_public_projection_keeps_internal_text_internal(workspace: Path) -> None:
    estimate = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    estimate["provenance"]["note"] = SENTINEL
    (workspace / ESTIMATE_REL).write_text(json.dumps(estimate, indent=2) + "\n", encoding="utf-8")
    job = json.loads((workspace / JOB_REL).read_text(encoding="utf-8"))
    job["internal_notes"].append(SENTINEL)
    (workspace / JOB_REL).write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    packet = _run(workspace).output_dir
    customer_json = (packet / "customer" / "proposal.json").read_text(encoding="utf-8")
    customer_md = (packet / "customer" / "proposal.md").read_text(encoding="utf-8")
    customer = customer_json + "\n" + customer_md
    internal = "\n".join(
        (packet / rel).read_text(encoding="utf-8")
        for rel in (
            "internal/bid.json",
            "internal/cost_report.md",
            "internal/estimate.json",
            f"internal/sources/{ESTIMATE_REL}",
        )
    )
    assert SENTINEL in internal
    assert SENTINEL not in customer
    for private in (
        "target_margin",
        "machine_hour_rate",
        "28.97",
        "28.75",
        "23.00",
        "924.09",
        "risked_cost",
        "tool_wear",
        "fixtures/machines",
        "fixtures/estimates",
        "Packaging for safe transport",
        "Authorized Signature",
        "Direct-cost-based preliminary pricing",
        "INTERNAL-DEMO synthetic request",
    ):
        assert private not in customer
    proposal = json.loads(customer_json)
    assert proposal["source_summary_ref"] is None
    assert proposal["project_ref"] is None
    assert proposal["status"] == "draft"
    assert proposal["exclusions"] == job["customer_exclusions"]
    deliverables = next(
        section for section in proposal["sections"] if section["title"] == "Deliverables"
    )
    exclusions = next(
        section for section in proposal["sections"] if section["title"] == "Exclusions"
    )
    assert deliverables["bullets"] == job["customer_deliverables"]
    assert exclusions["bullets"] == job["customer_exclusions"]
    assert "DRAFT FOR REVIEW" in customer_md
    assert "1,320.13" in customer_md
    assert "INTERNAL-DEMO" in customer_md


def test_reviewed_input_does_not_approve_the_price(workspace: Path) -> None:
    estimate = json.loads((workspace / ESTIMATE_REL).read_text(encoding="utf-8"))
    estimate["status"] = "approved"
    estimate["provenance"]["confidence"] = "approved"
    (workspace / ESTIMATE_REL).write_text(json.dumps(estimate, indent=2) + "\n", encoding="utf-8")
    packet = _run(workspace).output_dir
    produced = _read(packet, "internal/estimate.json")
    proposal = _read(packet, "customer/proposal.json")
    bid = _read(packet, "internal/bid.json")
    assert produced["status"] == "draft"
    assert produced["provenance"]["confidence"] == "approved"
    assert proposal["status"] == "draft"
    assert bid["status"] == "draft"
    markdown = (packet / "customer" / "proposal.md").read_text(encoding="utf-8")
    assert "Authorized Signature" not in markdown


def test_zero_margin_quotes_the_direct_cost(workspace: Path) -> None:
    job = json.loads((workspace / JOB_REL).read_text(encoding="utf-8"))
    job["pricing_policy"]["target_margin_pct"] = 0
    (workspace / JOB_REL).write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    result = _run(workspace)
    assert result.direct_manufacturing_cost == 924.09
    assert result.quote_price == 924.09


def test_replay_is_byte_identical_and_digests_match(tmp_path: Path) -> None:
    first = copy_demo_workspace(tmp_path / "a")
    second = copy_demo_workspace(tmp_path / "b")
    left = _run(first).output_dir
    right = _run(second).output_dir
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
        original = (first / source["original_ref"]).read_bytes()
        assert copied == original
        assert hashlib.sha256(copied).hexdigest() == source["sha256"]
    for artifact in manifest["artifacts"]:
        raw = (left / artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]


def test_changed_source_bytes_change_the_recorded_digest(tmp_path: Path) -> None:
    original = copy_demo_workspace(tmp_path / "original")
    changed = copy_demo_workspace(tmp_path / "changed")
    product = json.loads((changed / PRODUCT_REL).read_text(encoding="utf-8"))
    product["notes"].append("digest-change-only")
    (changed / PRODUCT_REL).write_text(json.dumps(product) + "\n", encoding="utf-8")
    left = _read(_run(original).output_dir, "manifest.json")
    right = _read(_run(changed).output_dir, "manifest.json")
    left_product = next(item for item in left["sources"] if item["role"] == "product")
    right_product = next(item for item in right["sources"] if item["role"] == "product")
    assert left_product["sha256"] != right_product["sha256"]
    assert left["pricing_policy"]["target_margin_pct"] == right["pricing_policy"][
        "target_margin_pct"
    ]


def test_calculation_uses_captured_snapshot_bytes(workspace: Path) -> None:
    loaded = load_job_quote(workspace, JOB_REL)
    estimate_path = workspace / ESTIMATE_REL
    original = estimate_path.read_bytes()
    mutated = original.replace(
        b"Baseline draft inputs for internal manufacturing-cost modeling only.",
        b"MUTATED-AFTER-SNAPSHOT sentinel that must not be calculated.",
    )
    assert mutated != original
    estimate_path.write_bytes(mutated)
    packet = build_job_quote_packet(loaded)
    snapshot_rel = f"internal/sources/{ESTIMATE_REL}"
    assert packet.files[snapshot_rel] == original
    assert b"MUTATED-AFTER-SNAPSHOT" not in packet.files["internal/estimate.json"]
    assert b"MUTATED-AFTER-SNAPSHOT" not in packet.files["customer/proposal.md"]


def test_existing_destination_is_refused_without_changing_bytes(workspace: Path) -> None:
    destination = workspace / OUTPUT_REL
    destination.mkdir(parents=True)
    marker = destination / "keep.txt"
    marker.write_bytes(b"unchanged-marker")
    before = marker.read_bytes()
    with pytest.raises(JobQuoteRefusalError):
        _run(workspace)
    assert marker.read_bytes() == before
    assert sorted(path.name for path in destination.iterdir()) == ["keep.txt"]


def test_staging_failure_leaves_no_packet(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("simulated staging failure")

    monkeypatch.setattr("business.workflows.reporting._rename_without_replacement", boom)
    destination = workspace / OUTPUT_REL
    with pytest.raises(JobQuoteFailureError):
        _run(workspace)
    assert not destination.exists()
    parent = destination.parent
    if parent.exists():
        assert list(parent.glob(".job-quote-*")) == []


@pytest.mark.parametrize("kind", ["empty_directory", "file", "symlink"])
def test_destination_created_during_publication_is_not_replaced(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from business.workflows import reporting

    real_rename = reporting._rename_without_replacement
    destination = workspace / OUTPUT_REL
    identity = []

    def raced_rename(source: Path, target: Path) -> None:
        if kind == "empty_directory":
            target.mkdir()
        elif kind == "file":
            target.write_bytes(b"concurrently created file")
        else:
            target.symlink_to(workspace / "other-target")
        identity.append(target.lstat())
        real_rename(source, target)

    monkeypatch.setattr(reporting, "_rename_without_replacement", raced_rename)
    with pytest.raises(JobQuoteRefusalError, match="already exists"):
        _run(workspace)
    assert destination.lstat().st_ino == identity[0].st_ino
    if kind == "empty_directory":
        assert list(destination.iterdir()) == []
    elif kind == "file":
        assert destination.read_bytes() == b"concurrently created file"
    else:
        assert destination.is_symlink()
        assert not (workspace / "other-target").exists()
    assert list(destination.parent.glob(".job-quote-*")) == []


def test_output_outside_root_and_symlink_are_refused(workspace: Path, tmp_path: Path) -> None:
    with pytest.raises(JobQuoteRefusalError):
        run_job_quote(root=workspace, job=JOB_REL, output_dir=tmp_path / "outside")
    assert not (tmp_path / "outside").exists()

    parent = workspace / "exports" / "jobs"
    parent.mkdir(parents=True)
    link = parent / "linked-out"
    link.symlink_to(tmp_path / "linked-target")
    with pytest.raises(JobQuoteRefusalError):
        run_job_quote(root=workspace, job=JOB_REL, output_dir="exports/jobs/linked-out")
    assert not (tmp_path / "linked-target").exists()


def test_unavailable_exclusive_rename_fails_without_a_partial_packet(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from business.workflows import reporting

    if reporting.os.name == "nt":
        pytest.skip("Windows os.rename already provides no-replacement semantics")
    monkeypatch.setattr(reporting.ctypes, "CDLL", lambda *_args, **_kwargs: object())
    with pytest.raises(JobQuoteFailureError, match="exclusive directory rename is unavailable"):
        _run(workspace)
    destination = workspace / OUTPUT_REL
    assert not destination.exists()
    assert list(destination.parent.glob(".job-quote-*")) == []


def test_generated_validation_failure_publishes_nothing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from business.workflows import reporting

    original = reporting.bid_payload

    def broken(bid: BidV1):
        payload = original(bid)
        del payload["bid_id"]
        return payload

    monkeypatch.setattr("business.workflows.quote_pipeline.bid_payload", broken)
    with pytest.raises(JobQuoteFailureError):
        _run(workspace)
    assert not (workspace / OUTPUT_REL).exists()


def test_business_workflow_does_not_import_cam_rmos_or_saw() -> None:
    forbidden = {"cam_assist", "cam", "rmos", "saw_lab", "saw"}
    roots = [ROOT / "business" / "workflows"]
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    assert module.split(".")[0] not in forbidden
