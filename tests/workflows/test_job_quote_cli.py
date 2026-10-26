"""CLI exit codes, working directory handling, and partial-output refusals."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from business.workflows.cli import main
from tests.workflows.conftest import JOB_REL, OUTPUT_REL


def test_module_command_from_another_working_directory(workspace: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "business.workflows.cli",
            "run",
            "--root",
            str(workspace),
            "--job",
            JOB_REL,
            "--output-dir",
            OUTPUT_REL,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "job_id: JOB-CNC-QUOTE-DEMO-001" in result.stdout
    assert "status: draft" in result.stdout
    assert "direct_manufacturing_cost: 924.09" in result.stdout
    assert "quote_price: 1320.13" in result.stdout
    assert (workspace / OUTPUT_REL / "customer" / "proposal.md").is_file()
    assert (workspace / OUTPUT_REL / "manifest.json").is_file()


def test_cli_runner_ignores_the_current_directory(workspace: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main,
            [
                "run",
                "--root",
                str(workspace),
                "--job",
                JOB_REL,
                "--output-dir",
                OUTPUT_REL,
            ],
        )
    assert result.exit_code == 0, result.output
    assert (workspace / OUTPUT_REL / "manifest.json").is_file()


def test_invalid_input_exits_2_without_a_traceback_or_packet(workspace: Path) -> None:
    job = (workspace / JOB_REL).read_text(encoding="utf-8")
    replaced = job.replace('"quantity": 1', '"quantity": 2', 1)
    (workspace / JOB_REL).write_text(replaced, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--root", str(workspace), "--job", JOB_REL, "--output-dir", OUTPUT_REL],
    )
    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "error:" in result.stderr
    assert not (workspace / OUTPUT_REL).exists()


def test_existing_output_exits_2_and_keeps_bytes(workspace: Path) -> None:
    destination = workspace / OUTPUT_REL
    destination.mkdir(parents=True)
    marker = destination / "keep.txt"
    marker.write_bytes(b"same-bytes")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--root", str(workspace), "--job", JOB_REL, "--output-dir", OUTPUT_REL],
    )
    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert marker.read_bytes() == b"same-bytes"


def test_missing_arguments_are_an_invocation_error() -> None:
    result = CliRunner().invoke(main, ["run"])
    assert result.exit_code == 2


def test_unexpected_failure_is_not_relabelled_as_a_refusal(
    workspace: Path, monkeypatch
) -> None:
    def boom(**_kwargs):
        raise RuntimeError("programming failure")

    monkeypatch.setattr("business.workflows.cli.run_job_quote", boom)
    result = CliRunner().invoke(
        main,
        ["run", "--root", str(workspace), "--job", JOB_REL, "--output-dir", OUTPUT_REL],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert not (workspace / OUTPUT_REL).exists()


def test_publish_io_failure_exits_1(workspace: Path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("simulated publish failure")

    monkeypatch.setattr("business.workflows.reporting.os.rename", boom)
    result = CliRunner().invoke(
        main,
        ["run", "--root", str(workspace), "--job", JOB_REL, "--output-dir", OUTPUT_REL],
    )
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.output
    assert not (workspace / OUTPUT_REL).exists()
