"""Read-only admission of one saved job-quote packet.

Dev Order: CNC-JOB-QUOTE-VERIFY-001

The reader uses non-following filesystem inspection. It does not repair,
normalize, or write packet files, and it does not calculate economics.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from business.workflows.loading import parse_json_object, validate_instance
from business.workflows.models import JobQuoteRefusalError
from business.workflows.verification_models import (
    JobQuoteVerification,
    PacketRejectedError,
    VerificationDiagnostic,
    VerificationOperationalError,
    checks_for,
)

_ARTIFACTS = (
    ("internal/job_request.json", "job_request", "internal"),
    ("internal/estimate.json", "estimate", "internal"),
    ("internal/bid.json", "bid", "internal"),
    ("internal/bid_summary.json", "bid_summary", "internal"),
    ("internal/cost_report.md", "cost_report", "internal"),
    ("customer/proposal.json", "proposal_json", "customer"),
    ("customer/proposal.md", "proposal_markdown", "customer"),
)
_MANIFEST_SCHEMAS = {
    "1.0.0": "workflows/job_quote_manifest_v1.schema.json",
    "2.0.0": "workflows/job_quote_manifest_v2.schema.json",
}
_SOURCE_SCHEMAS = {
    "1.0.0": {
        "job_request": "workflows/job_quote_request_v1.schema.json",
        "estimate_input": "estimates/guitar_estimate_input_v1.schema.json",
        "product": "products/guitar_product_definition_v1.schema.json",
        "machine_profile": "machines/machine_profile_v1.schema.json",
        "machine_cost_basis": "machines/machine_cost_basis_v1.schema.json",
    },
    "2.0.0": {
        "job_request": "workflows/job_quote_request_v2.schema.json",
        "estimate_input": "estimates/thin_skin_estimate_input_v2.schema.json",
        "product": "products/thin_skin_guitar_product_definition_v1.schema.json",
        "machine_profile": "machines/machine_profile_v1.schema.json",
        "machine_cost_basis": "machines/machine_cost_basis_v1.schema.json",
        "equipment_profile": "equipment/equipment_profile_v1.schema.json",
        "equipment_cost_basis": "equipment/equipment_cost_basis_v1.schema.json",
    },
}
_GENERATED_SCHEMAS = {
    "1.0.0": {
        "internal/job_request.json": "workflows/job_quote_request_v1.schema.json",
        "internal/estimate.json": "estimates/guitar_build_estimate_v1.schema.json",
        "internal/bid.json": "bids/bid_v1.schema.json",
        "internal/bid_summary.json": "bids/bid_summary_v1.schema.json",
        "customer/proposal.json": "proposals/proposal_v1.schema.json",
    },
    "2.0.0": {
        "internal/job_request.json": "workflows/job_quote_request_v2.schema.json",
        "internal/estimate.json": "estimates/thin_skin_build_estimate_v2.schema.json",
        "internal/bid.json": "bids/bid_v2.schema.json",
        "internal/bid_summary.json": "bids/bid_summary_v1.schema.json",
        "customer/proposal.json": "proposals/proposal_v1.schema.json",
    },
}
_JSON_ARTIFACTS = (
    "internal/estimate.json",
    "internal/bid.json",
    "internal/bid_summary.json",
    "customer/proposal.json",
)
_Identity = tuple[int, int, int, int]


@dataclass(frozen=True)
class CapturedPacket:
    """Bytes and metadata captured from one quiescent packet directory."""

    root: Path
    manifest_sha256: str
    manifest: dict[str, Any]
    packet_version: str
    files: dict[str, bytes]
    job_id: str
    estimate_id: str
    bid_id: str
    proposal_id: str
    economic_status: str | None
    identities: dict[str, _Identity]
    directories: tuple[str, ...]


@dataclass
class _State:
    expected_manifest_sha256: str | None
    manifest_sha256: str | None = None
    anchor_status: str = "not_checked"
    packet_version: str | None = None
    economic_status: str | None = None
    job_id: str | None = None
    estimate_id: str | None = None
    bid_id: str | None = None
    proposal_id: str | None = None

    def reject(self, phase: str | None, code: str, member: str | None) -> NoReturn:
        """Raise the first diagnostic. An empty phase leaves every check not_run."""
        failed = "" if phase is None else phase
        verification = JobQuoteVerification(
            result="invalid",
            manifest_sha256=self.manifest_sha256,
            expected_manifest_sha256=self.expected_manifest_sha256,
            anchor_status=self.anchor_status,
            packet_version=self.packet_version,
            economic_status=self.economic_status,
            job_id=self.job_id,
            estimate_id=self.estimate_id,
            bid_id=self.bid_id,
            proposal_id=self.proposal_id,
            checks=checks_for(failed),
            errors=(VerificationDiagnostic(code, member),),
        )
        raise PacketRejectedError(verification)


def admit_packet(packet_dir: Path | str, expected_manifest_sha256: str | None) -> CapturedPacket:
    """Capture one supported packet, or reject it before economic replay."""
    state = _State(expected_manifest_sha256)
    root = _existing_directory(packet_dir, state)
    identities, directories, unsafe = _scan_tree(root)
    if unsafe:
        state.reject("inventory", "UNSAFE_MEMBER", unsafe[0])
    if "manifest.json" not in identities:
        state.reject("inventory", "INVENTORY_MISMATCH", "manifest.json")
    files = {relative: read_member(root, relative, state) for relative in sorted(identities)}
    ensure_unchanged(root, identities, directories, state, "inventory")
    manifest_bytes = files["manifest.json"]
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    state.manifest_sha256 = digest
    _compare_anchor(state)
    manifest = _parse_manifest(manifest_bytes, state)
    version = _supported_version(manifest, state)
    _require_inventory(manifest, files, directories, state)
    _validate_schemas(version, manifest, files, state)
    _require_hashes(manifest, files, state)
    ensure_unchanged(root, identities, directories, state, "hashes")
    economic = state.economic_status
    return CapturedPacket(
        root=root,
        manifest_sha256=digest,
        manifest=manifest,
        packet_version=version,
        files=dict(files),
        job_id=str(manifest["job_id"]),
        estimate_id=str(manifest["estimate_id"]),
        bid_id=str(manifest["bid_id"]),
        proposal_id=str(manifest["proposal_id"]),
        economic_status=economic,
        identities=identities,
        directories=directories,
    )


def read_member(root: Path, relative: str, state: _State) -> bytes:
    """Read one regular packet member without following a symlink."""
    path = root.joinpath(*relative.split("/"))
    try:
        info = path.lstat()
    except FileNotFoundError:
        state.reject("inventory", "PACKET_CHANGED_DURING_READ", relative)
    except OSError as exc:
        raise VerificationOperationalError("packet member could not be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        state.reject("inventory", "UNSAFE_MEMBER", relative)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        state.reject("inventory", "PACKET_CHANGED_DURING_READ", relative)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            state.reject("inventory", "UNSAFE_MEMBER", relative)
        raise VerificationOperationalError("packet member could not be read") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise VerificationOperationalError("packet member could not be read") from exc


def ensure_unchanged(
    root: Path,
    identities: dict[str, _Identity],
    directories: tuple[str, ...],
    state: _State,
    phase: str,
) -> None:
    """Reject the capture when the packet changed after the baseline inspection."""
    observed, observed_dirs, unsafe = _scan_tree(root)
    changed = sorted(
        (set(observed) ^ set(identities))
        | {name for name in observed if name in identities and observed[name] != identities[name]}
        | (set(observed_dirs) ^ set(directories))
    )
    if unsafe or changed:
        state.reject(phase, "PACKET_CHANGED_DURING_READ", (unsafe or changed)[0])


def _existing_directory(packet_dir: Path | str, state: _State) -> Path:
    path = Path(packet_dir)
    if path.is_symlink():
        state.reject("inventory", "UNSAFE_MEMBER", None)
    if not path.exists() or not path.is_dir():
        state.reject("inventory", "PACKET_NOT_FOUND", None)
    return path


def _scan_tree(root: Path) -> tuple[dict[str, _Identity], tuple[str, ...], tuple[str, ...]]:
    """List regular files and directories without opening or following members."""
    unsafe: list[str] = []
    files: dict[str, _Identity] = {}
    directories: list[str] = []
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as exc:
            raise VerificationOperationalError("packet directory could not be inspected") from exc
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            kind, identity = _member_kind(entry)
            if kind == "dir":
                directories.append(relative)
                pending.append(Path(entry.path))
            elif kind == "file" and identity is not None:
                files[relative] = identity
            else:
                unsafe.append(relative)
    return files, tuple(sorted(directories)), tuple(sorted(unsafe))


def _member_kind(entry: os.DirEntry[str]) -> tuple[str, _Identity | None]:
    try:
        info = entry.stat(follow_symlinks=False)
    except OSError as exc:
        raise VerificationOperationalError("packet member could not be inspected") from exc
    identity = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
    if stat.S_ISLNK(info.st_mode):
        return "symlink", None
    if stat.S_ISREG(info.st_mode):
        return "file", identity
    if stat.S_ISDIR(info.st_mode):
        return "dir", None
    return "special", None


def _compare_anchor(state: _State) -> None:
    expected = state.expected_manifest_sha256
    if expected is None:
        state.anchor_status = "not_supplied"
        return
    if state.manifest_sha256 != expected:
        state.anchor_status = "mismatch"
        state.reject(None, "ANCHOR_MISMATCH", "manifest.json")
    state.anchor_status = "matched"


def _parse_manifest(raw: bytes, state: _State) -> dict[str, Any]:
    try:
        return parse_json_object(raw, label="manifest")
    except JobQuoteRefusalError:
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    raise AssertionError("unreachable manifest parse")


def _supported_version(manifest: dict[str, Any], state: _State) -> str:
    version = manifest.get("record_version")
    if manifest.get("record_type") != "cnc_job_quote_manifest" or version not in _MANIFEST_SCHEMAS:
        state.reject("schemas", "UNSUPPORTED_CONTRACT", "manifest.json")
    assert isinstance(version, str)
    return version


def _require_inventory(
    manifest: dict[str, Any],
    files: dict[str, bytes],
    directories: tuple[str, ...],
    state: _State,
) -> None:
    artifacts = manifest.get("artifacts")
    sources = manifest.get("sources")
    if not isinstance(artifacts, list) or not isinstance(sources, list):
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    artifact_rows = [_artifact_row(item, state) for item in artifacts]
    source_rows = [_source_row(item, state) for item in sources]
    _require_unique_artifacts(artifact_rows, state)
    _require_unique_sources(source_rows, state)
    declared = {path for path, _role, _audience in artifact_rows}
    declared.update(snapshot for _role, _ref, snapshot in source_rows)
    declared.add("manifest.json")
    actual = set(files)
    if actual != declared:
        missing = sorted(declared - actual)
        extra = sorted(actual - declared)
        state.reject("inventory", "INVENTORY_MISMATCH", (missing or extra)[0])
    expected_dirs = _parent_directories(declared)
    if set(directories) != expected_dirs:
        missing_dirs = sorted(expected_dirs - set(directories))
        extra_dirs = sorted(set(directories) - expected_dirs)
        state.reject("inventory", "INVENTORY_MISMATCH", (extra_dirs or missing_dirs)[0])
    triples = set(artifact_rows)
    if triples != set(_ARTIFACTS) or len(artifact_rows) != len(_ARTIFACTS):
        state.reject("inventory", "INVENTORY_MISMATCH", "manifest.json")


def _artifact_row(item: object, state: _State) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    path = _member_ref(item.get("path"), state)
    role = item.get("role")
    audience = item.get("audience")
    if not isinstance(role, str) or not isinstance(audience, str):
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    if path == "manifest.json":
        state.reject("inventory", "DUPLICATE_ENTRY", "manifest.json")
    return path, role, audience


def _source_row(item: object, state: _State) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    role = item.get("role")
    if not isinstance(role, str) or not role:
        state.reject("schemas", "SCHEMA_INVALID", "manifest.json")
    original = _member_ref(item.get("original_ref"), state)
    snapshot = _member_ref(item.get("snapshot_ref"), state)
    if snapshot in {row[0] for row in _ARTIFACTS} or snapshot == "manifest.json":
        state.reject("inventory", "DUPLICATE_ENTRY", snapshot)
    if snapshot != f"internal/sources/{original}":
        state.reject("inventory", "INVENTORY_MISMATCH", snapshot)
    return role, original, snapshot


def _member_ref(value: object, state: _State) -> str:
    if not isinstance(value, str) or _is_unsafe_ref(value):
        state.reject("inventory", "UNSAFE_MEMBER", None)
    return value


def _is_unsafe_ref(value: str) -> bool:
    if not value or value != value.strip():
        return True
    if "://" in value or "\\" in value or value.startswith("/"):
        return True
    if len(value) >= 2 and value[1] == ":":
        return True
    return any(part in {"", ".", ".."} for part in value.split("/"))


def _require_unique_artifacts(
    rows: list[tuple[str, str, str]],
    state: _State,
) -> None:
    paths: set[str] = set()
    roles: set[str] = set()
    for path, role, _audience in rows:
        if path in paths or role in roles:
            state.reject("inventory", "DUPLICATE_ENTRY", path)
        paths.add(path)
        roles.add(role)


def _require_unique_sources(rows: list[tuple[str, str, str]], state: _State) -> None:
    seen_pairs: set[tuple[str, str]] = set()
    seen_refs: set[str] = set()
    seen_snapshots: set[str] = set()
    job_requests = 0
    for role, original, snapshot in rows:
        if role == "job_request":
            job_requests += 1
        pair = (role, original)
        if pair in seen_pairs or original in seen_refs or snapshot in seen_snapshots:
            state.reject("inventory", "DUPLICATE_ENTRY", snapshot)
        seen_pairs.add(pair)
        seen_refs.add(original)
        seen_snapshots.add(snapshot)
    if job_requests != 1:
        code = "DUPLICATE_ENTRY" if job_requests > 1 else "INVENTORY_MISMATCH"
        state.reject("inventory", code, "manifest.json")


def _parent_directories(files: set[str]) -> set[str]:
    parents: set[str] = set()
    for relative in files:
        parent = relative.rpartition("/")[0]
        while parent:
            parents.add(parent)
            parent = parent.rpartition("/")[0]
    return parents


def _validate_schemas(
    version: str,
    manifest: dict[str, Any],
    files: dict[str, bytes],
    state: _State,
) -> None:
    _validate_json(files["manifest.json"], _MANIFEST_SCHEMAS[version], "manifest.json", state)
    state.packet_version = version
    state.job_id = _text_field(manifest, "job_id")
    state.estimate_id = _text_field(manifest, "estimate_id")
    state.bid_id = _text_field(manifest, "bid_id")
    state.proposal_id = _text_field(manifest, "proposal_id")
    generated = _GENERATED_SCHEMAS[version]
    for relative, schema in generated.items():
        _validate_json(files[relative], schema, relative, state)
    source_schemas = _SOURCE_SCHEMAS[version]
    for source in manifest["sources"]:
        role = source["role"]
        source_schema = source_schemas.get(role)
        if source_schema is None:
            state.reject("schemas", "UNSUPPORTED_CONTRACT", source["snapshot_ref"])
        _validate_json(
            files[source["snapshot_ref"]],
            source_schema,
            source["snapshot_ref"],
            state,
        )
    state.economic_status = _draft_status(manifest, files)


def _validate_json(raw: bytes, schema: str, member: str, state: _State) -> None:
    try:
        payload = parse_json_object(raw, label=member)
        validate_instance(payload, schema, label=member)
    except JobQuoteRefusalError:
        state.reject("schemas", "SCHEMA_INVALID", member)


def _text_field(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if isinstance(value, str) and value:
        return value
    return None


def _draft_status(manifest: dict[str, Any], files: dict[str, bytes]) -> str | None:
    payloads = [manifest]
    relatives = (
        "internal/estimate.json",
        "internal/bid.json",
        "internal/bid_summary.json",
        "customer/proposal.json",
    )
    for relative in relatives:
        try:
            payloads.append(parse_json_object(files[relative], label=relative))
        except JobQuoteRefusalError:
            return None
    if all(item.get("status") == "draft" for item in payloads):
        return "draft"
    return None


def _require_hashes(
    manifest: dict[str, Any],
    files: dict[str, bytes],
    state: _State,
) -> None:
    mismatched: list[str] = []
    for entry in manifest["artifacts"]:
        path = entry["path"]
        if hashlib.sha256(files[path]).hexdigest() != entry["sha256"]:
            mismatched.append(path)
    for entry in manifest["sources"]:
        path = entry["snapshot_ref"]
        if hashlib.sha256(files[path]).hexdigest() != entry["sha256"]:
            mismatched.append(path)
    job = next(entry for entry in manifest["sources"] if entry["role"] == "job_request")
    if files["internal/job_request.json"] != files[job["snapshot_ref"]]:
        mismatched.append("internal/job_request.json")
    if mismatched:
        state.reject("hashes", "HASH_MISMATCH", sorted(mismatched)[0])
