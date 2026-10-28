"""CLI output, exits, and invocation errors for packet verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from business.workflows.cli import main
from business.workflows.loading import validate_instance
from business.workflows.verification_models import VerificationOperationalError
from tests.workflows.conftest import pristine_copy

_RESULT_SCHEMA = "workflows/job_quote_verification_v1.schema.json"


def _invoke(packet: Path, *extra: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "business.workflows.cli",
            "verify",
            "--packet-dir",
            str(packet),
            *extra,
        ],
        cwd=cwd or packet.parent,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("variant", ["v1", "a", "b"])
def test_human_summary_has_no_absolute_path(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path / "packet", variant)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = _invoke(packet, cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert result.stderr == ""
    assert "result: valid" in result.stdout
    assert "authority: verification_only" in result.stdout
    assert "economic_status: draft" in result.stdout
    assert "anchor_status: not_supplied" in result.stdout
    assert str(packet) not in result.stdout
    assert str(tmp_path) not in result.stdout


@pytest.mark.parametrize("variant", ["v1", "a"])
def test_json_result_is_deterministic_and_schema_valid(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    variant: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, variant)
    other = tmp_path / "other"
    other.mkdir()
    first = _invoke(packet, "--json", cwd=tmp_path)
    second = _invoke(packet, "--json", cwd=other)
    assert first.returncode == 0, first.stderr
    assert first.stderr == ""
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    validate_instance(payload, _RESULT_SCHEMA, label="verification")
    assert payload["result"] == "valid"
    assert payload["economic_status"] == "draft"
    assert list(payload) == sorted(payload)
    assert set(payload) == {
        "record_type",
        "record_version",
        "authority",
        "result",
        "manifest_sha256",
        "expected_manifest_sha256",
        "anchor_status",
        "packet_version",
        "economic_status",
        "job_id",
        "estimate_id",
        "bid_id",
        "proposal_id",
        "checks",
        "errors",
    }
    assert [check["name"] for check in payload["checks"]] == [
        "inventory",
        "schemas",
        "hashes",
        "source_closure",
        "replay",
    ]


def test_invalid_json_result_is_stdout_only_and_exits_2(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    report = packet / "internal" / "cost_report.md"
    report.write_bytes(report.read_bytes() + b"\n")
    result = _invoke(packet, "--json")
    assert result.returncode == 2
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["result"] == "invalid"
    assert payload["errors"] == [{"code": "HASH_MISMATCH", "member": "internal/cost_report.md"}]
    assert "progress" not in result.stdout
    assert str(packet) not in result.stdout


def test_cli_runner_renders_valid_text_and_invalid_json(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    runner = CliRunner()
    valid = runner.invoke(main, ["verify", "--packet-dir", str(packet)])
    assert valid.exit_code == 0, valid.output
    assert "result: valid" in valid.output
    assert "economic_status: draft" in valid.output
    invalid = runner.invoke(
        main,
        ["verify", "--packet-dir", str(tmp_path / "missing-packet"), "--json"],
    )
    assert invalid.exit_code == 2
    payload = json.loads(invalid.output)
    assert payload["errors"][0] == {"code": "PACKET_NOT_FOUND", "member": None}


def test_human_rejection_prints_stable_diagnostics(tmp_path: Path) -> None:
    missing = tmp_path / "missing-packet"
    result = _invoke(missing)
    assert result.returncode == 2
    assert result.stderr == ""
    assert "result: invalid" in result.stdout
    assert "anchor_status: not_checked" in result.stdout
    assert "manifest_sha256: null" in result.stdout
    assert "packet_version: null" in result.stdout
    assert "economic_status: null" in result.stdout
    assert "error: PACKET_NOT_FOUND -" in result.stdout
    assert "inventory=fail" in result.stdout
    assert "replay=not_run" in result.stdout
    assert str(tmp_path) not in result.stdout


def test_missing_packet_json_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "missing-packet"
    result = _invoke(missing, "--json")
    assert result.returncode == 2
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["errors"][0]["code"] == "PACKET_NOT_FOUND"
    assert payload["manifest_sha256"] is None
    assert payload["anchor_status"] == "not_checked"


def test_anchor_match_and_mismatch_exits(
    generated_packets: dict[str, Path],
    tmp_path: Path,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "b")
    digest = hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    matched = _invoke(packet, "--expected-manifest-sha256", digest, "--json")
    assert matched.returncode == 0, matched.stderr
    assert json.loads(matched.stdout)["anchor_status"] == "matched"
    mismatched = _invoke(packet, "--expected-manifest-sha256", "0" * 64, "--json")
    assert mismatched.returncode == 2
    assert mismatched.stderr == ""
    payload = json.loads(mismatched.stdout)
    assert payload["anchor_status"] == "mismatch"
    assert payload["errors"][0]["code"] == "ANCHOR_MISMATCH"
    assert all(check["status"] == "not_run" for check in payload["checks"])


@pytest.mark.parametrize(
    "digest",
    ["ZZ", "ABCD", "", "A" * 64, "g" * 64],
)
def test_malformed_digest_is_a_click_usage_error(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    digest: str,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")
    before = (packet / "manifest.json").read_bytes()
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["verify", "--packet-dir", str(packet), "--expected-manifest-sha256", digest],
    )
    assert result.exit_code == 2
    assert "cnc_job_quote_verification" not in result.output
    assert (packet / "manifest.json").read_bytes() == before


def test_missing_packet_dir_flag_is_a_click_usage_error() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["verify"])
    assert result.exit_code == 2
    assert "cnc_job_quote_verification" not in result.output


def test_operational_failure_uses_stderr_and_exit_1(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise VerificationOperationalError("temporary verification storage could not be created")

    monkeypatch.setattr("business.workflows.cli.verify_job_quote_packet", boom)
    runner = CliRunner()
    result = runner.invoke(main, ["verify", "--packet-dir", str(packet), "--json"])
    assert result.exit_code == 1
    assert "cnc_job_quote_verification" not in result.output
    assert "temporary verification storage" in (result.stderr or result.output)


def test_unexpected_error_is_not_reclassified_as_invalid_input(
    generated_packets: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = pristine_copy(generated_packets, tmp_path, "v1")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom-verifier")

    monkeypatch.setattr("business.workflows.cli.verify_job_quote_packet", boom)
    runner = CliRunner()
    with pytest.raises(RuntimeError, match="boom-verifier"):
        runner.invoke(
            main,
            ["verify", "--packet-dir", str(packet)],
            catch_exceptions=False,
        )


def test_run_help_remains_available() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--root" in result.output
    assert "--job" in result.output
    assert "--output-dir" in result.output
