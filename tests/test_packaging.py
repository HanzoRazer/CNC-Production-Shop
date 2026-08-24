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

Every consumer test below runs an INSTALLED interpreter from a working directory
outside the checkout, and asserts the import resolved into ``site-packages`` —
otherwise a stray ``sys.path`` entry would let the source tree answer for the
artifact and the test would pass without testing anything.
"""

from __future__ import annotations

import email
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

FEATURE_PACKAGES = [
    "cam_assist",
    "business",
    "parametric",
    "fretboard",
    "materials",
    "acoustic",
    "musical_spatial_mapping",
]

# Neutral resolver introduced by CNC-VERSION-ALIGNMENT-2. It is not a feature
# package; it exists so no feature package owns the distribution version.
DECLARED_PACKAGES = ["cnc_version", *FEATURE_PACKAGES]


def _bail(reason: str) -> None:
    """Skip locally, FAIL under CI.

    A build-environment problem is not a defect on a workstation, but on CI a
    silent skip recreates precisely the blindness these tests exist to remove:
    the suite would go green having never built the artifact.
    """
    if os.environ.get("CI"):
        pytest.fail(f"{reason}\n(CI: refusing to skip the distribution boundary)")
    pytest.skip(reason)


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


def test_every_expected_package_is_declared(config):
    """A package dropped from this list still imports from the checkout and
    still passes every other test — it just stops shipping."""
    declared = _wheel_target(config).get("packages", [])
    assert sorted(declared) == sorted(DECLARED_PACKAGES), (
        f"declared packages drifted: {sorted(declared)}"
    )


# ------------------------------------------------------------ the real artifact


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build a real wheel from this checkout."""
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
        _bail(f"wheel could not be built in this environment:\n{combined[-500:]}")
    return wheels[0]


@pytest.fixture(scope="module")
def wheel_members(built_wheel) -> list[str]:
    return zipfile.ZipFile(built_wheel).namelist()


def test_the_wheel_builds(built_wheel):
    assert built_wheel.exists()


def test_the_wheel_writes_no_member_twice(wheel_members):
    """The failure mode itself: hatchling refuses, so a duplicate here means the
    build is impossible rather than merely wasteful."""
    duplicates = {n for n in wheel_members if wheel_members.count(n) > 1}
    assert not duplicates, f"duplicate archive members: {sorted(duplicates)}"


def test_the_wheel_carries_the_instrument_profiles(wheel_members):
    """force-include was added to guarantee this. It was never needed, and it
    broke the build — `packages` already carries the data."""
    resources = [n for n in wheel_members if "musical_spatial_mapping/resources/" in n]
    assert len(resources) >= 4, f"resources missing from the wheel: {resources}"
    for expected in (
        "guitar-standard-6.json",
        "bass-fretless-4.json",
        "mandolin-standard.json",
        "instrument-profile-v1.schema.json",
    ):
        assert any(expected in n for n in resources), f"{expected} not packaged"


def test_the_wheel_carries_every_declared_package(wheel_members):
    """Removing the force-include must not have cost any OTHER package its files.

    The fix edited a shared build table; this is the blast-radius check.
    Adding ``cnc_version`` increases the member count by that package's
    ``__init__.py`` only.
    """
    missing = [
        pkg for pkg in DECLARED_PACKAGES if not any(n.startswith(f"{pkg}/") for n in wheel_members)
    ]
    assert not missing, f"declared packages absent from the wheel: {missing}"


def test_the_wheel_carries_the_neutral_resolver(wheel_members):
    assert any(n == "cnc_version/__init__.py" for n in wheel_members), (
        "cnc_version must ship in the wheel so installed packages can resolve __version__"
    )


def test_the_wheel_carries_the_msme_modules(wheel_members):
    """Resources are worthless without the code that reads them."""
    modules = {
        n.split("/")[-1]
        for n in wheel_members
        if n.startswith("musical_spatial_mapping/") and n.endswith(".py") and n.count("/") == 1
    }
    for expected in (
        "__init__.py",
        "mapper.py",
        "serialization.py",
        "cli.py",
    ):
        assert expected in modules, f"musical_spatial_mapping/{expected} not packaged"
    assert "_distribution_version.py" not in modules


# ------------------------------------------------------- the installed consumer


@pytest.fixture(scope="module")
def installed_python(built_wheel, tmp_path_factory) -> Path:
    """Install the wheel into a fresh venv once, and hand back its interpreter.

    Module-scoped: every consumer test below shares this one installation, so
    proving more about the artifact does not cost another venv each time.
    """
    base = tmp_path_factory.mktemp("consumer")
    venv = base / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(built_wheel)],
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        _bail(f"could not install into a fresh venv:\n{install.stderr[-500:]}")
    return python


def _consume(python: Path, body: str) -> str:
    """Run `body` on the installed interpreter, outside the source tree.

    The preamble is the point: it proves the name resolved to the installed
    package rather than to the checkout, so none of these assertions can be
    satisfied by the very source tree they are meant to stand in for.
    """
    preamble = (
        "import musical_spatial_mapping as _m, pathlib as _p\n"
        "_loc = _p.Path(_m.__file__).resolve()\n"
        "assert 'site-packages' in str(_loc), f'not installed: {_loc}'\n"
        f"assert {str(ROOT)!r} not in str(_loc), f'resolved to the checkout: {{_loc}}'\n"
    )
    proc = subprocess.run(
        [str(python), "-c", preamble + body],
        capture_output=True,
        text=True,
        cwd=str(python.parent.parent.parent),  # outside the repository
    )
    assert proc.returncode == 0, f"installed package failed:\n{proc.stderr}"
    return proc.stdout


def test_the_installed_package_maps_a_note(installed_python):
    """The claim that matters: it works when INSTALLED, not just when imported
    from the checkout."""
    out = _consume(
        installed_python,
        "from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent\n"
        "from musical_spatial_mapping.fixtures import all_example_profiles\n"
        "profiles = all_example_profiles()\n"
        "r = MusicalSpatialMapper(profile=profiles[0]).map(\n"
        "    MusicalEvent(event_id='e1', midi_note=64, start_tick=0,"
        " duration_ticks=480))\n"
        "print(len(profiles), r.status.value)\n",
    )
    assert out.split() == ["3", "selected"], out


def test_the_installed_package_reports_the_distribution_version(installed_python):
    """``__version__`` is the installed ``cnc-production-shop`` version.

    Compared to package metadata, not to a source literal, so a second
    independently maintained number cannot quietly satisfy this check.
    """
    out = (
        _consume(
            installed_python,
            "import importlib.metadata as md\n"
            "print(_m.__version__, md.version('cnc-production-shop'), sep='\\n')\n",
        )
        .strip()
        .splitlines()
    )
    reported, meta = out
    assert reported == meta, f"installed __version__ {reported!r} != distribution metadata {meta!r}"


def test_all_installed_feature_packages_report_the_wheel_version(installed_python):
    """Every feature package __version__ equals wheel metadata, from site-packages."""
    names = ", ".join(repr(n) for n in FEATURE_PACKAGES)
    out = _consume(
        installed_python,
        "import importlib, importlib.metadata as md\n"
        "from pathlib import Path\n"
        f"packages = [{names}]\n"
        "meta = md.version('cnc-production-shop')\n"
        "for name in packages:\n"
        "    mod = importlib.import_module(name)\n"
        "    loc = Path(mod.__file__).resolve()\n"
        "    assert 'site-packages' in str(loc), loc\n"
        f"    assert {str(ROOT)!r} not in str(loc), loc\n"
        "    assert mod.__version__ == meta, (name, mod.__version__, meta)\n"
        "    print(name, mod.__version__)\n"
        "print('META', meta)\n",
    )
    lines = out.strip().splitlines()
    assert lines[-1] == f"META {_project_version()}", lines
    reported = [line.split()[1] for line in lines[:-1]]
    assert reported == [_project_version()] * len(FEATURE_PACKAGES)


def _project_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_the_installed_package_reports_msme_api_version(installed_python):
    """MSME contract maturity stays named, and stays 0.2.0, after install."""
    out = _consume(installed_python, "print(_m.MSME_API_VERSION)\n").strip()
    assert out == "0.2.0"


def test_wheel_metadata_reports_project_version_once(built_wheel, config):
    """The wheel carries exactly one distribution Version header."""
    project_version = config["project"]["version"]
    with zipfile.ZipFile(built_wheel) as archive:
        meta_name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        meta = email.message_from_bytes(archive.read(meta_name))
    versions = meta.get_all("Version") or []
    assert versions == [project_version]
    assert meta.get("Name") == "cnc-production-shop"


def test_the_installed_package_reads_its_packaged_schema(installed_python):
    """A data file can be present in the archive and still unreachable through
    the import system, which is the only way a consumer can get at it."""
    out = _consume(
        installed_python,
        "import json, importlib.resources as ir\n"
        "f = ir.files('musical_spatial_mapping') /"
        " 'resources/instruments/schema/instrument-profile-v1.schema.json'\n"
        "print(json.loads(f.read_text(encoding='utf-8'))['title'])\n",
    ).strip()
    assert out == "Instrument Profile v1", out


def test_the_installed_package_serializes_a_result(installed_python):
    """The byte contract has to hold for the artifact, not only in the repo."""
    out = _consume(
        installed_python,
        "import json\n"
        "from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent\n"
        "from musical_spatial_mapping.fixtures import all_example_profiles\n"
        "from musical_spatial_mapping.serialization import mapping_result_to_json\n"
        "r = MusicalSpatialMapper(profile=all_example_profiles()[0]).map(\n"
        "    MusicalEvent(event_id='e1', midi_note=64, start_tick=0,"
        " duration_ticks=480))\n"
        "blob = mapping_result_to_json(r)\n"
        "print(blob.isascii(), bool(json.loads(blob)))\n",
    )
    assert out.split() == ["True", "True"], out


def test_module_execution_survives_the_wheel_install(installed_python):
    """``python -m musical_spatial_mapping.cli`` is a published entry point, and
    module execution depends on packaging details an import test never touches.

    It also re-checks the byte contract across the process boundary: the CLI now
    serializes through the library, so identical bytes are the evidence that the
    two emitters cannot drift apart again in a shipped artifact.
    """
    out = _consume(
        installed_python,
        "import json, subprocess, sys, tempfile\n"
        "from pathlib import Path\n"
        "from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent\n"
        "from musical_spatial_mapping.fixtures import all_example_profiles\n"
        "from musical_spatial_mapping.serialization import (\n"
        "    instrument_profile_to_dict, mapping_result_to_json)\n"
        "p = all_example_profiles()[0]\n"
        "with tempfile.TemporaryDirectory() as tmp:\n"
        "    f = Path(tmp) / 'profile.json'\n"
        "    f.write_text(json.dumps(instrument_profile_to_dict(p)),"
        " encoding='utf-8')\n"
        "    proc = subprocess.run([sys.executable, '-m',"
        " 'musical_spatial_mapping.cli',\n"
        "        '--profile', str(f), '--event',"
        ' \'{"midi_note": 64, "event_id": "e1"}\'],\n'
        "        capture_output=True, text=True, cwd=tmp)\n"
        "assert proc.returncode == 0, proc.stderr\n"
        "lib = mapping_result_to_json(MusicalSpatialMapper(profile=p).map(\n"
        "    MusicalEvent(event_id='e1', midi_note=64, start_tick=0,"
        " duration_ticks=480)), indent=2)\n"
        "print(proc.stdout.isascii(), proc.stdout.strip() == lib.strip())\n",
    )
    assert out.split() == ["True", "True"], f"CLI/library byte contract broke: {out}"
