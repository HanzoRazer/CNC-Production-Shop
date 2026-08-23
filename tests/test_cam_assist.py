"""Tests for CAM Assist core functionality."""

import cam_assist
from cnc_version import distribution_version


def test_version():
    assert cam_assist.__version__ == distribution_version()
