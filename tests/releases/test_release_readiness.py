"""Release-readiness CLI and release-note renderer."""

from __future__ import annotations

import email
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.release.check_release_readiness import check
from scripts.release.model import (
    changelog_has_release_ready_unreleased,
    changelog_has_version_section,
    parse_changelog,
    tag_for_version,
)
from scripts.release.render_release_notes import render

ROOT = Path(__file__).resolve().parents[2]
FEATURE_PACKAGES = (
    "cam_assist",
    "business",
    "parametric",
    "fretboard",
    "materials",
    "acoustic",
    "musical_spatial_mapping",
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "release-tests@example.com")
    _git(path, "config", "user.name", "Release Tests")
    (path / "README").write_text("x\n", encoding="utf-8")
    _git(path, "add", "README")
    _git(path, "commit", "-m", "init")


def _write_pyproject(path: Path, version: str) -> None:
    path.write_text(
        f'[project]\nname = "cnc-production-shop"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def _write_changelog(path: Path, body: str) -> None:
    path.write_text("# Changelog\n\n" + body, encoding="utf-8")


def _fake_wheel(path: Path, version: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    filename = f"cnc_production_shop-{version}-py3-none-any.whl"
    wheel = path / filename
    meta = (f"Metadata-Version: 2.1\nName: cnc-production-shop\nVersion: {version}\n").encode()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"cnc_production_shop-{version}.dist-info/METADATA", meta)
    return wheel


def _commit_release_tree(path: Path, version: str) -> None:
    _write_pyproject(path / "pyproject.toml", version)
    _write_changelog(path / "CHANGELOG.md", "## Unreleased\n\n### Fixed\n- ready\n")
    _git(path, "add", "pyproject.toml", "CHANGELOG.md")
    _git(path, "commit", "-m", "release tree")


def test_readiness_fails_on_dirty_working_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.0")
    (tmp_path / "dirt").write_text("nope\n", encoding="utf-8")
    assert check("0.1.0", tmp_path, None) == 1


def test_readiness_fails_if_canonical_tag_already_exists(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.0")
    _git(tmp_path, "tag", tag_for_version("0.1.0"))
    assert check("0.1.0", tmp_path, None) == 1


def test_readiness_ignores_witness_tag(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.0")
    _git(tmp_path, "tag", "msme-001-foundation-original")
    assert check("0.1.0", tmp_path, None) == 0


def test_readiness_fails_if_package_versions_drift(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "9.9.9")
    assert check("9.9.9", tmp_path, None) == 1


def test_readiness_fails_if_wheel_metadata_disagrees(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.0")
    wheel = _fake_wheel(tmp_path.parent / "wheels-disagree", "0.2.0")
    assert check("0.1.0", tmp_path, wheel) == 1


def test_readiness_passes_on_clean_synthetic_fixture(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_release_tree(tmp_path, "0.1.0")
    wheel = _fake_wheel(tmp_path.parent / "wheels-ready", "0.1.0")
    assert check("0.1.0", tmp_path, wheel) == 0


def test_current_tree_is_not_release_ready_without_unreleased_entries() -> None:
    # CHANGELOG.md is Unreleased-only with no categorized entries, by policy.
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## Unreleased" in changelog
    assert not changelog_has_version_section(changelog, "0.1.0")
    assert not changelog_has_release_ready_unreleased(changelog)


def test_release_note_rendering_is_deterministic() -> None:
    changelog = "# Changelog\n\n## Unreleased\n\n### Fixed\n- one\n\n### Added\n- two\n"
    manifest = {
        "release_id": "REL-CNC-9.9.9",
        "release_state": "development",
        "commit_sha": "a" * 40,
        "tag": "",
        "example_only": True,
        "artifacts": [
            {
                "filename": "cnc_production_shop-9.9.9-py3-none-any.whl",
                "sha256": "sha256:" + "c" * 64,
            }
        ],
        "subsystem_versions": {"MSME_API_VERSION": "0.2.0"},
    }
    first = render("9.9.9", changelog_text=changelog, manifest=manifest, date="2026-08-24")
    second = render("9.9.9", changelog_text=changelog, manifest=manifest, date="2026-08-24")
    assert first == second
    assert "MSME_API_VERSION" in first
    assert "0.2.0" in first
    assert first.index("## Added") < first.index("## Fixed")


def test_release_notes_do_not_invent_absent_sections() -> None:
    changelog = "# Changelog\n\n## Unreleased\n\n### Fixed\n- only this\n"
    text = render("0.1.0", changelog_text=changelog, manifest=None, date=None)
    assert "## Fixed" in text
    assert "## Added" not in text
    assert "## Security" not in text


def test_changelog_parser_reads_version_section() -> None:
    text = "# Changelog\n\n## Unreleased\n\n## [0.1.1]\n\n### Packaging\n- wheel\n"
    sections = parse_changelog(text)
    assert changelog_has_version_section(text, "0.1.1")
    packaging = next(s for s in sections if s.heading == "0.1.1")
    assert packaging.categories["Packaging"] == ("wheel",)


def test_renderer_cli_and_readiness_cli_are_read_only() -> None:
    tags_before = subprocess.run(
        ["git", "tag", "--list"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pyproject_before = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    renderer = ROOT / "scripts" / "release" / "render_release_notes.py"
    proc = subprocess.run(
        [sys.executable, str(renderer), "--version", "0.1.0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    ready = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release" / "check_release_readiness.py"),
            "--version",
            "0.1.0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ready.returncode == 1
    tags_after = subprocess.run(
        ["git", "tag", "--list"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert tags_before == tags_after
    # CI checkouts often omit remote tags. Require only that the CLIs did not
    # create a canonical release tag. Witness-tag preservation is covered by
    # test_readiness_ignores_witness_tag on a synthetic repo.
    listed = {line for line in tags_after.splitlines() if line}
    assert tag_for_version("0.1.0") not in listed
    assert (ROOT / "pyproject.toml").read_text(encoding="utf-8") == pyproject_before
    assert 'version = "0.1.0"' in pyproject_before


def test_all_feature_packages_still_match_distribution() -> None:
    from cnc_version import distribution_version

    expected = distribution_version()
    for name in FEATURE_PACKAGES:
        module = __import__(name)
        assert module.__version__ == expected


def test_fake_wheel_metadata_round_trip(tmp_path: Path) -> None:
    wheel = _fake_wheel(tmp_path, "0.1.0")
    with zipfile.ZipFile(wheel) as archive:
        meta_name = next(n for n in archive.namelist() if n.endswith("METADATA"))
        meta = email.message_from_bytes(archive.read(meta_name))
    assert meta.get("Version") == "0.1.0"
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert len(digest) == 64
