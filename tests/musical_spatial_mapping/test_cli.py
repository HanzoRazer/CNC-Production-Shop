"""CLI tests.

Dev Order: MSME-002 Phase H

Invoked as a real subprocess rather than by calling ``main()`` directly, because
the properties under test — exit codes, what lands on stdout versus stderr, and
whether stdout is parseable — only exist at the process boundary.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from musical_spatial_mapping import fixtures
from musical_spatial_mapping.serialization import (
    instrument_profile_to_dict,
    mapping_result_from_dict,
)

MODULE = "musical_spatial_mapping.cli"


@pytest.fixture(scope="module")
def profiles(tmp_path_factory):
    """The shipped example profiles written out as files for the CLI to read."""
    directory = tmp_path_factory.mktemp("profiles")
    paths = {}
    for name, profile in (
        ("guitar", fixtures.guitar_standard_6()),
        ("bass", fixtures.bass_fretless_4()),
        ("mandolin", fixtures.mandolin_standard()),
    ):
        path = directory / f"{name}.json"
        path.write_text(
            json.dumps(instrument_profile_to_dict(profile), indent=2), encoding="utf-8"
        )
        paths[name] = str(path)
    return paths


def run(*args, executable=None):
    return subprocess.run(
        [executable or sys.executable, "-m", MODULE, *args],
        capture_output=True, text=True,
    )


def ok(profiles, instrument="guitar", event='{"midi_note": 64}', *extra):
    proc = run("--profile", profiles[instrument], "--event", event, *extra)
    assert proc.returncode == 0, proc.stderr
    return proc


# ------------------------------------------------------------------ happy paths


def test_a_basic_guitar_mapping_prints_json(profiles):
    proc = ok(profiles)
    data = json.loads(proc.stdout)
    assert data["status"] == "selected"
    assert data["instrument_id"] == "guitar.standard.6"
    assert data["selected"] is not None


def test_stderr_is_empty_on_success(profiles):
    assert ok(profiles).stderr == ""


def test_stdout_is_json_and_nothing_else(profiles):
    """A banner above the JSON would make the command unpipeable."""
    stdout = ok(profiles).stdout
    assert stdout.lstrip().startswith("{")
    json.loads(stdout)  # would raise if any prose were present


def test_a_capo_mapping_keeps_both_coordinates(profiles):
    proc = ok(profiles, "guitar", '{"midi_note": 67}', "--constraints", '{"capo_fret": 2}')
    position = json.loads(proc.stdout)["selected"]["position"]
    assert position["physical"]["fret_number"] == 3
    assert position["playing"]["fret_relative_to_capo"] == 1


def test_a_fretless_mapping_reports_a_null_fret(profiles):
    proc = ok(profiles, "bass", '{"midi_note": 50}')
    position = json.loads(proc.stdout)["selected"]["position"]
    assert position["physical"]["fret_number"] is None
    assert position["physical"]["normalized_position"] > 0


def test_a_mandolin_mapping_stays_at_course_level(profiles):
    proc = ok(profiles, "mandolin", '{"midi_note": 74}')
    data = json.loads(proc.stdout)
    courses = [c["position"]["course_id"] for c in data["candidates"]]
    assert all(c is not None for c in courses)
    assert len(courses) == len(set(courses))


def test_an_ambiguous_result_still_exits_zero(profiles):
    zeroed = json.dumps({
        "movement_weight": 0.0, "string_change_weight": 0.0, "position_weight": 0.0,
        "preferred_region_weight": 0.0, "open_string_weight": 0.0,
        "lower_position_bias": 0.0,
    })
    proc = ok(profiles, "guitar", '{"midi_note": 64}', "--preferences", zeroed)
    assert json.loads(proc.stdout)["status"] == "ambiguous"


def test_a_previous_position_is_accepted(profiles):
    first = json.loads(ok(profiles).stdout)
    previous = json.dumps(first["candidates"][-1]["position"])
    proc = ok(profiles, "guitar", '{"midi_note": 64}',
              "--previous-position", previous,
              "--preferences", '{"movement_weight": 25.0}')
    assert json.loads(proc.stdout)["status"] in ("selected", "ambiguous")


def test_indent_zero_emits_one_line(profiles):
    proc = ok(profiles, "guitar", '{"midi_note": 64}', "--indent", "0")
    assert len(proc.stdout.strip().splitlines()) == 1


# ------------------------------------------------------------------- unplayable


def test_an_unplayable_pitch_exits_zero(profiles):
    """A valid outcome carrying evidence, not a crashed command."""
    proc = ok(profiles, "guitar", '{"midi_note": 30}')
    data = json.loads(proc.stdout)
    assert data["status"] == "unplayable"
    assert data["selected"] is None
    assert data["diagnostics"]
    assert proc.stderr == ""


# ----------------------------------------------------------------- input errors


def test_an_invalid_event_exits_nonzero(profiles):
    proc = run("--profile", profiles["guitar"], "--event", '{"midi_note": 999}')
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.startswith("error:")


def test_an_event_without_a_pitch_exits_nonzero(profiles):
    proc = run("--profile", profiles["guitar"], "--event", "{}")
    assert proc.returncode != 0
    assert "midi_note" in proc.stderr


def test_a_missing_event_argument_exits_nonzero(profiles):
    proc = run("--profile", profiles["guitar"])
    assert proc.returncode != 0
    assert proc.stdout == ""


def test_malformed_json_exits_nonzero(profiles):
    proc = run("--profile", profiles["guitar"], "--event", "{not json")
    assert proc.returncode != 0
    assert "invalid JSON" in proc.stderr


def test_a_missing_profile_path_exits_nonzero(tmp_path):
    proc = run("--profile", str(tmp_path / "absent.json"), "--event", '{"midi_note": 64}')
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert proc.stderr.startswith("error:")


def test_an_invalid_profile_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "1.0"}', encoding="utf-8")
    proc = run("--profile", str(bad), "--event", '{"midi_note": 64}')
    assert proc.returncode != 0
    assert proc.stderr.startswith("error:")


def test_an_unknown_open_string_policy_exits_nonzero(profiles):
    proc = run("--profile", profiles["guitar"], "--event", '{"midi_note": 64}',
               "--constraints", '{"open_string_policy": "sometimes"}')
    assert proc.returncode != 0
    assert "open_string_policy" in proc.stderr


def test_inline_and_file_together_is_refused(profiles, tmp_path):
    path = tmp_path / "event.json"
    path.write_text('{"midi_note": 64}', encoding="utf-8")
    proc = run("--profile", profiles["guitar"], "--event", '{"midi_note": 64}',
               "--event-file", str(path))
    assert proc.returncode != 0
    assert "not both" in proc.stderr


def test_no_traceback_reaches_the_user(profiles):
    proc = run("--profile", profiles["guitar"], "--event", '{"midi_note": 999}')
    assert "Traceback" not in proc.stderr


# ------------------------------------------------------------ contract & parity


def test_cli_output_round_trips_through_the_phase_g_parser(profiles):
    for instrument, midi in (("guitar", 64), ("bass", 50), ("mandolin", 74), ("guitar", 30)):
        data = json.loads(ok(profiles, instrument, json.dumps({"midi_note": midi})).stdout)
        restored = mapping_result_from_dict(data)
        assert restored.instrument_id == data["instrument_id"]


def test_output_is_ascii_only(profiles):
    assert ok(profiles).stdout.isascii()


def test_output_carries_no_paths_or_timestamps(profiles):
    lowered = ok(profiles).stdout.lower()
    for banned in ("c:\\", "/home/", "/users/", "timestamp", "appdata", "tmp"):
        assert banned not in lowered


def test_repeated_invocations_are_byte_identical(profiles):
    runs = [ok(profiles).stdout for _ in range(3)]
    assert all(r == runs[0] for r in runs)


@pytest.mark.skipif(shutil.which("py") is None, reason="Windows py launcher not available")
def test_python_311_and_current_produce_identical_output(profiles):
    """The cross-version guarantee that math.fsum bought, checked end to end."""
    probe = subprocess.run(["py", "-3.11", "-c", "import musical_spatial_mapping"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("Python 3.11 with the package importable is not available")
    current = ok(profiles).stdout
    other = subprocess.run(
        ["py", "-3.11", "-m", MODULE, "--profile", profiles["guitar"],
         "--event", '{"midi_note": 64}'],
        capture_output=True, text=True,
    )
    assert other.returncode == 0, other.stderr
    assert json.loads(other.stdout) == json.loads(current)
