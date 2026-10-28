"""Replay, relocation, anchors, and economic consistency of saved packets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from business.workflows.loading import resolve_workspace_file, validate_instance
from business.workflows.quote_pipeline import run_job_quote
from business.workflows.reporting import dumps_json
from business.workflows.verification import verify_job_quote_packet
from business.workflows.verification_models import (
    JobQuoteVerification,
    VerificationDiagnostic,
    VerificationOperationalError,
    checks_for,
    verification_payload,
)
from tests.workflows.conftest import (
    JOB_REL,
    ROOT,
    assert_rejected,
    copy_demo_workspace,
    packet_fingerprint,
    pristine_copy,
)

_ORACLES = {
    "v1": ("924.09", "1320.13", "JOB-CNC-QUOTE-DEMO-001"),
    "a": ("700.89", "1001.27", "JOB-THIN-SKIN-A-DEMO-001"),
    "b": ("730.59", "1043.70", "JOB-THIN-SKIN-B-DEMO-001"),
}
_RESULT_SCHEMA = "workflows/job_quote_verification_v1.schema.json"


def _manifest(packet: Path) -> dict[str, object]:
    return json.loads((packet / "manifest.json").read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def _rehash(packet: Path) -> None:
    manifest = _manifest(packet)
    artifacts = manifest["artifacts"]
    sources = manifest["sources"]
    assert isinstance(artifacts, list) and isinstance(sources, list)
    for entry in artifacts:
        assert isinstance(entry, dict)
        entry["sha256"] = hashlib.sha256((packet / str(entry["path"])).read_bytes()).hexdigest()
    for entry in sources:
        assert isinstance(entry, dict)
        relative = str(entry["snapshot_ref"])
        entry["sha256"] = hashlib.sha256((packet / relative).read_bytes()).hexdigest()
    _write_json(packet / "manifest.json", manifest)


def _reject(packet: Path, code: str, member: str | None, phase: str):
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(packet)
    assert_rejected(result, code, member, phase)
    assert packet_fingerprint(packet) == before
    rendered = json.dumps(verification_payload(result))
    assert "924.09" not in rendered
    assert "1320.13" not in rendered
    return result


def _job_files(packet: Path) -> list[Path]:
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    job = next(row for row in sources if isinstance(row, dict) and row["role"] == "job_request")
    return [packet / "internal" / "job_request.json", packet / str(job["snapshot_ref"])]


def _source(packet: Path, role: str, token: str) -> dict[str, object]:
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    return next(
        row
        for row in sources
        if isinstance(row, dict) and row["role"] == role and token in str(row["original_ref"])
    )


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
def test_current_packets_verify_and_keep_draft_oracles_out_of_the_result(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    first = verify_job_quote_packet(packet)
    second = verify_job_quote_packet(packet)
    assert dumps_json(verification_payload(first)) == dumps_json(verification_payload(second))
    validate_instance(verification_payload(first), _RESULT_SCHEMA, label="verification")
    cost, price, job_id = _ORACLES[variant]
    assert first.result == "valid"
    assert first.authority == "verification_only"
    assert first.economic_status == "draft"
    assert first.anchor_status == "not_supplied"
    assert first.job_id == job_id
    assert first.packet_version == ("1.0.0" if variant == "v1" else "2.0.0")
    assert first.errors == ()
    body = b"".join(
        path.read_bytes()
        for path in sorted(packet.rglob("*"))
        if path.is_file() and not path.is_symlink()
    )
    assert cost.encode("utf-8") in body
    assert price.encode("utf-8") in body
    rendered = dumps_json(verification_payload(first)).decode("utf-8")
    assert cost not in rendered
    assert price not in rendered
    assert str(packet) not in rendered
    anchored = verify_job_quote_packet(packet, first.manifest_sha256)
    assert anchored.result == "valid"
    assert anchored.anchor_status == "matched"


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
def test_relocated_packet_verifies_after_sources_and_cwd_are_gone(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path / "origin", variant)
    relocated = tmp_path / "relocated" / variant
    shutil.copytree(packet, relocated, symlinks=True)
    shutil.rmtree(packet)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = verify_job_quote_packet(relocated)
    assert result.result == "valid"
    assert result.economic_status == "draft"
    assert packet_fingerprint(relocated)


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
def test_verifier_does_not_fall_back_to_live_checkout_or_publication(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    calls = {"publish": 0, "network": 0, "process": 0, "run": 0}

    def refuse_checkout(root: Path, raw: str, *, label: str) -> tuple[str, Path]:
        if Path(root).resolve().is_relative_to(ROOT):
            raise AssertionError("live checkout lookup")
        return resolve_workspace_file(root, raw, label=label)

    def refuse_publish(*_args: object, **_kwargs: object) -> None:
        calls["publish"] += 1
        raise AssertionError("publish")

    def refuse_network(*_args: object, **_kwargs: object) -> None:
        calls["network"] += 1
        raise AssertionError("network")

    def refuse_process(*_args: object, **_kwargs: object) -> None:
        calls["process"] += 1
        raise AssertionError("process")

    def refuse_run(*_args: object, **_kwargs: object) -> None:
        calls["run"] += 1
        raise AssertionError("run")

    monkeypatch.setattr("business.workflows.loading.resolve_workspace_file", refuse_checkout)
    monkeypatch.setattr("business.workflows.loading_v2.resolve_workspace_file", refuse_checkout)
    monkeypatch.setattr("business.workflows.quote_pipeline.publish_packet", refuse_publish)
    monkeypatch.setattr("business.workflows.quote_pipeline.run_job_quote", refuse_run)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    monkeypatch.setattr(subprocess, "Popen", refuse_process)
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(packet)
    assert result.result == "valid"
    assert calls == {"publish": 0, "network": 0, "process": 0, "run": 0}
    assert packet_fingerprint(packet) == before


def test_verifier_writes_do_not_target_the_packet(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    real_open = os.open

    def guarded(path: object, flags: int, *args: object, **kwargs: object) -> int:
        candidate = Path(os.fspath(path))
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND))
        if writing and candidate.resolve().is_relative_to(packet.resolve()):
            raise AssertionError("packet write")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(packet)
    assert result.result == "valid"
    assert packet_fingerprint(packet) == before


@pytest.mark.parametrize("variant", ["v1", "a"])
def test_rehashed_quote_price_still_fails_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    bid_path = packet / "internal" / "bid.json"
    bid = json.loads(bid_path.read_text(encoding="utf-8"))
    bid["pricing"]["quote_price"] = 1.0
    bid["pricing"]["price_per_unit"] = 1.0
    _write_json(bid_path, bid)
    _rehash(packet)
    _reject(packet, "REPLAY_MISMATCH", "internal/bid.json", "replay")


def test_rehashed_equipment_amount_still_fails_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    basis = _source(packet, "equipment_cost_basis", "cure_rack")
    path = packet / str(basis["snapshot_ref"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["equipment_burden_rate_per_hour"] = 0.10
    payload["equipment_hour_rate"] = 0.13
    _write_json(path, payload)
    _rehash(packet)
    _reject(packet, "REPLAY_MISMATCH", "customer/proposal.json", "replay")


def test_rehashed_reserve_and_margin_still_fail_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    reserve_packet = pristine_copy(generated_packets, tmp_path / "reserve", "a")
    estimate = _source(reserve_packet, "estimate_input", "thin_skin_variant_a")
    estimate_path = reserve_packet / str(estimate["snapshot_ref"])
    payload = json.loads(estimate_path.read_text(encoding="utf-8"))
    payload["process_yield_reserve_policy"]["reserve_rate"] = 0.5
    _write_json(estimate_path, payload)
    _rehash(reserve_packet)
    _reject(reserve_packet, "REPLAY_MISMATCH", "customer/proposal.json", "replay")

    margin_packet = pristine_copy(generated_packets, tmp_path / "margin", "a")
    for path in _job_files(margin_packet):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["pricing_policy"]["target_margin_pct"] = 10
        _write_json(path, payload)
    _rehash(margin_packet)
    _reject(margin_packet, "REPLAY_MISMATCH", "customer/proposal.json", "replay")


def test_rehashed_source_link_fails_closure_and_draft_status_fails_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    linked = pristine_copy(generated_packets, tmp_path / "link", "a")
    for path in _job_files(linked):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["estimate_input_ref"] = "fixtures/estimates/guitar/missing_input.json"
        _write_json(path, payload)
    _rehash(linked)
    result = _reject(linked, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")
    assert result.economic_status == "draft"

    status_packet = pristine_copy(generated_packets, tmp_path / "status", "v1")
    bid_path = status_packet / "internal" / "bid.json"
    bid = json.loads(bid_path.read_text(encoding="utf-8"))
    bid["status"] = "approved"
    _write_json(bid_path, bid)
    _rehash(status_packet)
    result = _reject(status_packet, "REPLAY_MISMATCH", "internal/bid.json", "replay")
    assert result.economic_status is None


@pytest.mark.parametrize(
    ("edit", "member"),
    [
        ("notes", "customer/proposal.json"),
        ("path", "customer/proposal.json"),
        ("steps", "customer/proposal.json"),
        ("signature", "customer/proposal.md"),
    ],
)
def test_customer_boundary_edits_fail_replay_without_echoing_private_text(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    edit: str,
    member: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    canary = "CANARY-PRIVATE-MARGIN-42"
    hidden_path = "fixtures/machines/bcm_2030ca_atc_v1.json"
    if edit == "signature":
        report = packet / "customer" / "proposal.md"
        report.write_bytes(report.read_bytes() + b"\nAuthorized Signature\n")
    else:
        proposal_path = packet / "customer" / "proposal.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        if edit == "notes":
            proposal["notes"].append(canary)
        elif edit == "path":
            proposal["sections"][0]["body"] = hidden_path
        else:
            proposal["next_steps"].append("Approve this price and release manufacturing")
        _write_json(proposal_path, proposal)
    _rehash(packet)
    result = _reject(packet, "REPLAY_MISMATCH", member, "replay")
    rendered = json.dumps(verification_payload(result))
    assert canary not in rendered
    assert hidden_path not in rendered
    assert "Authorized Signature" not in rendered
    if edit == "notes":
        assert canary in (packet / "customer" / "proposal.json").read_text(encoding="utf-8")
    if edit == "path":
        assert hidden_path in (packet / "customer" / "proposal.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("relative", "mutate"),
    [
        ("customer/proposal.json", "json"),
        ("customer/proposal.md", "markdown"),
    ],
)
def test_reformatted_canonical_bytes_fail_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    relative: str,
    mutate: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    target = packet / relative
    if mutate == "json":
        payload = json.loads(target.read_text(encoding="utf-8"))
        target.write_bytes(json.dumps(payload, indent=4).encode("utf-8") + b"\n")
    else:
        target.write_bytes(target.read_bytes().replace(b"\n", b" \n", 1))
    _rehash(packet)
    _reject(packet, "REPLAY_MISMATCH", relative, "replay")


def test_removed_equipment_source_fails_closure(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    kept = []
    for row in sources:
        assert isinstance(row, dict)
        if "cure_rack" in str(row["original_ref"]):
            (packet / str(row["snapshot_ref"])).unlink()
            continue
        kept.append(row)
    manifest["sources"] = kept
    _write_json(packet / "manifest.json", manifest)
    _reject(packet, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")


def test_extra_unrelated_source_fails_closure(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    product = next(row for row in sources if isinstance(row, dict) and row["role"] == "product")
    original = "fixtures/products/unrelated_product_v1.json"
    snapshot = f"internal/sources/{original}"
    destination = packet / snapshot
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((packet / str(product["snapshot_ref"])).read_bytes())
    sources.append(
        {
            "role": "product",
            "record_id": "UNRELATED-PRODUCT",
            "original_ref": original,
            "snapshot_ref": snapshot,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    )
    _write_json(packet / "manifest.json", manifest)
    _reject(packet, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")


def test_changed_source_identity_or_order_fails_closure(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    identity = pristine_copy(generated_packets, tmp_path / "identity", "a")
    manifest = _manifest(identity)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    product = next(row for row in sources if isinstance(row, dict) and row["role"] == "product")
    product["record_id"] = "PRODUCT-RENAMED"
    _write_json(identity / "manifest.json", manifest)
    _reject(identity, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")

    ordered = pristine_copy(generated_packets, tmp_path / "order", "a")
    manifest = _manifest(ordered)
    sources = manifest["sources"]
    assert isinstance(sources, list) and len(sources) >= 2
    sources[0], sources[1] = sources[1], sources[0]
    _write_json(ordered / "manifest.json", manifest)
    _reject(ordered, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")


def test_moved_source_ref_fails_closure(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "a")
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    product = next(row for row in sources if isinstance(row, dict) and row["role"] == "product")
    old_snapshot = packet / str(product["snapshot_ref"])
    new_original = "fixtures/products/moved_product_v1.json"
    new_snapshot = packet / "internal" / "sources" / new_original
    new_snapshot.parent.mkdir(parents=True, exist_ok=True)
    old_snapshot.rename(new_snapshot)
    parent = old_snapshot.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
    product["original_ref"] = new_original
    product["snapshot_ref"] = f"internal/sources/{new_original}"
    _write_json(packet / "manifest.json", manifest)
    _reject(packet, "SOURCE_CLOSURE_MISMATCH", "manifest.json", "source_closure")


def test_coherent_replacement_passes_unanchored_and_fails_the_retained_digest(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    copy_demo_workspace(workspace)
    original = run_job_quote(root=workspace, job=JOB_REL, output_dir="exports/jobs/original")
    retained = hashlib.sha256((original.output_dir / "manifest.json").read_bytes()).hexdigest()
    job_path = workspace / JOB_REL
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    payload["internal_notes"].append("coherent replacement note")
    _write_json(job_path, payload)
    replaced = run_job_quote(root=workspace, job=JOB_REL, output_dir="exports/jobs/replaced")
    unanchored = verify_job_quote_packet(replaced.output_dir)
    assert unanchored.result == "valid"
    assert unanchored.economic_status == "draft"
    assert unanchored.manifest_sha256 != retained
    anchored = verify_job_quote_packet(replaced.output_dir, retained)
    assert_rejected(anchored, "ANCHOR_MISMATCH", "manifest.json", "")


@pytest.mark.parametrize("variant", ["a", "b"])
def test_equipment_detail_rounding_stays_valid_until_rehashed(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    manifest = _manifest(packet)
    mapping = manifest["category_mapping"]
    assert isinstance(mapping, dict)
    rounding = mapping["rounding_reconciliation"]
    assert isinstance(rounding, dict)
    assert rounding["equipment_record_total"] == 12.13
    assert rounding["equipment_operation_detail_total"] == 12.12
    assert rounding["equipment_detail_difference"] == 0.01
    verified = verify_job_quote_packet(packet)
    assert verified.result == "valid"
    rendered = json.dumps(verification_payload(verified))
    assert "12.13" not in rendered
    assert "12.12" not in rendered
    rounding["equipment_detail_difference"] = 0.02
    _write_json(packet / "manifest.json", manifest)
    _reject(packet, "REPLAY_MISMATCH", "manifest.json", "replay")


def test_temporary_storage_failure_is_operational_and_leaves_no_reconstruction(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    before = set(Path(tempfile.gettempdir()).glob("job-quote-verify-*"))
    snapshots = set(Path(tempfile.gettempdir()).glob("job-quote-snapshot-*"))

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("temp unavailable")

    monkeypatch.setattr("business.workflows.verification.tempfile.TemporaryDirectory", boom)
    with pytest.raises(VerificationOperationalError, match="temporary verification storage"):
        verify_job_quote_packet(packet)
    assert set(Path(tempfile.gettempdir()).glob("job-quote-verify-*")) == before
    assert set(Path(tempfile.gettempdir()).glob("job-quote-snapshot-*")) == snapshots


def test_successful_and_refused_replay_clean_temporary_directories(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "b")
    before = set(Path(tempfile.gettempdir()).glob("job-quote-verify-*"))
    assert verify_job_quote_packet(packet).result == "valid"
    report = packet / "internal" / "cost_report.md"
    report.write_bytes(report.read_bytes() + b"\n")
    assert verify_job_quote_packet(packet).result == "invalid"
    assert set(Path(tempfile.gettempdir()).glob("job-quote-verify-*")) == before


def test_malformed_expected_digest_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex"):
        verify_job_quote_packet(tmp_path, "ABCD")
    with pytest.raises(ValueError, match="64 lowercase hex"):
        verify_job_quote_packet(tmp_path, "")


def test_result_invariants_reject_a_valid_record_with_an_error() -> None:
    with pytest.raises(ValueError, match="passing checks"):
        JobQuoteVerification(
            result="valid",
            manifest_sha256="a" * 64,
            expected_manifest_sha256=None,
            anchor_status="not_supplied",
            packet_version="1.0.0",
            economic_status="draft",
            job_id="JOB",
            estimate_id="EST",
            bid_id="BID",
            proposal_id="PROP",
            checks=checks_for(None),
            errors=(VerificationDiagnostic("HASH_MISMATCH", "manifest.json"),),
        )
    with pytest.raises(ValueError, match="fixed order"):
        JobQuoteVerification(
            result="invalid",
            manifest_sha256=None,
            expected_manifest_sha256=None,
            anchor_status="not_checked",
            packet_version=None,
            economic_status=None,
            job_id=None,
            estimate_id=None,
            bid_id=None,
            proposal_id=None,
            checks=tuple(reversed(checks_for("inventory"))),
            errors=(VerificationDiagnostic("PACKET_NOT_FOUND", None),),
        )


def test_read_failure_is_operational(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    real_open = os.open

    def guarded(path: object, flags: int, *args: object, **kwargs: object) -> int:
        candidate = Path(os.fspath(path))
        if candidate.name == "manifest.json" and candidate.parent == packet:
            raise OSError("unreadable")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    with pytest.raises(VerificationOperationalError, match="could not be read"):
        verify_job_quote_packet(packet)
