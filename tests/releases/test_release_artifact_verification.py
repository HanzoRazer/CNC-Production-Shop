"""Wheel inspection and hash gates for release-candidate automation."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from scripts.release.model import (
    DECLARED_PACKAGES,
    DISTRIBUTION_NAME,
    REQUIRED_MSME_RESOURCE_SUFFIXES,
    sha256_hex,
    wheel_filename_for_version,
)
from scripts.release.verify_release_artifact import (
    verify_release_artifact,
)


def _metadata_bytes(version: str, name: str = DISTRIBUTION_NAME) -> bytes:
    return (f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: test\n").encode()


def make_wheel(
    directory: Path,
    version: str,
    *,
    filename: str | None = None,
    metadata_version: str | None = None,
    include_packages: bool = True,
    include_resources: bool = True,
    duplicate_member: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = filename or wheel_filename_for_version(version)
    wheel = directory / name
    meta_version = metadata_version if metadata_version is not None else version
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"cnc_production_shop-{version}.dist-info/METADATA",
            _metadata_bytes(meta_version),
        )
        archive.writestr(
            f"cnc_production_shop-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        if include_packages:
            for pkg in DECLARED_PACKAGES:
                archive.writestr(f"{pkg}/__init__.py", "# pkg\n")
        if include_resources:
            base = "musical_spatial_mapping/resources/instruments"
            archive.writestr(f"{base}/examples/guitar-standard-6.json", "{}")
            archive.writestr(f"{base}/examples/bass-fretless-4.json", "{}")
            archive.writestr(f"{base}/examples/mandolin-standard.json", "{}")
            archive.writestr(f"{base}/schema/instrument-profile-v1.schema.json", "{}")
        if duplicate_member:
            archive.writestr("dup.txt", "one")
            archive.writestr("dup.txt", "two")
    return wheel


def test_valid_wheel_passes(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    result = verify_release_artifact(wheel, "0.1.2")
    assert result.ok
    assert result.duplicate_members == []
    assert result.packages_present
    assert result.resources_present
    assert result.sha256 == sha256_hex(wheel.read_bytes())
    assert result.metadata_name == DISTRIBUTION_NAME
    assert result.metadata_version == "0.1.2"


def test_wrong_wheel_filename_fails(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", filename="not_a_canonical_wheel.whl")
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert any("filename" in item for item in result.blockers)


def test_wrong_metadata_version_fails(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", metadata_version="9.9.9")
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert any("METADATA Version" in item for item in result.blockers)


def test_duplicate_member_fails(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", duplicate_member=True)
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert "dup.txt" in result.duplicate_members
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert names.count("dup.txt") > 1


def test_missing_package_fails(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", include_packages=False)
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert not result.packages_present
    assert any("declared packages absent" in item for item in result.blockers)


def test_missing_msme_resource_fails(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2", include_resources=False)
    result = verify_release_artifact(wheel, "0.1.2")
    assert not result.ok
    assert not result.resources_present
    assert any("MSME resources absent" in item for item in result.blockers)
    for suffix in REQUIRED_MSME_RESOURCE_SUFFIXES:
        assert any(suffix in item for item in result.blockers)


def test_hash_generated_correctly(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    result = verify_release_artifact(wheel, "0.1.2")
    assert result.sha256 == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert len(result.sha256) == 64


def test_modified_wheel_changes_hash(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "0.1.2")
    first = verify_release_artifact(wheel, "0.1.2")
    wheel.write_bytes(wheel.read_bytes() + b"\x00")
    second = verify_release_artifact(wheel, "0.1.2")
    assert first.sha256 != second.sha256
    assert first.ok
    # Appending a byte changes the digest even if the zip still parses.
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == second.sha256


def test_verification_json_has_no_timestamp(tmp_path: Path) -> None:
    from scripts.release.verify_release_artifact import verification_to_json

    wheel = make_wheel(tmp_path, "0.1.2")
    payload = verification_to_json(verify_release_artifact(wheel, "0.1.2"))
    assert "created_at" not in payload
    assert "timestamp" not in payload
    assert payload["distribution"] == DISTRIBUTION_NAME
