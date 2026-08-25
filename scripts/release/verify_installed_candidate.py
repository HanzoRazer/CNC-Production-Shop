#!/usr/bin/env python3
"""Install a wheel into an isolated venv and verify it from outside the checkout.

Usage:
    python scripts/release/verify_installed_candidate.py \\
        --wheel dist-release-candidate/cnc_production_shop-0.1.1-py3-none-any.whl \\
        --version 0.1.1

Creates a fresh virtualenv. Does not mutate the source tree, create tags, or
publish. Reuses the same site-packages / MSME / CLI claims as tests/test_packaging.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    DISTRIBUTION_NAME,
    FEATURE_PACKAGES,
    ReleasePolicyError,
)


@dataclass
class InstalledVerification:
    ok: bool
    distribution_version: str = ""
    msme_api_version: str = ""
    package_versions: dict[str, str] = field(default_factory=dict)
    site_packages: bool = False
    resources_ok: bool = False
    msme_cli_ok: bool = False
    cam_assist_ok: bool = False
    blockers: list[str] = field(default_factory=list)


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _create_venv(venv: Path) -> Path:
    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr)[-800:] or f"exit {proc.returncode}"
        raise ReleasePolicyError(f"could not create venv: {detail}")
    python = _venv_python(venv)
    if not python.is_file():
        raise ReleasePolicyError(f"venv python missing: {python}")
    return python


def _install_wheel(python: Path, wheel: Path) -> None:
    proc = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(wheel.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ReleasePolicyError(f"could not install wheel into venv: {proc.stderr[-800:]}")


def _consume(python: Path, repo_root: Path, body: str, *, cwd: Path) -> tuple[int, str, str]:
    source_msme = str(repo_root.resolve() / "musical_spatial_mapping")
    preamble = (
        "import musical_spatial_mapping as _m, pathlib as _p\n"
        "_loc = _p.Path(_m.__file__).resolve()\n"
        "assert 'site-packages' in str(_loc), f'not installed: {_loc}'\n"
        f"assert not str(_loc).startswith({source_msme!r} + {os.sep!r}), "
        f"f'resolved to the checkout: {{_loc}}'\n"
    )
    proc = subprocess.run(
        [str(python), "-c", preamble + body],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        check=False,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
    )
    return proc.returncode, proc.stdout, proc.stderr


def verify_installed_candidate(
    wheel: Path,
    version: str,
    *,
    repo_root: Path,
    venv_dir: Path | None = None,
) -> InstalledVerification:
    """Install ``wheel`` into an isolated venv and verify the installed tree."""
    result = InstalledVerification(ok=False)
    if not wheel.is_file():
        result.blockers.append(f"wheel does not exist: {wheel}")
        return result

    if venv_dir is None:
        venv_dir = Path(tempfile.mkdtemp(prefix="cnc-rc-venv-"))
    try:
        python = _create_venv(venv_dir)
        _install_wheel(python, wheel)
    except ReleasePolicyError as exc:
        result.blockers.append(str(exc))
        return result

    workdir = venv_dir.parent
    names = ", ".join(repr(n) for n in FEATURE_PACKAGES)
    source_dirs = {name: str(repo_root.resolve() / name) for name in FEATURE_PACKAGES}
    code, out, err = _consume(
        python,
        repo_root,
        "import importlib, importlib.metadata as md, os\n"
        "from pathlib import Path\n"
        f"packages = [{names}]\n"
        f"source_dirs = {source_dirs!r}\n"
        f"meta = md.version({DISTRIBUTION_NAME!r})\n"
        "print('META', meta)\n"
        "print('MSME_API', _m.MSME_API_VERSION)\n"
        "print('SITE', int('site-packages' in str(_loc)))\n"
        "for name in packages:\n"
        "    mod = importlib.import_module(name)\n"
        "    loc = Path(mod.__file__).resolve()\n"
        "    assert 'site-packages' in str(loc), loc\n"
        "    assert not str(loc).startswith(source_dirs[name] + os.sep), loc\n"
        "    print('PKG', name, mod.__version__)\n"
        "    assert mod.__version__ == meta, (name, mod.__version__, meta)\n",
        cwd=workdir,
    )
    if code != 0:
        result.blockers.append(f"installed import/parity check failed: {err[-800:] or out[-800:]}")
        return result

    package_versions: dict[str, str] = {}
    for line in out.splitlines():
        if line.startswith("META "):
            result.distribution_version = line.split(" ", 1)[1]
        elif line.startswith("MSME_API "):
            result.msme_api_version = line.split(" ", 1)[1]
        elif line.startswith("SITE "):
            result.site_packages = line.split(" ", 1)[1] == "1"
        elif line.startswith("PKG "):
            _, name, reported = line.split(" ", 2)
            package_versions[name] = reported
    result.package_versions = package_versions
    if result.distribution_version != version:
        result.blockers.append(
            f"installed distribution version {result.distribution_version!r} != {version!r}"
        )
    mismatched = [name for name, reported in package_versions.items() if reported != version]
    if mismatched:
        result.blockers.append(f"package __version__ mismatch: {mismatched}")
    if set(package_versions) != set(FEATURE_PACKAGES):
        result.blockers.append("not every feature package reported a version from site-packages")
    if not result.site_packages:
        result.blockers.append("imports did not resolve into site-packages")
    if not result.msme_api_version:
        result.blockers.append("MSME_API_VERSION missing after install")

    code, out, err = _consume(
        python,
        repo_root,
        "import json, importlib.resources as ir\n"
        "f = ir.files('musical_spatial_mapping') /"
        " 'resources/instruments/schema/instrument-profile-v1.schema.json'\n"
        "print(json.loads(f.read_text(encoding='utf-8'))['title'])\n",
        cwd=workdir,
    )
    result.resources_ok = code == 0 and out.strip() == "Instrument Profile v1"
    if not result.resources_ok:
        result.blockers.append(f"packaged MSME schema unreadable: {err[-400:] or out[-400:]}")

    code, out, err = _consume(
        python,
        repo_root,
        "import json, subprocess, sys, tempfile\n"
        "from pathlib import Path\n"
        "from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent\n"
        "from musical_spatial_mapping.fixtures import all_example_profiles\n"
        "from musical_spatial_mapping.serialization import (\n"
        "    instrument_profile_to_dict, mapping_result_to_json)\n"
        "p = all_example_profiles()[0]\n"
        "with tempfile.TemporaryDirectory() as tmp:\n"
        "    f = Path(tmp) / 'profile.json'\n"
        "    f.write_text(json.dumps(instrument_profile_to_dict(p)), encoding='utf-8')\n"
        "    proc = subprocess.run([sys.executable, '-m',\n"
        "        'musical_spatial_mapping.cli',\n"
        "        '--profile', str(f), '--event',\n"
        '        \'{"midi_note": 64, "event_id": "e1"}\'],\n'
        "        capture_output=True, text=True, cwd=tmp)\n"
        "    assert proc.returncode == 0, proc.stderr\n"
        "    lib = mapping_result_to_json(MusicalSpatialMapper(profile=p).map(\n"
        "        MusicalEvent(event_id='e1', midi_note=64, start_tick=0,"
        " duration_ticks=480)), indent=2)\n"
        "    print(proc.stdout.isascii(), proc.stdout.strip() == lib.strip())\n",
        cwd=workdir,
    )
    result.msme_cli_ok = code == 0 and out.split() == ["True", "True"]
    if not result.msme_cli_ok:
        result.blockers.append(f"MSME CLI smoke failed: {err[-400:] or out[-400:]}")

    cam = python.parent / ("cam-assist.exe" if sys.platform == "win32" else "cam-assist")
    cam_proc = subprocess.run(
        [str(cam), "status"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(workdir),
    )
    expected_status = f"CAM Assist v{version} — Ready"
    result.cam_assist_ok = cam_proc.returncode == 0 and cam_proc.stdout.strip() == expected_status
    if not result.cam_assist_ok:
        result.blockers.append(
            f"cam-assist status failed: {cam_proc.stderr[-400:] or cam_proc.stdout[-400:]}"
        )

    result.ok = not result.blockers
    return result


def installed_to_json(result: InstalledVerification) -> dict[str, object]:
    return {
        "ok": result.ok,
        "distribution_version": result.distribution_version,
        "msme_api_version": result.msme_api_version,
        "package_versions": dict(result.package_versions),
        "site_packages": result.site_packages,
        "resources_ok": result.resources_ok,
        "msme_cli_ok": result.msme_cli_ok,
        "cam_assist_ok": result.cam_assist_ok,
        "blockers": list(result.blockers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--venv-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = verify_installed_candidate(
        args.wheel,
        args.version,
        repo_root=args.root.resolve(),
        venv_dir=args.venv_dir,
    )
    encoded = json.dumps(installed_to_json(result), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
