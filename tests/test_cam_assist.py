"""Tests for CAM Assist core functionality."""

import cam_assist
from cnc_version import distribution_version


def test_version() -> None:
    assert cam_assist.__version__ == distribution_version()


def test_status_reports_distribution_version() -> None:
    from click.testing import CliRunner

    from cam_assist.cli import main

    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert cam_assist.__version__ in result.output
    assert "Ready" in result.output
