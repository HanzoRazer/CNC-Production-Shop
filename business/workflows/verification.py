"""Replay a saved draft quote packet from its captured sources.

Dev Order: CNC-JOB-QUOTE-VERIFY-001

Verification reuses the canonical loader and packet builder. It does not publish
a packet, and it does not approve a price or a manufacturing release.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from business.workflows.loading import load_job_quote, validate_instance
from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError, SourceSnapshot
from business.workflows.packet_loading import CapturedPacket, _State, admit_packet, ensure_unchanged
from business.workflows.quote_pipeline import build_job_quote_packet
from business.workflows.verification_models import (
    JobQuoteVerification,
    PacketRejectedError,
    VerificationOperationalError,
    checks_for,
    verification_payload,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RESULT_SCHEMA = "workflows/job_quote_verification_v1.schema.json"


def verify_job_quote_packet(
    packet_dir: Path | str,
    expected_manifest_sha256: str | None = None,
) -> JobQuoteVerification:
    """Verify one saved packet. Invalid packets return a result; I/O failures raise."""
    if expected_manifest_sha256 is not None and _DIGEST.fullmatch(expected_manifest_sha256) is None:
        raise ValueError("expected_manifest_sha256 must be 64 lowercase hex characters")
    try:
        captured = admit_packet(packet_dir, expected_manifest_sha256)
    except PacketRejectedError as exc:
        return _checked(exc.verification)
    state = _state_from(captured, expected_manifest_sha256)
    try:
        verified = _replay(captured, state)
    except PacketRejectedError as exc:
        return _checked(exc.verification)
    return _checked(verified)


def _replay(captured: CapturedPacket, state: _State) -> JobQuoteVerification:
    ensure_unchanged(
        captured.root,
        captured.identities,
        captured.directories,
        state,
        "source_closure",
    )
    try:
        temporary = tempfile.TemporaryDirectory(prefix="job-quote-verify-")
    except OSError as exc:
        raise VerificationOperationalError(
            "temporary verification storage could not be created"
        ) from exc
    try:
        workspace = Path(temporary.name)
        job_ref = _materialize_sources(workspace, captured)
        try:
            loaded = load_job_quote(workspace, job_ref)
        except JobQuoteRefusalError:
            state.reject("source_closure", "SOURCE_CLOSURE_MISMATCH", "manifest.json")
        except JobQuoteFailureError as exc:
            raise VerificationOperationalError("captured sources could not be admitted") from exc
        if not _sources_match(captured, loaded.sources):
            state.reject("source_closure", "SOURCE_CLOSURE_MISMATCH", "manifest.json")
        try:
            rebuilt = build_job_quote_packet(loaded)
        except (JobQuoteRefusalError, JobQuoteFailureError):
            state.reject("replay", "REPLAY_MISMATCH", None)
        mismatch = _first_mismatch(captured.files, rebuilt.files)
        if mismatch is not None:
            state.reject("replay", "REPLAY_MISMATCH", mismatch)
        if captured.economic_status != "draft":
            state.reject("replay", "REPLAY_MISMATCH", None)
        ensure_unchanged(
            captured.root,
            captured.identities,
            captured.directories,
            state,
            "replay",
        )
        return JobQuoteVerification(
            result="valid",
            manifest_sha256=captured.manifest_sha256,
            expected_manifest_sha256=state.expected_manifest_sha256,
            anchor_status=state.anchor_status,
            packet_version=captured.packet_version,
            economic_status="draft",
            job_id=captured.job_id,
            estimate_id=captured.estimate_id,
            bid_id=captured.bid_id,
            proposal_id=captured.proposal_id,
            checks=checks_for(None),
            errors=(),
        )
    finally:
        temporary.cleanup()


def _state_from(captured: CapturedPacket, expected: str | None) -> _State:
    state = _State(expected)
    state.manifest_sha256 = captured.manifest_sha256
    state.anchor_status = "matched" if expected is not None else "not_supplied"
    state.packet_version = captured.packet_version
    state.economic_status = captured.economic_status
    state.job_id = captured.job_id
    state.estimate_id = captured.estimate_id
    state.bid_id = captured.bid_id
    state.proposal_id = captured.proposal_id
    return state


def _materialize_sources(workspace: Path, captured: CapturedPacket) -> str:
    job_ref = ""
    for source in captured.manifest["sources"]:
        original = source["original_ref"]
        if source["role"] == "job_request":
            job_ref = original
        destination = workspace.joinpath(*original.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(destination, flags, 0o644)
        except OSError as exc:
            raise VerificationOperationalError(
                "temporary verification storage could not be written"
            ) from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(captured.files[source["snapshot_ref"]])
        except OSError as exc:
            raise VerificationOperationalError(
                "temporary verification storage could not be written"
            ) from exc
    if not job_ref:
        raise VerificationOperationalError("captured packet has no job request")
    return job_ref


def _sources_match(captured: CapturedPacket, sources: tuple[SourceSnapshot, ...]) -> bool:
    declared = [
        (
            item["role"],
            item["record_id"],
            item["original_ref"],
            item["snapshot_ref"],
            item["sha256"],
        )
        for item in captured.manifest["sources"]
    ]
    admitted = [
        (item.role, item.record_id, item.original_ref, item.snapshot_ref, item.sha256)
        for item in sources
    ]
    if declared != admitted:
        return False
    return all(captured.files[item.snapshot_ref] == item.raw_bytes for item in sources)


def _first_mismatch(captured: dict[str, bytes], rebuilt: dict[str, bytes]) -> str | None:
    captured_names = set(captured)
    rebuilt_names = set(rebuilt)
    if captured_names != rebuilt_names:
        missing = sorted(captured_names - rebuilt_names)
        extra = sorted(rebuilt_names - captured_names)
        return (missing or extra)[0]
    for name in sorted(captured_names):
        if captured[name] != rebuilt[name]:
            return name
    return None


def _checked(result: JobQuoteVerification) -> JobQuoteVerification:
    try:
        validate_instance(verification_payload(result), _RESULT_SCHEMA, label="verification")
    except JobQuoteRefusalError as exc:
        raise VerificationOperationalError("verification result failed its contract") from exc
    return result
