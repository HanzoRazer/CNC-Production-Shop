#!/usr/bin/env python3
"""Read-only check that a source tree is internally consistent for a release.

Usage:
    python scripts/release/check_release_readiness.py --version 0.1.0
    python scripts/release/check_release_readiness.py --version 0.1.0 --root /path/to/checkout

``--root`` is the sole inspection source. The script does not consult the
caller's installed distribution or imported packages. Package parity means
each feature package exists under ``--root`` and binds ``__version__`` to
``cnc_version.distribution_version()``.

Exit 0 if internally release-ready. Exit 1 if any blocker is found.

Does not create tags, mutate files, or talk to the network.
"""

from __future__ import annotations

import argparse
import email
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    DISTRIBUTION_NAME,
    WITNESS_TAGS,
    ReleasePolicyError,
    changelog_has_release_ready_unreleased,
    changelog_has_version_section,
    package_binds_distribution_version,
    parse_distribution_version,
    read_assigned_string_constant,
    select_wheel_metadata_member,
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


def _read_wheel_metadata(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            member = select_wheel_metadata_member(archive.namelist())
            meta = email.message_from_bytes(archive.read(member))
    except zipfile.BadZipFile as exc:
        raise ReleasePolicyError(f"wheel is not a valid zip: {exc}") from exc
    name = meta.get("Name")
    version = meta.get("Version")
    if not name or not version:
        raise ReleasePolicyError("wheel METADATA is missing Name or Version")
    return name, version


def _check_packages(root: Path) -> bool:
    ok = True
    resolver = root / "cnc_version" / "__init__.py"
    ok &= _say(resolver.is_file(), "cnc_version resolver present under --root")

    missing: list[str] = []
    unbound: list[str] = []
    for name in FEATURE_PACKAGES:
        init = root / name / "__init__.py"
        if not init.is_file():
            missing.append(name)
            continue
        try:
            source = init.read_text(encoding="utf-8")
            if not package_binds_distribution_version(source):
                unbound.append(name)
        except (OSError, ReleasePolicyError) as exc:
            unbound.append(f"{name} ({exc})")
    ok &= _say(not missing, "feature packages present under --root")
    if missing:
        print(f"     missing: {', '.join(missing)}")
    ok &= _say(not unbound, "package __version__ binds to distribution_version() under --root")
    if unbound:
        print(f"     unbound: {', '.join(unbound)}")

    msme_init = root / "musical_spatial_mapping" / "__init__.py"
    try:
        api = read_assigned_string_constant(
            msme_init.read_text(encoding="utf-8"), "MSME_API_VERSION"
        )
        ok &= _say(True, f"MSME_API_VERSION: {api}")
    except (OSError, ReleasePolicyError) as exc:
        ok &= _say(False, f"MSME_API_VERSION unreadable from --root: {exc}")
    return ok


def check(version: str, root: Path, wheel: Path | None) -> int:
    ok = True
    try:
        expected = parse_distribution_version(version)
    except ReleasePolicyError as exc:
        _say(False, str(exc))
        return 1

    try:
        declared = _project_version(root)
        ok &= _say(declared == expected, f"distribution version from --root: {declared}")
        if declared != expected:
            print(f"     expected --version {expected}")
    except (OSError, KeyError, ReleasePolicyError, tomllib.TOMLDecodeError) as exc:
        ok &= _say(False, f"project distribution version: {exc}")

    ok &= _check_packages(root)

    git_dir = root / ".git"
    if not git_dir.exists():
        ok &= _say(False, "git metadata present at --root")
    else:
        status = _git(root, "status", "--porcelain")
        clean = status.returncode == 0 and status.stdout.strip() == ""
        ok &= _say(clean, "working tree clean")
        if not clean and status.stdout.strip():
            print(status.stdout.rstrip())
        listed = _git(root, "tag", "--list")
        if listed.returncode != 0:
            detail = listed.stderr.strip() or f"exit {listed.returncode}"
            ok &= _say(False, f"git tag --list: {detail}")
        else:
            tags = {
                line for line in listed.stdout.splitlines() if line and line not in WITNESS_TAGS
            }
            canonical = tag_for_version(expected)
            ok &= _say(canonical not in tags, f"canonical tag {canonical} does not exist")

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
        if not wheel.is_file():
            ok &= _say(False, f"wheel exists: {wheel}")
        else:
            try:
                meta_name_value, meta_version = _read_wheel_metadata(wheel)
            except (OSError, ReleasePolicyError) as exc:
                ok &= _say(False, f"wheel metadata: {exc}")
            else:
                ok &= _say(
                    meta_name_value == DISTRIBUTION_NAME,
                    f"wheel metadata name: {meta_name_value}",
                )
                ok &= _say(meta_version == expected, f"wheel metadata version: {meta_version}")

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="proposed distribution version")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to inspect (sole source; default: this checkout)",
    )
    parser.add_argument("--wheel", type=Path, default=None, help="optional wheel to inspect")
    args = parser.parse_args()
    return check(args.version, args.root.resolve(), args.wheel)


if __name__ == "__main__":
    raise SystemExit(main())
