#!/usr/bin/env python3
"""Read-only check that a source tree is internally consistent for a release.

Usage:
    python scripts/release/check_release_readiness.py --version 0.1.0

Exit 0 if internally release-ready. Exit 1 if any blocker is found.

Does not create tags, mutate files, or talk to the network.
"""

from __future__ import annotations

import argparse
import email
import importlib
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cnc_version import DISTRIBUTION_NAME, distribution_version  # noqa: E402
from scripts.release.model import (  # noqa: E402
    WITNESS_TAGS,
    ReleasePolicyError,
    changelog_has_release_ready_unreleased,
    changelog_has_version_section,
    parse_distribution_version,
    tag_for_version,
    version_from_wheel_filename,
)

FEATURE_PACKAGES = (
    "cam_assist",
    "business",
    "parametric",
    "fretboard",
    "materials",
    "acoustic",
    "musical_spatial_mapping",
)


def _say(ok: bool, message: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {message}")
    return ok


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise ReleasePolicyError("pyproject [project].version is not a string")
    return parse_distribution_version(version)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def check(version: str, root: Path, wheel: Path | None) -> int:
    ok = True
    try:
        expected = parse_distribution_version(version)
    except ReleasePolicyError as exc:
        _say(False, str(exc))
        return 1

    try:
        declared = _project_version(root)
        ok &= _say(declared == expected, f"distribution version: {declared}")
        if declared != expected:
            print(f"     expected --version {expected}")
    except (OSError, KeyError, ReleasePolicyError, tomllib.TOMLDecodeError) as exc:
        ok &= _say(False, f"project distribution version: {exc}")
        declared = expected

    runtime = distribution_version()
    ok &= _say(runtime == expected, f"runtime distribution version: {runtime}")

    drifted: list[str] = []
    for name in FEATURE_PACKAGES:
        module = importlib.import_module(name)
        reported = getattr(module, "__version__", None)
        if reported != expected:
            drifted.append(f"{name}={reported!r}")
    ok &= _say(not drifted, "package version parity")
    if drifted:
        print(f"     {', '.join(drifted)}")

    try:
        msme = importlib.import_module("musical_spatial_mapping")
        api = getattr(msme, "MSME_API_VERSION")
        ok &= _say(isinstance(api, str) and bool(api), f"MSME_API_VERSION: {api}")
    except Exception as exc:  # noqa: BLE001 — readiness must fail closed
        ok &= _say(False, f"MSME_API_VERSION unreadable: {exc}")

    git_dir = root / ".git"
    if git_dir.exists():
        status = _git(root, "status", "--porcelain")
        clean = status.returncode == 0 and status.stdout.strip() == ""
        ok &= _say(clean, "working tree clean")
        if not clean and status.stdout.strip():
            print(status.stdout.rstrip())
        listed = _git(root, "tag", "--list")
        tags = {line for line in listed.stdout.splitlines() if line and line not in WITNESS_TAGS}
        canonical = tag_for_version(expected)
        ok &= _say(canonical not in tags, f"canonical tag {canonical} does not exist")
    else:
        ok &= _say(True, "working tree clean (no git metadata at --root)")
        ok &= _say(True, f"canonical tag {tag_for_version(expected)} does not exist")

    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        ok &= _say(False, "CHANGELOG.md exists")
    else:
        text = changelog_path.read_text(encoding="utf-8")
        ready = changelog_has_version_section(text, expected) or (
            changelog_has_release_ready_unreleased(text)
        )
        ok &= _say(
            ready,
            f"changelog has a {expected} section or release-ready Unreleased material",
        )

    if wheel is not None:
        try:
            wheel_version = version_from_wheel_filename(wheel.name)
            ok &= _say(
                wheel_version == expected,
                f"wheel filename version: {wheel_version}",
            )
        except ReleasePolicyError as exc:
            ok &= _say(False, str(exc))
        if wheel.is_file():
            with zipfile.ZipFile(wheel) as archive:
                meta_name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
                meta = email.message_from_bytes(archive.read(meta_name))
            meta_name_value = meta.get("Name")
            meta_version = meta.get("Version")
            ok &= _say(
                meta_name_value == DISTRIBUTION_NAME,
                f"wheel metadata name: {meta_name_value}",
            )
            ok &= _say(meta_version == expected, f"wheel metadata version: {meta_version}")
        else:
            ok &= _say(False, f"wheel exists: {wheel}")

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="proposed distribution version")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to inspect (default: this checkout)",
    )
    parser.add_argument("--wheel", type=Path, default=None, help="optional wheel to inspect")
    args = parser.parse_args()
    return check(args.version, args.root.resolve(), args.wheel)


if __name__ == "__main__":
    raise SystemExit(main())
