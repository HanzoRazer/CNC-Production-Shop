#!/usr/bin/env python3
"""Inspect a built wheel without installing it.

Usage:
    python scripts/release/verify_release_artifact.py --version 0.1.1 --wheel path.whl

Writes deterministic JSON (no timestamps). Does not mutate source, create
tags, or publish.
"""

from __future__ import annotations

import argparse
import email
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    DECLARED_PACKAGES,
    DISTRIBUTION_NAME,
    REQUIRED_MSME_RESOURCE_SUFFIXES,
    ReleasePolicyError,
    format_artifact_hash,
    select_wheel_metadata_member,
    sha256_hex,
    version_from_wheel_filename,
    wheel_filename_for_version,
)


@dataclass
class ArtifactVerification:
    distribution: str
    version: str
    wheel: str
    sha256: str
    duplicate_members: list[str] = field(default_factory=list)
    packages_present: bool = False
    resources_present: bool = False
    metadata_name: str = ""
    metadata_version: str = ""
    ok: bool = False
    blockers: list[str] = field(default_factory=list)


def _duplicate_members(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def _packages_missing(names: list[str]) -> list[str]:
    return [pkg for pkg in DECLARED_PACKAGES if not any(n.startswith(f"{pkg}/") for n in names)]


def _resources_missing(names: list[str]) -> list[str]:
    resources = [n for n in names if "musical_spatial_mapping/resources/" in n]
    missing: list[str] = []
    for expected in REQUIRED_MSME_RESOURCE_SUFFIXES:
        if not any(expected in n for n in resources):
            missing.append(expected)
    return missing


def verify_release_artifact(wheel: Path, version: str) -> ArtifactVerification:
    """Return a deterministic verification record for ``wheel``."""
    blockers: list[str] = []
    filename = wheel.name
    expected_name = wheel_filename_for_version(version)
    result = ArtifactVerification(
        distribution=DISTRIBUTION_NAME,
        version=version,
        wheel=filename,
        sha256="",
    )
    try:
        parsed = version_from_wheel_filename(filename)
        if parsed != version:
            blockers.append(
                f"wheel filename version {parsed} does not match requested version {version}"
            )
    except ReleasePolicyError as exc:
        blockers.append(str(exc))
    if filename != expected_name:
        blockers.append(f"wheel filename {filename!r} is not {expected_name!r}")
    if not wheel.is_file():
        blockers.append(f"wheel does not exist: {wheel}")
        result.blockers = blockers
        result.ok = False
        return result

    digest = sha256_hex(wheel.read_bytes())
    result.sha256 = digest

    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            duplicates = _duplicate_members(names)
            result.duplicate_members = duplicates
            if duplicates:
                blockers.append(f"duplicate archive members: {duplicates}")
            missing_packages = _packages_missing(names)
            result.packages_present = not missing_packages
            if missing_packages:
                blockers.append(f"declared packages absent from the wheel: {missing_packages}")
            missing_resources = _resources_missing(names)
            result.resources_present = not missing_resources
            if missing_resources:
                blockers.append(f"MSME resources absent from the wheel: {missing_resources}")
            try:
                member = select_wheel_metadata_member(names)
                meta = email.message_from_bytes(archive.read(member))
            except (KeyError, ReleasePolicyError) as exc:
                blockers.append(f"wheel metadata: {exc}")
            else:
                result.metadata_name = str(meta.get("Name") or "")
                result.metadata_version = str(meta.get("Version") or "")
                if result.metadata_name != DISTRIBUTION_NAME:
                    blockers.append(f"wheel METADATA Name is {result.metadata_name!r}")
                if result.metadata_version != version:
                    blockers.append(
                        f"wheel METADATA Version {result.metadata_version!r} "
                        f"does not match {version}"
                    )
    except zipfile.BadZipFile as exc:
        blockers.append(f"wheel is not a valid zip: {exc}")

    result.blockers = blockers
    result.ok = not blockers
    return result


def verification_to_json(result: ArtifactVerification) -> dict[str, object]:
    """Public verification object. Hash is lowercase hex; no timestamps."""
    return {
        "distribution": result.distribution,
        "version": result.version,
        "wheel": result.wheel,
        "sha256": result.sha256,
        "duplicate_members": list(result.duplicate_members),
        "packages_present": result.packages_present,
        "resources_present": result.resources_present,
        "ok": result.ok,
        "blockers": list(result.blockers),
    }


def artifact_hash(result: ArtifactVerification) -> str:
    return format_artifact_hash(result.sha256)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = verify_release_artifact(args.wheel, args.version)
    encoded = json.dumps(verification_to_json(result), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
