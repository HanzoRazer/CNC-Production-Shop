"""Packet inventory, confinement, strict JSON, and capture checks."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from business.workflows import packet_loading
from business.workflows.verification import verify_job_quote_packet
from business.workflows.verification_models import verification_payload
from tests.workflows.conftest import assert_rejected, packet_fingerprint, pristine_copy

_VARIANTS = ("v1", "a", "b")


def _manifest(packet: Path) -> dict[str, object]:
    return json.loads((packet / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(packet: Path, manifest: dict[str, object]) -> None:
    encoded = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (packet / "manifest.json").write_bytes(encoded)


def _reject_unchanged(
    packet: Path,
    code: str,
    member: str | None,
    phase: str,
):
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(packet)
    assert_rejected(result, code, member, phase)
    assert packet_fingerprint(packet) == before
    return result


def _member_paths(packet: Path, kind: str) -> list[str]:
    manifest = _manifest(packet)
    rows = manifest["artifacts" if kind == "artifact" else "sources"]
    assert isinstance(rows, list)
    key = "path" if kind == "artifact" else "snapshot_ref"
    return [str(row[key]) for row in rows if isinstance(row, dict)]


@pytest.mark.parametrize("variant", _VARIANTS)
def test_generated_packet_verifies_before_inventory_mutations(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    assert (packet / "manifest.json").is_file()
    assert packet_fingerprint(packet)


@pytest.mark.parametrize("variant", _VARIANTS)
def test_missing_artifacts_and_sources_are_inventory_mismatches(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    template = pristine_copy(generated_packets, tmp_path / "template", variant)
    relatives = _member_paths(template, "artifact") + _member_paths(template, "source")
    assert relatives
    for relative in relatives:
        packet = pristine_copy(generated_packets, tmp_path / relative.replace("/", "-"), variant)
        (packet / relative).unlink()
        _reject_unchanged(packet, "INVENTORY_MISMATCH", relative, "inventory")


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize(
    ("relative", "payload"),
    [
        ("customer/extra.txt", b"unlisted"),
        ("internal/attachment.txt", b"unlisted"),
    ],
)
def test_unlisted_files_are_inventory_mismatches(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    relative: str,
    payload: bytes,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    target = packet / relative
    target.write_bytes(payload)
    _reject_unchanged(packet, "INVENTORY_MISMATCH", relative, "inventory")


@pytest.mark.parametrize("variant", _VARIANTS)
def test_unexpected_empty_directory_is_an_inventory_mismatch(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    (packet / "customer" / "empty").mkdir()
    _reject_unchanged(packet, "INVENTORY_MISMATCH", "customer/empty", "inventory")


@pytest.mark.parametrize("variant", ["v1", "a"])
def test_duplicate_artifact_role_or_path_is_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    role_packet = pristine_copy(generated_packets, tmp_path / "role", variant)
    manifest = _manifest(role_packet)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    report = next(
        row for row in artifacts if isinstance(row, dict) and row["role"] == "cost_report"
    )
    report["role"] = "bid"
    _write_manifest(role_packet, manifest)
    _reject_unchanged(role_packet, "DUPLICATE_ENTRY", "internal/cost_report.md", "inventory")

    path_packet = pristine_copy(generated_packets, tmp_path / "path", variant)
    manifest = _manifest(path_packet)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    report = next(
        row for row in artifacts if isinstance(row, dict) and row["role"] == "cost_report"
    )
    report["path"] = "internal/bid.json"
    _write_manifest(path_packet, manifest)
    _reject_unchanged(path_packet, "DUPLICATE_ENTRY", "internal/bid.json", "inventory")


@pytest.mark.parametrize("variant", ["v1", "a"])
def test_duplicate_source_entry_is_refused_within_the_existing_length(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list) and len(sources) >= 2
    first = sources[0]
    last = sources[-1]
    assert isinstance(first, dict) and isinstance(last, dict)
    last["role"] = first["role"]
    last["original_ref"] = first["original_ref"]
    last["snapshot_ref"] = first["snapshot_ref"]
    _write_manifest(packet, manifest)
    _reject_unchanged(packet, "DUPLICATE_ENTRY", str(first["snapshot_ref"]), "inventory")


def test_missing_job_request_and_manifest_self_entry_are_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    missing = pristine_copy(generated_packets, tmp_path / "missing", "v1")
    manifest = _manifest(missing)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    job = next(row for row in sources if isinstance(row, dict) and row["role"] == "job_request")
    job["role"] = "estimate_input"
    _write_manifest(missing, manifest)
    _reject_unchanged(missing, "INVENTORY_MISMATCH", "manifest.json", "inventory")

    self_entry = pristine_copy(generated_packets, tmp_path / "self", "v1")
    manifest = _manifest(self_entry)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    report = next(
        row for row in artifacts if isinstance(row, dict) and row["role"] == "cost_report"
    )
    report["path"] = "manifest.json"
    _write_manifest(self_entry, manifest)
    _reject_unchanged(self_entry, "DUPLICATE_ENTRY", "manifest.json", "inventory")


def test_artifact_source_collision_is_a_duplicate_entry(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    product = next(row for row in sources if isinstance(row, dict) and row["role"] == "product")
    product["snapshot_ref"] = "internal/bid.json"
    _write_manifest(packet, manifest)
    _reject_unchanged(packet, "DUPLICATE_ENTRY", "internal/bid.json", "inventory")


def test_wrong_snapshot_prefix_is_an_inventory_mismatch(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    manifest = _manifest(packet)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    product = next(row for row in sources if isinstance(row, dict) and row["role"] == "product")
    product["snapshot_ref"] = "internal/not-sources/product.json"
    _write_manifest(packet, manifest)
    _reject_unchanged(
        packet,
        "INVENTORY_MISMATCH",
        "internal/not-sources/product.json",
        "inventory",
    )


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        "/etc/passwd",
        "C:/Windows/notepad.exe",
        "https://example.invalid/packet.json",
        "internal\\bid.json",
        "../outside.json",
        "internal/./bid.json",
        "internal//bid.json",
        "internal/../manifest.json",
    ],
)
def test_unsafe_member_refs_are_not_echoed_or_opened(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    unsafe_ref: str,
) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("SECRET-CANARY-OUTSIDE", encoding="utf-8")
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    manifest = _manifest(packet)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    bid = next(row for row in artifacts if isinstance(row, dict) and row["role"] == "bid")
    bid["path"] = unsafe_ref
    _write_manifest(packet, manifest)
    result = _reject_unchanged(packet, "UNSAFE_MEMBER", None, "inventory")
    rendered = json.dumps(verification_payload(result))
    assert unsafe_ref not in rendered
    assert "SECRET-CANARY-OUTSIDE" not in rendered
    assert outside.read_text(encoding="utf-8") == "SECRET-CANARY-OUTSIDE"


def test_symlink_root_is_refused_without_a_member_path(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    link = tmp_path / "linked-root"
    os.symlink(packet, link)
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(link)
    assert_rejected(result, "UNSAFE_MEMBER", None, "inventory")
    assert packet_fingerprint(packet) == before


def test_symlink_member_dangling_link_and_symlink_parent_are_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    outside = tmp_path / "sentinel.txt"
    outside.write_text("SENTINEL-OUTSIDE-PACKET", encoding="utf-8")

    member = pristine_copy(generated_packets, tmp_path / "member", "v1")
    os.symlink(outside, member / "customer" / "linked.json")
    result = _reject_unchanged(member, "UNSAFE_MEMBER", "customer/linked.json", "inventory")
    assert "SENTINEL-OUTSIDE-PACKET" not in json.dumps(verification_payload(result))

    dangling = pristine_copy(generated_packets, tmp_path / "dangling", "v1")
    os.symlink(dangling / "missing-target", dangling / "customer" / "dangling.json")
    _reject_unchanged(dangling, "UNSAFE_MEMBER", "customer/dangling.json", "inventory")

    parent = pristine_copy(generated_packets, tmp_path / "parent", "v1")
    real_customer = parent / "customer-real"
    (parent / "customer").rename(real_customer)
    os.symlink(real_customer, parent / "customer", target_is_directory=True)
    _reject_unchanged(parent, "UNSAFE_MEMBER", "customer", "inventory")


def test_fifo_member_is_refused_without_reading_it(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo is unavailable on this platform")
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    fifo = packet / "customer" / "pipe"
    try:
        os.mkfifo(fifo)
    except OSError as exc:
        pytest.skip(f"fifo could not be created: {exc}")
    _reject_unchanged(packet, "UNSAFE_MEMBER", "customer/pipe", "inventory")
    assert stat.S_ISFIFO(fifo.lstat().st_mode)


def test_unix_socket_member_is_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX is unavailable on this platform")
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    sock_path = packet / "customer" / "listener"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(os.fspath(sock_path))
    except OSError as exc:
        server.close()
        pytest.skip(f"unix socket could not be bound: {exc}")
    try:
        _reject_unchanged(packet, "UNSAFE_MEMBER", "customer/listener", "inventory")
    finally:
        server.close()


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"record_type":"cnc_job_quote_manifest","record_type":"other"}\n', "SCHEMA_INVALID"),
        (b'{"record_type":"cnc_job_quote_manifest","n":NaN}\n', "SCHEMA_INVALID"),
        (b'{"record_type":"cnc_job_quote_manifest","n":Infinity}\n', "SCHEMA_INVALID"),
    ],
)
def test_strict_manifest_json_is_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    raw: bytes,
    code: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    (packet / "manifest.json").write_bytes(raw)
    _reject_unchanged(packet, code, "manifest.json", "schemas")


def test_bool_numeric_unknown_field_and_bad_timestamp_are_schema_invalid(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    boolean = pristine_copy(generated_packets, tmp_path / "bool", "v1")
    manifest = _manifest(boolean)
    mapping = manifest["category_mapping"]
    assert isinstance(mapping, dict)
    amounts = mapping["mapped_amounts"]
    assert isinstance(amounts, dict)
    amounts["direct_material_cost"] = True
    _write_manifest(boolean, manifest)
    _reject_unchanged(boolean, "SCHEMA_INVALID", "manifest.json", "schemas")

    unknown = pristine_copy(generated_packets, tmp_path / "unknown", "v1")
    manifest = _manifest(unknown)
    manifest["unexpected_field"] = "no"
    _write_manifest(unknown, manifest)
    _reject_unchanged(unknown, "SCHEMA_INVALID", "manifest.json", "schemas")

    dated = pristine_copy(generated_packets, tmp_path / "date", "a")
    manifest = _manifest(dated)
    manifest["created_at"] = "2026-10-26"
    _write_manifest(dated, manifest)
    _reject_unchanged(dated, "SCHEMA_INVALID", "manifest.json", "schemas")


def test_unsupported_version_does_not_admit_the_packet(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    manifest = _manifest(packet)
    manifest["record_version"] = "9.0.0"
    _write_manifest(packet, manifest)
    result = _reject_unchanged(packet, "UNSUPPORTED_CONTRACT", "manifest.json", "schemas")
    assert result.packet_version is None
    assert result.job_id is None
    assert result.economic_status is None


@pytest.mark.parametrize(("variant", "other_version"), [("v1", "2.0.0"), ("a", "1.0.0")])
def test_cross_version_lineage_is_schema_invalid(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    other_version: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    manifest = _manifest(packet)
    manifest["record_version"] = other_version
    manifest["workflow_version"] = other_version
    manifest["mapping_version"] = other_version
    _write_manifest(packet, manifest)
    result = _reject_unchanged(packet, "SCHEMA_INVALID", "manifest.json", "schemas")
    assert result.packet_version is None


def test_hash_tamper_without_updating_the_manifest_fails_hashes(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    report = packet / "internal" / "cost_report.md"
    report.write_bytes(report.read_bytes() + b"\n")
    _reject_unchanged(packet, "HASH_MISMATCH", "internal/cost_report.md", "hashes")


def test_job_artifact_and_snapshot_byte_disagreement_is_a_hash_mismatch(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    request = packet / "internal" / "job_request.json"
    payload = json.loads(request.read_text(encoding="utf-8"))
    notes = payload["internal_notes"]
    assert isinstance(notes, list)
    notes.append("artifact-only edit")
    request.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    manifest = _manifest(packet)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    job = next(
        row
        for row in artifacts
        if isinstance(row, dict) and row["path"] == "internal/job_request.json"
    )
    job["sha256"] = hashlib.sha256(request.read_bytes()).hexdigest()
    _write_manifest(packet, manifest)
    _reject_unchanged(packet, "HASH_MISMATCH", "internal/job_request.json", "hashes")


def test_replacing_a_member_during_capture_invalidates_the_read(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    original = packet_loading.read_member

    def wrapped(root: Path, relative: str, state: object) -> bytes:
        data = original(root, relative, state)
        if relative == "manifest.json":
            target = root / "customer" / "proposal.md"
            target.write_bytes(target.read_bytes() + b"\n")
        return data

    monkeypatch.setattr(packet_loading, "read_member", wrapped)
    before = packet_fingerprint(packet)
    result = verify_job_quote_packet(packet)
    assert_rejected(result, "PACKET_CHANGED_DURING_READ", "customer/proposal.md", "inventory")
    assert packet_fingerprint(packet) != before


def test_adding_a_member_between_inventory_scans_invalidates_the_read(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    original = packet_loading._scan_tree
    calls = {"count": 0}

    def wrapped(root: Path) -> tuple[object, ...]:
        calls["count"] += 1
        if calls["count"] == 2:
            (root / "unexpected.txt").write_bytes(b"x")
        return original(root)

    monkeypatch.setattr(packet_loading, "_scan_tree", wrapped)
    result = verify_job_quote_packet(packet)
    assert_rejected(result, "PACKET_CHANGED_DURING_READ", "unexpected.txt", "inventory")
    assert (packet / "unexpected.txt").read_bytes() == b"x"


def test_missing_packet_directory_is_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "absent-packet"
    result = verify_job_quote_packet(missing)
    assert_rejected(result, "PACKET_NOT_FOUND", None, "inventory")
    assert result.manifest_sha256 is None
    assert result.anchor_status == "not_checked"
    assert result.packet_version is None


def test_anchor_mismatch_stops_before_replay(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    original = hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    manifest = _manifest(packet)
    manifest["job_id"] = "JOB-EDITED"
    _write_manifest(packet, manifest)
    result = verify_job_quote_packet(packet, original)
    assert_rejected(result, "ANCHOR_MISMATCH", "manifest.json", "")
    assert result.anchor_status == "mismatch"
    assert result.expected_manifest_sha256 == original
    assert result.manifest_sha256 != original
    assert result.packet_version is None
