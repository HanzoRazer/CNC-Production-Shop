"""Record a caller-asserted price decision against one verified draft packet."""

from __future__ import annotations

import errno
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from business.workflows.loading import validate_instance
from business.workflows.price_review import (
    _cent_valued,
    _is_zero,
    _matched_subject,
    _object,
    _require_bound_hashes,
    _require_direct_cost_only,
    record_price_review,
)
from business.workflows.price_review_models import (
    AUTHORITY,
    COST_ACKNOWLEDGMENT,
    IDENTITY_ASSURANCE,
    VERIFICATION_AUTHORITY,
    VERIFICATION_CONTRACT,
    PriceReviewFailureError,
    PriceReviewRecord,
    PriceReviewRefusalError,
    ReviewedSubject,
)
from business.workflows.reporting import dumps_json
from business.workflows.verification import verify_job_quote_packet
from business.workflows.verification_models import verification_payload
from tests.workflows.conftest import (
    copy_saved_packet,
    packet_fingerprint,
    price_review_request_bytes,
)

_PRICES = {"v1": 1320.13, "a": 1001.27, "b": 1043.70}
_COSTS = {"v1": "924.09", "a": "700.89", "b": "730.59"}
_VERSIONS = {"v1": "1.0.0", "a": "2.0.0", "b": "2.0.0"}
_RESULT_SCHEMA = "workflows/job_quote_price_review_v1.schema.json"
_REQUEST_SCHEMA = "workflows/job_quote_price_review_request_v1.schema.json"
_CANARY_NOTE = "CANARY-PRIVATE-NOTE"
_CANARY_REASON = "CANARY-RATIONALE for this synthetic decision."
_REVIEW_KEYS = {
    "authority",
    "cost_basis_acknowledgment",
    "decision",
    "internal_notes",
    "proposal_sha256",
    "reason",
    "record_type",
    "record_version",
    "review_id",
    "review_request_sha256",
    "reviewed_at",
    "reviewer_identity_assurance",
    "reviewer_ref",
    "reviewer_role",
    "subject",
    "verification_authority",
    "verification_contract",
    "verification_sha256",
}
_SUBJECT_KEYS = {
    "bid_id",
    "currency",
    "economic_status",
    "estimate_id",
    "job_id",
    "manifest_sha256",
    "packet_version",
    "proposal_id",
    "quantity",
    "quote_price",
    "revision",
}


def _dump(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _request(packet: Path, **kwargs: object) -> bytes:
    return price_review_request_bytes(packet, **kwargs)  # type: ignore[arg-type]


def _record(packet: Path, directory: Path, raw: bytes, name: str = "review-out"):
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / f"{name}-request.json"
    output = directory / name
    request.write_bytes(raw)
    recorded = record_price_review(
        packet_dir=str(packet),
        request_path=str(request),
        output_dir=str(output),
    )
    return recorded, output


def _refuse(
    packet: Path,
    directory: Path,
    raw: bytes,
    code: str,
    name: str = "refused",
    *,
    keep_output: bool = False,
    unchanged: bool = True,
) -> None:
    before = packet_fingerprint(packet)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / name
    request = directory / f"{name}-request.json"
    request.write_bytes(raw)
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert caught.value.code == code
    assert str(caught.value) == code
    assert _CANARY_NOTE not in str(caught.value)
    assert _CANARY_REASON not in str(caught.value)
    assert output.exists() if keep_output else not output.exists()
    if unchanged:
        assert packet_fingerprint(packet) == before
    assert list(directory.glob(".job-quote-*")) == []


def _subject_sample() -> ReviewedSubject:
    return ReviewedSubject(
        packet_version="1.0.0",
        manifest_sha256="a" * 64,
        job_id="JOB",
        estimate_id="EST",
        bid_id="BID",
        proposal_id="PROP",
        revision="Draft 1",
        currency="USD",
        quantity=1,
        quote_price=1.0,
        economic_status="draft",
    )


def _record_sample(**overrides: object) -> PriceReviewRecord:
    fields: dict[str, object] = {
        "review_id": "REVIEW-1",
        "reviewed_at": "2026-10-25T16:00:00Z",
        "reviewer_ref": "person-demo-001",
        "reviewer_role": "price-reviewer",
        "decision": "approve_price",
        "reason": "stated reason",
        "internal_notes": (),
        "subject": _subject_sample(),
        "proposal_sha256": "b" * 64,
        "review_request_sha256": "c" * 64,
        "verification_sha256": "d" * 64,
    }
    fields.update(overrides)
    return PriceReviewRecord(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
@pytest.mark.parametrize("decision", ["approve_price", "request_changes", "reject"])
def test_each_decision_records_the_retained_subject(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    decision: str,
) -> None:
    packet = copy_saved_packet(generated_packets[variant], tmp_path / "packet")
    before = packet_fingerprint(packet)
    raw = _request(
        packet,
        decision=decision,
        review_id=f"REVIEW-{variant}-{decision}",
        reason=_CANARY_REASON,
        internal_notes=[_CANARY_NOTE],
    )
    validate_instance(json.loads(raw), _REQUEST_SCHEMA, label="price review request")
    recorded, output = _record(packet, tmp_path, raw, name=f"out-{variant}-{decision}")
    price = _PRICES[variant]
    manifest_sha = hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    assert recorded.decision == decision
    assert recorded.review_id == f"REVIEW-{variant}-{decision}"
    assert recorded.quote_price == price
    assert recorded.manifest_sha256 == manifest_sha
    assert packet_fingerprint(packet) == before

    review = json.loads((output / "review.json").read_text(encoding="utf-8"))
    validate_instance(review, _RESULT_SCHEMA, label="price review")
    assert set(review) == _REVIEW_KEYS
    assert review["decision"] == decision
    assert review["authority"] == AUTHORITY
    assert review["reviewer_identity_assurance"] == IDENTITY_ASSURANCE
    assert review["cost_basis_acknowledgment"] == COST_ACKNOWLEDGMENT
    assert review["verification_contract"] == VERIFICATION_CONTRACT
    assert review["verification_authority"] == VERIFICATION_AUTHORITY
    assert review["internal_notes"] == [_CANARY_NOTE]
    assert review["reason"] == _CANARY_REASON
    subject = review["subject"]
    assert set(subject) == _SUBJECT_KEYS
    assert subject["packet_version"] == _VERSIONS[variant]
    assert subject["economic_status"] == "draft"
    assert subject["manifest_sha256"] == manifest_sha
    assert subject["quote_price"] == price
    assert subject["currency"] == "USD"
    assert subject["quantity"] == 1
    assert subject["revision"] == "Draft 1"
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    assert subject["job_id"] == manifest["job_id"]
    assert subject["estimate_id"] == manifest["estimate_id"]
    assert subject["bid_id"] == manifest["bid_id"]
    assert subject["proposal_id"] == manifest["proposal_id"]
    for relative in ("manifest.json", "customer/proposal.json", "internal/bid.json"):
        assert json.loads((packet / relative).read_text(encoding="utf-8"))["status"] == "draft"

    proposal_bytes = (packet / "customer" / "proposal.json").read_bytes()
    verification_bytes = (output / "verification.json").read_bytes()
    assert (output / "review_request.json").read_bytes() == raw
    assert review["review_request_sha256"] == hashlib.sha256(raw).hexdigest()
    assert review["proposal_sha256"] == hashlib.sha256(proposal_bytes).hexdigest()
    assert review["verification_sha256"] == hashlib.sha256(verification_bytes).hexdigest()
    artifact = next(
        item for item in manifest["artifacts"] if item["path"] == "customer/proposal.json"
    )
    assert artifact["sha256"] == review["proposal_sha256"]
    verification = json.loads(verification_bytes)
    assert verification["result"] == "valid"
    assert verification["anchor_status"] == "matched"
    assert verification["expected_manifest_sha256"] == manifest_sha
    assert verification["authority"] == "verification_only"
    fresh = verify_job_quote_packet(packet, manifest_sha)
    assert verification_bytes == dumps_json(verification_payload(fresh))

    rendered = (output / "review.md").read_text(encoding="utf-8")
    bundle_text = (output / "review.json").read_text(encoding="utf-8") + rendered
    assert f"{price:.2f}" in bundle_text
    assert _COSTS[variant] not in bundle_text
    assert _CANARY_NOTE in rendered
    assert _CANARY_REASON in rendered
    assert "does not authenticate" in rendered
    assert "does not release manufacturing" in rendered
    assert "customer-send permission" in rendered
    own = hashlib.sha256((output / "review.json").read_bytes()).hexdigest()
    summary = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert own not in bundle_text
    assert summary not in bundle_text
    packet_bytes = b"".join(
        path.read_bytes() for path in packet.rglob("*") if path.is_file() and not path.is_symlink()
    )
    assert _CANARY_NOTE.encode() not in packet_bytes
    assert _CANARY_REASON.encode() not in packet_bytes
    internal_text = "\n".join(
        (packet / relative).read_text(encoding="utf-8")
        for relative in (
            "internal/estimate.json",
            "internal/bid.json",
            "internal/cost_report.md",
        )
    )
    assert _COSTS[variant] in internal_text
    assert sorted(path.name for path in output.iterdir()) == [
        "review.json",
        "review.md",
        "review_request.json",
        "verification.json",
    ]
    rejected = verify_job_quote_packet(output)
    assert rejected.result == "invalid"
    assert rejected.errors[0].code == "INVENTORY_MISMATCH"
    assert not (packet / "customer" / "review.json").exists()


def test_same_bytes_produce_the_same_bundle(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    left = copy_saved_packet(generated_packets["a"], tmp_path / "left-packet")
    right = copy_saved_packet(generated_packets["a"], tmp_path / "right-packet")
    raw = _request(left, decision="request_changes", internal_notes=[])
    _, left_out = _record(left, tmp_path, raw, name="left-review")
    _, right_out = _record(right, tmp_path, raw, name="right-review")
    for name in ("review_request.json", "verification.json", "review.json", "review.md"):
        assert (left_out / name).read_bytes() == (right_out / name).read_bytes()
    rendered = (left_out / "review.md").read_text(encoding="utf-8")
    assert "(none)" in rendered
    assert "private note" not in rendered


def test_later_decision_needs_a_new_destination(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    first_raw = _request(packet, decision="approve_price", review_id="REVIEW-FIRST")
    recorded, output = _record(packet, tmp_path, first_raw, name="first")
    original = (output / "review.json").read_bytes()
    second_raw = _request(packet, decision="reject", review_id="REVIEW-SECOND")
    _refuse(packet, tmp_path, second_raw, "OUTPUT_EXISTS", name="first", keep_output=True)
    assert (output / "review.json").read_bytes() == original
    assert recorded.decision == "approve_price"
    _, second = _record(packet, tmp_path, second_raw, name="second")
    assert json.loads((second / "review.json").read_text(encoding="utf-8"))["decision"] == "reject"
    assert json.loads((output / "review.json").read_text(encoding="utf-8"))["decision"] == (
        "approve_price"
    )
    assert "latest" not in original.decode()
    assert "superseded" not in (second / "review.json").read_text(encoding="utf-8")


def test_relocated_packet_still_requires_the_retained_digest(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "relocated")
    assert not (tmp_path / "fixtures").exists()
    raw = _request(packet, decision="reject", review_id="REVIEW-RELOCATED")
    recorded, _output = _record(packet, tmp_path, raw, name="relocated-review")
    assert recorded.quote_price == 1320.13
    assert recorded.decision == "reject"
    payload = json.loads(raw)
    del payload["expected_manifest_sha256"]
    _refuse(packet, tmp_path, _dump(payload), "REQUEST_INVALID", name="no-digest")


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        ("missing", "REQUEST_INVALID"),
        ("short", "REQUEST_INVALID"),
        ("upper", "REQUEST_INVALID"),
        ("mismatch", "VERIFICATION_REJECTED ANCHOR_MISMATCH"),
    ],
)
def test_anchor_must_be_the_retained_lowercase_digest(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    mutate: str,
    code: str,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / f"packet-{mutate}")
    payload = json.loads(_request(packet))
    if mutate == "missing":
        del payload["expected_manifest_sha256"]
    elif mutate == "short":
        payload["expected_manifest_sha256"] = "ab" * 16
    elif mutate == "upper":
        payload["expected_manifest_sha256"] = str(payload["expected_manifest_sha256"]).upper()
    else:
        payload["expected_manifest_sha256"] = "0" * 64
    forged = tmp_path / f"forged-{mutate}.json"
    forged.write_text('{"result":"valid","authority":"authenticated_approval"}\n', encoding="utf-8")
    _refuse(packet, tmp_path, _dump(payload), code, name=f"anchor-{mutate}")
    assert forged.read_text(encoding="utf-8").startswith('{"result":"valid"')
    unanchored = verify_job_quote_packet(packet)
    assert unanchored.result == "valid"
    assert unanchored.anchor_status == "not_supplied"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("job_id", "JOB-OTHER-001", "SUBJECT_MISMATCH job_id"),
        ("estimate_id", "EST-OTHER-001", "SUBJECT_MISMATCH estimate_id"),
        ("bid_id", "BID-OTHER-001", "SUBJECT_MISMATCH bid_id"),
        ("proposal_id", "PROP-OTHER-001", "SUBJECT_MISMATCH proposal_id"),
        ("revision", "Draft 2", "SUBJECT_MISMATCH revision"),
        ("quote_price", 1.0, "SUBJECT_MISMATCH quote_price"),
        ("currency", "EUR", "REQUEST_INVALID"),
        ("quantity", 2, "REQUEST_INVALID"),
    ],
)
def test_stated_subject_must_match_the_capture(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    field: str,
    value: object,
    code: str,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / f"packet-{field}")
    payload = json.loads(_request(packet, reason=_CANARY_REASON, internal_notes=[_CANARY_NOTE]))
    payload["reviewed_subject"][field] = value
    _refuse(packet, tmp_path, _dump(payload), code, name=f"subject-{field}")


@pytest.mark.parametrize(
    "raw_price",
    ["true", "false", "-1", "1320.135", "NaN", "Infinity"],
)
def test_non_cent_prices_are_invalid_requests(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    raw_price: str,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / f"packet-{raw_price}")
    payload = json.loads(_request(packet))
    text = _dump(payload).decode("utf-8")
    price = payload["reviewed_subject"]["quote_price"]
    replaced = text.replace(f'"quote_price": {price}', f'"quote_price": {raw_price}', 1)
    assert replaced != text
    _refuse(packet, tmp_path, replaced.encode(), "REQUEST_INVALID", name=f"price-{raw_price}")


def test_fraction_of_a_cent_is_refused_before_money_rounding(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    payload = json.loads(_request(packet))
    payload["reviewed_subject"]["quote_price"] = 1320.134
    _refuse(packet, tmp_path, _dump(payload), "REQUEST_INVALID", name="fraction")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_type", "cnc_job_quote_price_review"),
        ("record_version", "9.9.9"),
        ("decision", "approve"),
        ("reviewer_ref", " "),
        ("reviewer_role", ""),
        ("reason", "\n"),
        ("reviewed_at", "2026-02-31T00:00:00Z"),
        ("review_id", "../outside"),
        ("signed_by", "person-demo-001"),
        ("identity_verified", True),
        ("release", "REL-1"),
        ("sent", True),
        ("authority", AUTHORITY),
    ],
)
def test_request_contract_rejects_unknown_or_blank_claims(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / f"packet-{field}")
    payload = json.loads(_request(packet, internal_notes=[_CANARY_NOTE]))
    payload[field] = value
    _refuse(packet, tmp_path, _dump(payload), "REQUEST_INVALID", name=f"request-{field}")


def test_duplicate_keys_are_invalid_requests(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    text = _request(packet).decode("utf-8")
    duplicated = text.replace('"decision":', '"decision": "reject", "decision":', 1)
    _refuse(packet, tmp_path, duplicated.encode(), "REQUEST_INVALID", name="duplicate")


def test_reviewed_at_must_not_precede_the_captured_creation(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    created = datetime.strptime("2026-10-25T16:00:00Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    earlier = (created - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = (created + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _refuse(
        packet,
        tmp_path,
        _request(packet, reviewed_at=earlier),
        "REVIEWED_AT_BEFORE_CREATION",
        name="earlier",
    )
    recorded, _output = _record(
        packet,
        tmp_path,
        _request(packet, reviewed_at=later, review_id="REVIEW-LATER"),
        name="later",
    )
    assert recorded.decision == "approve_price"


@pytest.mark.parametrize("decision", ["approve_price", "request_changes", "reject"])
def test_tampered_packet_refuses_every_decision(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    decision: str,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / f"packet-{decision}")
    raw = _request(packet, decision=decision, review_id=f"REVIEW-TAMPER-{decision}")
    report = packet / "internal" / "cost_report.md"
    report.write_bytes(report.read_bytes() + b"\n")
    _refuse(
        packet,
        tmp_path,
        raw,
        "VERIFICATION_REJECTED HASH_MISMATCH",
        name=f"tamper-{decision}",
    )


def test_rehashed_price_refuses_recording(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    retained = _request(packet, decision="reject", review_id="REVIEW-RETAINED")
    bid_path = packet / "internal" / "bid.json"
    bid = json.loads(bid_path.read_text(encoding="utf-8"))
    bid["pricing"]["quote_price"] = 1.0
    bid["pricing"]["price_per_unit"] = 1.0
    bid_path.write_bytes(dumps_json(bid))
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        entry["sha256"] = hashlib.sha256((packet / entry["path"]).read_bytes()).hexdigest()
    for entry in manifest["sources"]:
        entry["sha256"] = hashlib.sha256((packet / entry["snapshot_ref"]).read_bytes()).hexdigest()
    (packet / "manifest.json").write_bytes(dumps_json(manifest))
    _refuse(
        packet,
        tmp_path,
        retained,
        "VERIFICATION_REJECTED ANCHOR_MISMATCH",
        name="retained-anchor",
    )
    edited = _request(packet, decision="reject", review_id="REVIEW-REHASH")
    _refuse(packet, tmp_path, edited, "VERIFICATION_REJECTED REPLAY_MISMATCH", name="rehash")


def test_disk_change_after_capture_prevents_publication(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    original = (packet / "customer" / "proposal.json").read_bytes()
    raw = _request(packet)
    from business.workflows.price_review import ensure_captured_unchanged

    def swap(verified: object) -> None:
        captured = verified.captured  # type: ignore[attr-defined]
        assert captured.files["customer/proposal.json"] == original
        (packet / "customer" / "proposal.json").write_bytes(original + b"\n")
        ensure_captured_unchanged(verified)  # type: ignore[arg-type]

    monkeypatch.setattr("business.workflows.price_review.ensure_captured_unchanged", swap)
    _refuse(packet, tmp_path, raw, "PACKET_CHANGED", name="changed", unchanged=False)


def test_published_subject_stays_on_the_capture_if_disk_changes(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    original = (packet / "customer" / "proposal.json").read_bytes()
    raw = _request(packet, review_id="REVIEW-CAPTURE")

    def swap_and_ignore(_verified: object) -> None:
        (packet / "customer" / "proposal.json").write_bytes(b'{"total_price": 1}\n')

    monkeypatch.setattr(
        "business.workflows.price_review.ensure_captured_unchanged",
        swap_and_ignore,
    )
    _recorded, output = _record(packet, tmp_path, raw, name="captured")
    review = json.loads((output / "review.json").read_text(encoding="utf-8"))
    assert review["subject"]["quote_price"] == 1001.27
    assert review["proposal_sha256"] == hashlib.sha256(original).hexdigest()
    assert (packet / "customer" / "proposal.json").read_bytes() != original


def test_relative_paths_resolve_from_the_working_directory(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "request.json").write_bytes(_request(packet, review_id="REVIEW-RELATIVE"))
    monkeypatch.chdir(tmp_path)
    recorded = record_price_review(
        packet_dir="packet",
        request_path="nested/../request.json",
        output_dir="reviews/one",
    )
    assert recorded.output_dir == (tmp_path / "reviews" / "one").resolve().as_posix()
    assert (tmp_path / "reviews" / "one" / "review.json").is_file()


@pytest.mark.parametrize(
    "output_dir",
    [
        "../outside",
        "reviews/../../outside",
        "file://reviews/one",
        "reviews\\one",
        "  reviews",
        "",
    ],
)
def test_parent_traversal_and_unsafe_output_spellings_are_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_dir: str,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    work = tmp_path / "work"
    work.mkdir()
    request = work / "request.json"
    request.write_bytes(_request(packet))
    monkeypatch.chdir(work)
    before = packet_fingerprint(packet)
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(packet),
            request_path="request.json",
            output_dir=output_dir,
        )
    assert caught.value.code == "OUTPUT_REFUSED"
    assert not (tmp_path / "outside").exists()
    assert packet_fingerprint(packet) == before


def test_output_inside_the_packet_is_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    raw = _request(packet)
    for relative in ("reviews/one", "customer/review-out"):
        destination = packet / relative
        request = tmp_path / f"request-{relative.replace('/', '-')}.json"
        request.write_bytes(raw)
        before = packet_fingerprint(packet)
        with pytest.raises(PriceReviewRefusalError) as caught:
            record_price_review(
                packet_dir=str(packet),
                request_path=str(request),
                output_dir=str(destination),
            )
        assert caught.value.code == "OUTPUT_REFUSED"
        assert not destination.exists()
        assert packet_fingerprint(packet) == before


def test_output_that_would_contain_the_packet_is_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    holder = tmp_path / "holder"
    holder.mkdir()
    packet = copy_saved_packet(generated_packets["a"], holder / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    output = tmp_path / "fresh-parent"
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(output / "missing-packet"),
            request_path=str(request),
            output_dir=str(output),
        )
    assert caught.value.code == "OUTPUT_REFUSED"
    assert not output.exists()


def test_symlink_output_components_are_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep.txt").write_bytes(b"keep")
    link = tmp_path / "linked-out"
    link.symlink_to(target)
    parent = tmp_path / "linked-parent"
    parent.symlink_to(tmp_path / "other-parent", target_is_directory=True)
    before = packet_fingerprint(packet)
    for output in (link, parent / "bundle"):
        with pytest.raises(PriceReviewRefusalError) as caught:
            record_price_review(
                packet_dir=str(packet),
                request_path=str(request),
                output_dir=str(output),
            )
        assert caught.value.code == "OUTPUT_REFUSED"
    assert (target / "keep.txt").read_bytes() == b"keep"
    assert link.is_symlink()
    assert not (tmp_path / "other-parent").exists()
    assert packet_fingerprint(packet) == before


def test_existing_output_is_kept(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    output = tmp_path / "exists"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_bytes(b"keep")
    _refuse(packet, tmp_path, _request(packet), "OUTPUT_EXISTS", name="exists", keep_output=True)
    assert marker.read_bytes() == b"keep"


def test_request_symlink_and_directory_are_unsafe(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    output = tmp_path / "out"
    real = tmp_path / "request.json"
    real.write_bytes(_request(packet))
    link = tmp_path / "request-link.json"
    link.symlink_to(real)
    folder = tmp_path / "request-dir"
    folder.mkdir()
    for request in (link, folder):
        with pytest.raises(PriceReviewRefusalError) as caught:
            record_price_review(
                packet_dir=str(packet),
                request_path=str(request),
                output_dir=str(output),
            )
        assert caught.value.code == "REQUEST_UNSAFE"
        assert not output.exists()


def test_missing_request_is_invalid(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(tmp_path / "missing.json"),
            output_dir=str(tmp_path / "out"),
        )
    assert caught.value.code == "REQUEST_INVALID"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["empty_directory", "file", "symlink"])
def test_destination_created_during_publication_survives(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    from business.workflows import reporting

    packet = copy_saved_packet(generated_packets["v1"], tmp_path / f"packet-{kind}")
    output = tmp_path / f"raced-{kind}"
    request = tmp_path / f"request-{kind}.json"
    request.write_bytes(_request(packet, review_id=f"REVIEW-RACE-{kind}"))
    real_rename = reporting._rename_without_replacement
    identity: list[object] = []

    def raced_rename(source: Path, target: Path) -> None:
        if kind == "empty_directory":
            target.mkdir()
        elif kind == "file":
            target.write_bytes(b"concurrently created file")
        else:
            target.symlink_to(tmp_path / "other-target")
        identity.append(target.lstat().st_ino)
        real_rename(source, target)

    monkeypatch.setattr(reporting, "_rename_without_replacement", raced_rename)
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert caught.value.code == "OUTPUT_EXISTS"
    assert output.lstat().st_ino == identity[0]
    if kind == "empty_directory":
        assert list(output.iterdir()) == []
    elif kind == "file":
        assert output.read_bytes() == b"concurrently created file"
    else:
        assert output.is_symlink()
        assert not (tmp_path / "other-target").exists()
    assert list(output.parent.glob(".job-quote-*")) == []


def test_publish_failure_leaves_no_bundle(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    output = tmp_path / "unpublished"

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr("business.workflows.reporting._rename_without_replacement", boom)
    with pytest.raises(PriceReviewFailureError, match="could not be published"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert not output.exists()
    assert list(tmp_path.glob(".job-quote-*")) == []


def test_unavailable_exclusive_rename_leaves_no_bundle(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from business.workflows import reporting

    if reporting.os.name == "nt":
        pytest.skip("Windows os.rename already provides no-replacement semantics")
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    output = tmp_path / "unavailable"
    monkeypatch.setattr(reporting.ctypes, "CDLL", lambda *_args, **_kwargs: object())
    with pytest.raises(PriceReviewFailureError, match="could not be published"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert not output.exists()
    assert list(tmp_path.glob(".job-quote-*")) == []


def test_contract_failure_is_operational(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    output = tmp_path / "bad-contract"
    monkeypatch.setattr("business.workflows.price_review.review_payload", lambda _record: {})
    with pytest.raises(PriceReviewFailureError, match="failed its contract"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert not output.exists()
    assert list(tmp_path.glob(".job-quote-*")) == []


def test_request_read_failure_is_operational(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    real_open = os.open

    def guarded(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(os.fspath(path)) == request:
            raise OSError("unreadable request")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", guarded)
    with pytest.raises(PriceReviewFailureError, match="could not be read"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(tmp_path / "out"),
        )
    assert not (tmp_path / "out").exists()


def test_recording_does_not_open_a_socket_or_process(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("price review must not open a socket or launch a process")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    recorded, _output = _record(packet, tmp_path, _request(packet, decision="reject"), name="quiet")
    assert recorded.decision == "reject"


def test_overridden_authority_labels_are_rejected() -> None:
    with pytest.raises(ValueError, match="caller-asserted only"):
        _record_sample(authority="authenticated_approval")
    with pytest.raises(ValueError, match="caller-asserted"):
        _record_sample(reviewer_identity_assurance="verified")
    with pytest.raises(ValueError, match="cost acknowledgment"):
        _record_sample(cost_basis_acknowledgment="commercially_complete")
    with pytest.raises(ValueError, match="verification contract"):
        _record_sample(verification_contract="approval_certificate")
    with pytest.raises(ValueError, match="verification authority"):
        _record_sample(verification_authority="manufacturing_release")
    with pytest.raises(ValueError, match="record identity"):
        _record_sample(record_type="cnc_job_quote_approval")
    with pytest.raises(ValueError, match="not supported"):
        _record_sample(decision="approve")
    subject = _subject_sample()
    with pytest.raises(ValueError, match="stays draft"):
        _record_sample(subject=_replaced_subject(subject, economic_status="approved"))
    with pytest.raises(ValueError, match="quantity 1 USD"):
        _record_sample(subject=_replaced_subject(subject, currency="EUR"))
    with pytest.raises(ValueError, match="packet version"):
        _record_sample(subject=_replaced_subject(subject, packet_version="9.9.9"))


def _replaced_subject(subject: ReviewedSubject, **changes: object) -> ReviewedSubject:
    fields = {
        "packet_version": subject.packet_version,
        "manifest_sha256": subject.manifest_sha256,
        "job_id": subject.job_id,
        "estimate_id": subject.estimate_id,
        "bid_id": subject.bid_id,
        "proposal_id": subject.proposal_id,
        "revision": subject.revision,
        "currency": subject.currency,
        "quantity": subject.quantity,
        "quote_price": subject.quote_price,
        "economic_status": subject.economic_status,
    }
    fields.update(changes)
    return ReviewedSubject(**fields)  # type: ignore[arg-type]


def test_blank_request_path_is_invalid(tmp_path: Path) -> None:
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(tmp_path),
            request_path=" request.json",
            output_dir=str(tmp_path / "out"),
        )
    assert caught.value.code == "REQUEST_INVALID"


def test_request_stat_and_read_failures_use_stable_codes(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["a"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    output = tmp_path / "out"
    real_lstat = Path.lstat

    def broken_lstat(self: Path):
        if self == request:
            raise OSError("stat failed")
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", broken_lstat)
    with pytest.raises(PriceReviewFailureError, match="could not be read"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    monkeypatch.undo()

    real_open = os.open

    def missing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(os.fspath(path)) == request:
            raise FileNotFoundError(path)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", missing_open)
    with pytest.raises(PriceReviewRefusalError) as missing:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert missing.value.code == "REQUEST_INVALID"
    monkeypatch.undo()

    def looped_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(os.fspath(path)) == request:
            raise OSError(errno.ELOOP, "too many links")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", looped_open)
    with pytest.raises(PriceReviewRefusalError) as looped:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert looped.value.code == "REQUEST_UNSAFE"
    monkeypatch.undo()

    real_fdopen = os.fdopen

    class _BrokenRead:
        def __init__(self, handle: object) -> None:
            self._handle = handle

        def __enter__(self) -> _BrokenRead:
            return self

        def __exit__(self, *_args: object) -> None:
            close = getattr(self._handle, "close", None)
            if close:
                close()

        def read(self) -> bytes:
            raise OSError("read failed")

    def broken_fdopen(fd: int, mode: str = "r", *args: object, **kwargs: object):
        handle = real_fdopen(fd, mode, *args, **kwargs)  # type: ignore[arg-type]
        if mode == "rb":
            return _BrokenRead(handle)
        return handle

    monkeypatch.setattr(os, "fdopen", broken_fdopen)
    with pytest.raises(PriceReviewFailureError, match="could not be read"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(output),
        )
    assert not output.exists()


def test_output_inspection_failures_are_operational(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["b"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    real_is_symlink = Path.is_symlink

    def broken_symlink(self: Path) -> bool:
        if self.name == "inspected":
            raise OSError("inspect failed")
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", broken_symlink)
    with pytest.raises(PriceReviewFailureError, match="could not be inspected"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(tmp_path / "inspected"),
        )
    monkeypatch.undo()
    real_resolve = Path.resolve

    def broken_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "resolved":
            raise OSError("resolve failed")
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", broken_resolve)
    with pytest.raises(PriceReviewFailureError, match="could not be inspected"):
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(tmp_path / "resolved"),
        )


def test_file_parent_and_dot_component_are_refused(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = copy_saved_packet(generated_packets["v1"], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(_request(packet))
    blocker = tmp_path / "not-a-directory"
    blocker.write_bytes(b"blocked")
    with pytest.raises(PriceReviewRefusalError) as caught:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir=str(blocker / "child"),
        )
    assert caught.value.code == "OUTPUT_REFUSED"
    assert blocker.read_bytes() == b"blocked"
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: Path("/tmp/price-review/..")))
    with pytest.raises(PriceReviewRefusalError) as lexical:
        record_price_review(
            packet_dir=str(packet),
            request_path=str(request),
            output_dir="review",
        )
    assert lexical.value.code == "OUTPUT_REFUSED"


def _verification() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="JOB",
        estimate_id="EST",
        bid_id="BID",
        proposal_id="PROP",
        economic_status="draft",
        manifest_sha256="a" * 64,
        packet_version="1.0.0",
    )


def _captured_files() -> tuple[dict[str, object], dict[str, bytes]]:
    manifest: dict[str, object] = {
        "job_id": "JOB",
        "estimate_id": "EST",
        "bid_id": "BID",
        "proposal_id": "PROP",
        "status": "draft",
        "cost_basis_disclosure": {
            "basis": "direct_manufacturing_cost_only",
            "tool_wear_pct": 0,
            "manufacturing_contingency_pct": 0,
            "business_overhead_pct": 0,
            "engineering_recovery_pct": 0,
        },
        "artifacts": [{"path": "customer/proposal.json", "sha256": "b" * 64}],
    }
    proposal: dict[str, object] = {
        "proposal_id": "PROP",
        "source_bid_id": "BID",
        "revision": "Draft 1",
        "status": "draft",
        "pricing": {
            "currency": "USD",
            "quantity": 1,
            "total_price": 1.0,
            "price_per_unit": 1.0,
        },
    }
    bid: dict[str, object] = {
        "bid_id": "BID",
        "status": "draft",
        "pricing": {
            "quote_price": 1.0,
            "tool_wear_pct": 0,
            "manufacturing_contingency_pct": 0,
            "business_overhead_pct": 0,
            "engineering_recovery_pct": 0,
        },
    }
    request = {
        "expected_manifest_sha256": "a" * 64,
        "reviewed_subject": {
            "job_id": "JOB",
            "estimate_id": "EST",
            "bid_id": "BID",
            "proposal_id": "PROP",
            "revision": "Draft 1",
            "currency": "USD",
            "quantity": 1,
            "quote_price": 1.0,
        },
    }
    files = {
        "manifest.json": dumps_json(manifest),
        "customer/proposal.json": dumps_json(proposal),
        "internal/bid.json": dumps_json(bid),
    }
    return request, files


def test_captured_subject_comparisons_refuse_internal_disagreements() -> None:
    request, files = _captured_files()
    subject = _matched_subject(request, files, _verification())
    assert subject.quote_price == 1.0
    assert subject.economic_status == "draft"

    def refuse(mutator, code: str) -> None:
        current_request, current_files = _captured_files()
        mutator(current_request, current_files)
        with pytest.raises(PriceReviewRefusalError) as caught:
            _matched_subject(current_request, current_files, _verification())
        assert caught.value.code == code

    def proposal_id(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["customer/proposal.json"])
        payload["proposal_id"] = "OTHER"
        current["customer/proposal.json"] = dumps_json(payload)

    def source_bid(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["customer/proposal.json"])
        payload["source_bid_id"] = "OTHER"
        current["customer/proposal.json"] = dumps_json(payload)

    def pricing(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["customer/proposal.json"])
        payload["pricing"] = []
        current["customer/proposal.json"] = dumps_json(payload)

    def currency(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["customer/proposal.json"])
        payload["pricing"]["currency"] = "EUR"
        current["customer/proposal.json"] = dumps_json(payload)

    def quantity(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["customer/proposal.json"])
        payload["pricing"]["quantity"] = 2
        current["customer/proposal.json"] = dumps_json(payload)

    def status(_request: dict[str, object], current: dict[str, bytes]) -> None:
        payload = json.loads(current["manifest.json"])
        payload["status"] = "sent"
        current["manifest.json"] = dumps_json(payload)

    refuse(proposal_id, "SUBJECT_MISMATCH proposal_id")
    refuse(source_bid, "SUBJECT_MISMATCH bid_id")
    refuse(pricing, "SUBJECT_MISMATCH quote_price")
    refuse(currency, "SUBJECT_MISMATCH currency")
    refuse(quantity, "SUBJECT_MISMATCH quantity")
    refuse(status, "SUBJECT_MISMATCH economic_status")

    mismatched = _verification()
    mismatched.manifest_sha256 = "c" * 64
    with pytest.raises(PriceReviewRefusalError) as digest:
        _matched_subject(request, files, mismatched)
    assert digest.value.code == "SUBJECT_MISMATCH manifest_sha256"
    mismatched.manifest_sha256 = "a" * 64
    mismatched.packet_version = "9.9.9"
    with pytest.raises(PriceReviewRefusalError) as version:
        _matched_subject(request, files, mismatched)
    assert version.value.code == "SUBJECT_MISMATCH packet_version"


def test_cost_basis_and_hash_binding_refuse_disagreement() -> None:
    _request, files = _captured_files()
    manifest = json.loads(files["manifest.json"])
    bid = json.loads(files["internal/bid.json"])
    _require_direct_cost_only(manifest, bid["pricing"])
    manifest["cost_basis_disclosure"] = []
    with pytest.raises(PriceReviewRefusalError) as missing:
        _require_direct_cost_only(manifest, bid["pricing"])
    assert missing.value.code == "SUBJECT_MISMATCH cost_basis"
    manifest["cost_basis_disclosure"] = {"basis": "complete", "tool_wear_pct": 0}
    with pytest.raises(PriceReviewRefusalError) as basis:
        _require_direct_cost_only(manifest, bid["pricing"])
    assert basis.value.code == "SUBJECT_MISMATCH cost_basis"
    manifest["cost_basis_disclosure"] = {
        "basis": "direct_manufacturing_cost_only",
        "tool_wear_pct": 1,
        "manufacturing_contingency_pct": 0,
        "business_overhead_pct": 0,
        "engineering_recovery_pct": 0,
    }
    with pytest.raises(PriceReviewRefusalError) as factor:
        _require_direct_cost_only(manifest, bid["pricing"])
    assert factor.value.code == "SUBJECT_MISMATCH cost_basis"
    bid["pricing"]["tool_wear_pct"] = True
    manifest["cost_basis_disclosure"]["tool_wear_pct"] = 0
    with pytest.raises(PriceReviewRefusalError) as boolean_zero:
        _require_direct_cost_only(manifest, bid["pricing"])
    assert boolean_zero.value.code == "SUBJECT_MISMATCH cost_basis"

    record = _record_sample(proposal_sha256="b" * 64)
    wrong_entry = json.loads(files["manifest.json"])
    wrong_entry["artifacts"][0]["sha256"] = "c" * 64
    wrong_files = dict(files)
    wrong_files["manifest.json"] = dumps_json(wrong_entry)
    with pytest.raises(PriceReviewRefusalError) as entry:
        _require_bound_hashes(record, wrong_files, files["customer/proposal.json"])
    assert entry.value.code == "SUBJECT_MISMATCH proposal_sha256"
    with pytest.raises(PriceReviewRefusalError) as bound:
        _require_bound_hashes(record, files, b"not-the-proposal")
    assert bound.value.code == "SUBJECT_MISMATCH proposal_sha256"
    broken = json.loads(files["manifest.json"])
    broken["artifacts"] = "none"
    files["manifest.json"] = dumps_json(broken)
    with pytest.raises(PriceReviewRefusalError) as artifacts:
        _require_bound_hashes(record, files, b"not-the-proposal")
    assert artifacts.value.code == "SUBJECT_MISMATCH proposal_sha256"
    with pytest.raises(PriceReviewRefusalError) as parsed:
        _object(b"[]", "manifest")
    assert parsed.value.code == "SUBJECT_MISMATCH"


def test_money_helpers_reject_bools_and_non_cent_values() -> None:
    assert _cent_valued(1) is True
    assert _cent_valued(1.255) is False
    assert _cent_valued(True) is False
    assert _cent_valued("1") is False
    assert _cent_valued(float("nan")) is False
    assert _cent_valued(-0.01) is False
    assert _is_zero(0) is True
    assert _is_zero(0.0) is True
    assert _is_zero(False) is False
    assert _is_zero("0") is False
