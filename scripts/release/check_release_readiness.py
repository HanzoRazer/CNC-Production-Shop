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
import json
import subprocess
import sys
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    DISTRIBUTION_NAME,
    FEATURE_PACKAGES,
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


@dataclass(frozen=True)
class CheckItem:
    ok: bool
    message: str
    extra: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    version: str
    ready: bool
    checks: tuple[CheckItem, ...]
    blockers: tuple[str, ...]


def _print_report(report: ReadinessReport) -> None:
    for item in report.checks:
        print(f"{'PASS' if item.ok else 'FAIL'} {item.message}")
        if item.extra:
            print(item.extra.rstrip())


def _report_to_json(report: ReadinessReport) -> dict[str, object]:
    payload = asdict(report)
    payload["checks"] = [asdict(item) for item in report.checks]
    payload["blockers"] = list(report.blockers)
    return payload


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


def inspect_release_readiness(version: str, root: Path, wheel: Path | None) -> ReadinessReport:
    """Evaluate release readiness without printing. Does not mutate ``root``."""
    checks: list[CheckItem] = []

    def record(ok: bool, message: str, extra: str = "") -> None:
        checks.append(CheckItem(ok=ok, message=message, extra=extra))

    try:
        expected = parse_distribution_version(version)
    except ReleasePolicyError as exc:
        record(False, str(exc))
        return ReadinessReport(
            version=version,
            ready=False,
            checks=tuple(checks),
            blockers=tuple(item.message for item in checks if not item.ok),
        )

    try:
        declared = _project_version(root)
        extra = f"     expected --version {expected}" if declared != expected else ""
        record(declared == expected, f"distribution version from --root: {declared}", extra)
    except (OSError, KeyError, ReleasePolicyError, tomllib.TOMLDecodeError) as exc:
        record(False, f"project distribution version: {exc}")

    resolver = root / "cnc_version" / "__init__.py"
    record(resolver.is_file(), "cnc_version resolver present under --root")

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
    record(
        not missing,
        "feature packages present under --root",
        f"     missing: {', '.join(missing)}" if missing else "",
    )
    record(
        not unbound,
        "package __version__ binds to distribution_version() under --root",
        f"     unbound: {', '.join(unbound)}" if unbound else "",
    )

    msme_init = root / "musical_spatial_mapping" / "__init__.py"
    try:
        api = read_assigned_string_constant(
            msme_init.read_text(encoding="utf-8"), "MSME_API_VERSION"
        )
        record(True, f"MSME_API_VERSION: {api}")
    except (OSError, ReleasePolicyError) as exc:
        record(False, f"MSME_API_VERSION unreadable from --root: {exc}")

    git_dir = root / ".git"
    if not git_dir.exists():
        record(False, "git metadata present at --root")
    else:
        status = _git(root, "status", "--porcelain")
        clean = status.returncode == 0 and status.stdout.strip() == ""
        dirty_extra = status.stdout.rstrip() if not clean and status.stdout.strip() else ""
        record(clean, "working tree clean", dirty_extra)
        listed = _git(root, "tag", "--list")
        if listed.returncode != 0:
            detail = listed.stderr.strip() or f"exit {listed.returncode}"
            record(False, f"git tag --list: {detail}")
        else:
            tags = {
                line for line in listed.stdout.splitlines() if line and line not in WITNESS_TAGS
            }
            canonical = tag_for_version(expected)
            record(canonical not in tags, f"canonical tag {canonical} does not exist")

    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        record(False, "CHANGELOG.md exists")
    else:
        text = changelog_path.read_text(encoding="utf-8")
        ready_notes = changelog_has_version_section(text, expected) or (
            changelog_has_release_ready_unreleased(text)
        )
        record(
            ready_notes,
            f"changelog has a {expected} section or release-ready Unreleased material",
        )

    if wheel is not None:
        try:
            wheel_version = version_from_wheel_filename(wheel.name)
            record(wheel_version == expected, f"wheel filename version: {wheel_version}")
        except ReleasePolicyError as exc:
            record(False, str(exc))
        if not wheel.is_file():
            record(False, f"wheel exists: {wheel}")
        else:
            try:
                meta_name_value, meta_version = _read_wheel_metadata(wheel)
            except (OSError, ReleasePolicyError) as exc:
                record(False, f"wheel metadata: {exc}")
            else:
                record(
                    meta_name_value == DISTRIBUTION_NAME,
                    f"wheel metadata name: {meta_name_value}",
                )
                record(meta_version == expected, f"wheel metadata version: {meta_version}")

    blockers = tuple(item.message for item in checks if not item.ok)
    return ReadinessReport(
        version=expected,
        ready=not blockers,
        checks=tuple(checks),
        blockers=blockers,
    )


def check(version: str, root: Path, wheel: Path | None) -> int:
    report = inspect_release_readiness(version, root, wheel)
    _print_report(report)
    return 0 if report.ready else 1


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
    parser.add_argument(
        "--json",
        action="store_true",
        help="write a machine-readable report to stdout instead of PASS/FAIL lines",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write JSON report to this path (human output kept unless --json)",
    )
    args = parser.parse_args()
    report = inspect_release_readiness(args.version, args.root.resolve(), args.wheel)
    payload = _report_to_json(report)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    if args.json:
        sys.stdout.write(encoded)
    else:
        _print_report(report)
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
