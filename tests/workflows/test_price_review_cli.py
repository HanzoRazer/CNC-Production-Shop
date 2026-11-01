"""CLI exits for a caller-asserted price review. The command does not send or release."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from business.workflows.cli import main
from tests.workflows.conftest import copy_saved_packet, price_review_request_bytes

_PRICES = {"v1": 1320.13, "a": 1001.27, "b": 1043.70}
_CANARY_NOTE = "CANARY-PRIVATE-NOTE"
_CANARY_REASON = "CANARY-RATIONALE stays in the bundle."


def _prepare(
    tmp_path: Path,
    generated_packets: dict[str, Path],
    variant: str,
    decision: str,
) -> tuple[Path, Path, Path]:
    packet = copy_saved_packet(generated_packets[variant], tmp_path / "packet")
    request = tmp_path / "request.json"
    request.write_bytes(
        price_review_request_bytes(
            packet,
            decision=decision,
            review_id=f"REVIEW-CLI-{variant}-{decision}",
            reason=_CANARY_REASON,
            internal_notes=[_CANARY_NOTE],
        )
    )
    return packet, request, tmp_path / "review-out"


def _run(
    tmp_path: Path,
    packet: Path,
    request: Path,
    output: Path,
    *,
    relative: bool,
) -> subprocess.CompletedProcess[str]:
    if relative:
        command = [
            sys.executable,
            "-m",
            "business.workflows.cli",
            "record-price-review",
            "--packet-dir",
            packet.name,
            "--request",
            request.name,
            "--output-dir",
            output.name,
        ]
        cwd = tmp_path
    else:
        command = [
            sys.executable,
            "-m",
            "business.workflows.cli",
            "record-price-review",
            "--packet-dir",
            str(packet),
            "--request",
            str(request),
            "--output-dir",
            str(output),
        ]
        cwd = tmp_path / "elsewhere"
        cwd.mkdir(exist_ok=True)
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
@pytest.mark.parametrize("decision", ["approve_price", "request_changes", "reject"])
def test_cli_prints_the_stated_decision_and_keeps_notes_internal(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
    decision: str,
) -> None:
    packet, request, output = _prepare(tmp_path, generated_packets, variant, decision)
    result = _run(tmp_path, packet, request, output, relative=variant == "v1")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    manifest = hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    expected = "\n".join(
        [
            f"decision: {decision}",
            f"review_id: REVIEW-CLI-{variant}-{decision}",
            f"quote_price: {_PRICES[variant]:.2f}",
            f"manifest_sha256: {manifest}",
            "authority: caller_asserted_price_review_only",
            "reviewer_identity_assurance: caller_asserted",
            f"output_dir: {output.resolve().as_posix()}",
        ]
    )
    assert result.stdout == expected + "\n"
    assert _CANARY_NOTE not in result.stdout
    assert _CANARY_REASON not in result.stdout
    assert _CANARY_NOTE in (output / "review.md").read_text(encoding="utf-8")
    review = json.loads((output / "review.json").read_text(encoding="utf-8"))
    assert review["decision"] == decision
    assert review["subject"]["economic_status"] == "draft"
    customer = packet / "customer"
    assert sorted(path.name for path in customer.iterdir()) == ["proposal.json", "proposal.md"]


def test_help_states_cwd_digest_and_authority_limits() -> None:
    result = CliRunner().invoke(main, ["record-price-review", "--help"], terminal_width=200)
    assert result.exit_code == 0
    text = " ".join(result.output.split())
    assert "current working directory" in text
    assert "retained manifest digest is a field in this file" in text
    assert "not a digest computed from the packet directory" in text
    assert "does not authenticate the reviewer" in text
    assert "or release manufacturing" in text
    root = CliRunner().invoke(main, ["--help"])
    assert "run" in root.output
    assert "verify" in root.output
    assert "record-price-review" in root.output


def test_missing_options_and_skip_flag_are_usage_errors() -> None:
    missing = CliRunner().invoke(main, ["record-price-review"])
    assert missing.exit_code == 2
    skipped = CliRunner().invoke(
        main,
        [
            "record-price-review",
            "--packet-dir",
            "packet",
            "--request",
            "request.json",
            "--output-dir",
            "out",
            "--skip-verify",
        ],
    )
    assert skipped.exit_code != 0
    assert "No such option" in skipped.output
    assert "--skip-verify" in skipped.output


def test_invalid_request_exits_2_without_notes_or_a_bundle(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet, request, output = _prepare(tmp_path, generated_packets, "a", "reject")
    request.write_bytes(b"{}\n")
    result = _run(tmp_path, packet, request, output, relative=False)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "error: REQUEST_INVALID\n"
    assert _CANARY_NOTE not in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


def test_publish_io_failure_exits_1(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, request, output = _prepare(tmp_path, generated_packets, "b", "approve_price")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr("business.workflows.reporting._rename_without_replacement", boom)
    result = CliRunner().invoke(
        main,
        [
            "record-price-review",
            "--packet-dir",
            str(packet),
            "--request",
            str(request),
            "--output-dir",
            str(output),
        ],
    )
    assert result.exit_code == 1
    assert "error: review bundle could not be published" in result.output
    assert "Traceback" not in result.output
    assert "REQUEST_INVALID" not in result.output
    assert not output.exists()


def test_programming_failure_is_not_relabelled_as_bad_input(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, request, output = _prepare(tmp_path, generated_packets, "v1", "approve_price")

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("programming failure")

    monkeypatch.setattr("business.workflows.cli.record_price_review", boom)
    result = CliRunner().invoke(
        main,
        [
            "record-price-review",
            "--packet-dir",
            str(packet),
            "--request",
            str(request),
            "--output-dir",
            str(output),
        ],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert "REQUEST_INVALID" not in result.output
    assert not output.exists()


def test_cli_does_not_open_a_socket_or_process(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, request, output = _prepare(tmp_path, generated_packets, "a", "request_changes")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("record-price-review must not open a socket or launch a process")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    result = CliRunner().invoke(
        main,
        [
            "record-price-review",
            "--packet-dir",
            str(packet),
            "--request",
            str(request),
            "--output-dir",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((output / "review.json").read_text(encoding="utf-8"))["decision"] == (
        "request_changes"
    )
