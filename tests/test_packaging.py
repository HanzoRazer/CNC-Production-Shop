"""The distributable artifact must actually build, and carry its data files.

Every other test in this repository runs against the source tree, and CI installs
with ``pip install -e``. PEP 660 editable installs call hatchling's
``build_editable``, which is a different code path from ``build_wheel`` — so the
whole suite can be green while ``pip wheel .`` is impossible.

That is not hypothetical. A ``force-include`` entry pointing inside an
already-declared package made hatchling write the same archive member twice and
fail the build, and nothing caught it: source imports worked, tests passed, CI
passed. These tests exist because "it imports from the repo" and "it installs"
are different claims.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _wheel_target(config: dict) -> dict:
    return config["tool"]["hatch"]["build"]["targets"]["wheel"]


# ------------------------------------------------------- fast structural guards


def test_no_force_include_duplicates_a_declared_package(config):
    """The exact defect: a forced path that lives inside a declared package.

    Fast and offline, so it fails in the first second of a run rather than only
    when someone tries to build a release.
    """
    target = _wheel_target(config)
    packages = target.get("packages", [])
    forced = target.get("force-include", {})
    offenders = [
        (source, pkg)
        for source in forced
        for pkg in packages
        if source == pkg or source.startswith(f"{pkg}/")
    ]
    assert not offenders, (
        f"force-include entries duplicate files already covered by `packages`: "
        f"{offenders}. hatchling writes the archive member twice and the wheel "
        f"build fails, while editable installs and the test suite stay green."
    )


def test_musical_spatial_mapping_is_a_declared_package(config):
    """Resources ride along with the package; if it is not declared, they vanish."""
    assert "musical_spatial_mapping" in _wheel_target(config).get("packages", [])


# ------------------------------------------------------------ the real artifact


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build a real wheel, or skip when the environment cannot.

    Skips rather than fails on a build-environment problem (no network for the
    isolated build backend, say). A wheel that builds and is missing its data is
    a defect; a machine that cannot fetch hatchling is not.
    """
    out = tmp_path_factory.mktemp("wheel")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(out)],
        capture_output=True,
        text=True,
    )
    wheels = list(out.glob("*.whl"))
    if not wheels:
        combined = proc.stdout + proc.stderr
        if "same path" in combined or "force-include" in combined:
            pytest.fail(f"wheel build failed on a packaging defect:\n{combined[-1500:]}")
        pytest.skip(f"wheel could not be built in this environment:\n{combined[-500:]}")
    return wheels[0]


def test_the_wheel_builds(built_wheel):
    assert built_wheel.exists()


def test_the_wheel_carries_the_instrument_profiles(built_wheel):
    """force-include was added to guarantee this. It was never needed, and it
    broke the build — `packages` already carries the data."""
    names = zipfile.ZipFile(built_wheel).namelist()
    resources = [n for n in names if "musical_spatial_mapping/resources/" in n]
    assert len(resources) >= 4, f"resources missing from the wheel: {resources}"
    for expected in (
        "guitar-standard-6.json",
        "bass-fretless-4.json",
        "mandolin-standard.json",
        "instrument-profile-v1.schema.json",
    ):
        assert any(expected in n for n in resources), f"{expected} not packaged"


def test_the_installed_package_maps_a_note(built_wheel, tmp_path):
    """The claim that matters: it works when INSTALLED, not just when imported
    from the checkout. Runs outside the source tree so a stray sys.path entry
    cannot rescue it."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(built_wheel)],
        capture_output=True, text=True,
    )
    if install.returncode != 0:
        pytest.skip(f"could not install into a fresh venv:\n{install.stderr[-500:]}")

    script = (
        "from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent\n"
        "from musical_spatial_mapping.fixtures import all_example_profiles\n"
        "profiles = all_example_profiles()\n"
        "r = MusicalSpatialMapper(profile=profiles[0]).map(\n"
        "    MusicalEvent(event_id='e1', midi_note=64, start_tick=0, duration_ticks=480))\n"
        "print(len(profiles), r.status.value)\n"
    )
    proc = subprocess.run(
        [str(python), "-c", script], capture_output=True, text=True, cwd=str(tmp_path)
    )
    assert proc.returncode == 0, f"installed package failed to map:\n{proc.stderr}"
    assert proc.stdout.split() == ["3", "selected"], proc.stdout
