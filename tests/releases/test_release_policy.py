"""Semantic version, tag, and artifact naming rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release.model import (
    DISTRIBUTION_NAME,
    ReleasePolicyError,
    is_canonical_release_tag,
    is_witness_tag,
    package_binds_distribution_version,
    parse_artifact_hash,
    parse_commit_sha,
    parse_created_at,
    parse_distribution_version,
    parse_release_state,
    read_assigned_string_constant,
    select_wheel_metadata_member,
    tag_for_version,
    version_from_tag,
    version_from_wheel_filename,
    wheel_filename_for_version,
)


@pytest.mark.parametrize("value", ["0.1.0", "0.1.1", "0.2.0"])
def test_valid_distribution_versions(value: str) -> None:
    assert parse_distribution_version(value) == value


@pytest.mark.parametrize("value", ["1", "01.0.0", "0.1", "0.1.0.1", ""])
def test_reject_malformed_project_versions(value: str) -> None:
    with pytest.raises(ReleasePolicyError):
        parse_distribution_version(value)


def test_reject_v_prefix_as_project_version() -> None:
    with pytest.raises(ReleasePolicyError, match="tag form"):
        parse_distribution_version("v0.1.0")


def test_accept_v_prefix_as_tag_for_matching_version() -> None:
    assert version_from_tag("v0.1.0") == "0.1.0"
    assert tag_for_version("0.1.0") == "v0.1.0"
    assert is_canonical_release_tag("v0.1.0")


def test_reject_tag_version_mismatch() -> None:
    assert version_from_tag("v0.1.1") != "0.1.0"
    with pytest.raises(ReleasePolicyError):
        version_from_tag("release-0.1.0")


def test_witness_tag_is_not_a_distribution_release_tag() -> None:
    assert is_witness_tag("msme-001-foundation-original")
    assert not is_canonical_release_tag("msme-001-foundation-original")


def test_distribution_name_is_cnc_production_shop() -> None:
    assert DISTRIBUTION_NAME == "cnc-production-shop"


def test_wheel_filename_version_round_trip() -> None:
    assert wheel_filename_for_version("0.1.1") == "cnc_production_shop-0.1.1-py3-none-any.whl"
    assert version_from_wheel_filename("cnc_production_shop-0.1.1-py3-none-any.whl") == "0.1.1"


def test_artifact_hash_must_be_sha256() -> None:
    digest = "sha256:" + ("a" * 64)
    assert parse_artifact_hash(digest) == digest
    with pytest.raises(ReleasePolicyError):
        parse_artifact_hash("a" * 64)
    with pytest.raises(ReleasePolicyError):
        parse_artifact_hash("sha256:xyz")


def test_commit_sha_format() -> None:
    sha = "b" * 40
    assert parse_commit_sha(sha) == sha
    with pytest.raises(ReleasePolicyError):
        parse_commit_sha("b" * 7)


def test_unknown_release_state_rejected() -> None:
    with pytest.raises(ReleasePolicyError, match="unknown release_state"):
        parse_release_state("shipped")
    assert parse_release_state("development") == "development"


@pytest.mark.parametrize(
    "value", ["2026-08-24", "2026-08-24T00:00:00Z", "2026-08-24T00:00:00+00:00"]
)
def test_created_at_accepts_iso8601(value: str) -> None:
    assert parse_created_at(value) == value


@pytest.mark.parametrize("value", ["", "soon", "2026/08/24", "2026-08-24T00:00:00", "2026-13-40"])
def test_created_at_rejects_non_iso8601(value: str) -> None:
    with pytest.raises(ReleasePolicyError, match="ISO 8601"):
        parse_created_at(value)


def test_package_bind_detects_resolver_and_alias() -> None:
    assert package_binds_distribution_version(
        "from cnc_version import distribution_version\n\n__version__ = distribution_version()\n"
    )
    assert package_binds_distribution_version(
        "from cnc_version import distribution_version as _resolve\n\n__version__ = _resolve()\n"
    )
    assert not package_binds_distribution_version('__version__ = "0.1.0"\n')
    root = Path(__file__).resolve().parents[2]
    for name in (
        "cam_assist",
        "business",
        "parametric",
        "fretboard",
        "materials",
        "acoustic",
        "musical_spatial_mapping",
    ):
        source = (root / name / "__init__.py").read_text(encoding="utf-8")
        assert package_binds_distribution_version(source), name


def test_read_assigned_string_constant() -> None:
    assert (
        read_assigned_string_constant('MSME_API_VERSION = "0.2.0"\n', "MSME_API_VERSION") == "0.2.0"
    )
    with pytest.raises(ReleasePolicyError):
        read_assigned_string_constant("__version__ = 'x'\n", "MSME_API_VERSION")


def test_select_wheel_metadata_member_is_fail_closed() -> None:
    assert (
        select_wheel_metadata_member(["cnc_production_shop-0.1.0.dist-info/METADATA"])
        == "cnc_production_shop-0.1.0.dist-info/METADATA"
    )
    with pytest.raises(ReleasePolicyError, match="no .dist-info/METADATA"):
        select_wheel_metadata_member(["empty.txt"])
    with pytest.raises(ReleasePolicyError, match="2 METADATA"):
        select_wheel_metadata_member(
            [
                "a.dist-info/METADATA",
                "b.dist-info/METADATA",
            ]
        )


def test_scripts_do_not_write_network_or_tags_or_pyproject() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    forbidden = (
        "git tag -a",
        "git tag -m",
        "gh release",
        "twine ",
        "pypi",
        "urllib.request",
        "requests.post",
        "httpx",
    )
    for path in (root / "scripts" / "release").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} contains {token!r}"
        assert "pyproject.toml" not in text or "write" not in text.lower() or "read" in text
    validator = (root / "scripts" / "validate_release_manifests.py").read_text(encoding="utf-8")
    for token in ("git tag -a", "twine ", "requests.post"):
        assert token not in validator


def test_changelog_is_unreleased_only_with_no_fabricated_history() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Changelog\n")
    assert "## Unreleased" in text
    assert "## [0.1.0]" not in text
    assert "## 0.1.0" not in text


def test_release_policy_documents_exist_and_stay_internal_by_default() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = (root / "docs" / "governance" / "RELEASE_POLICY.md").read_text(encoding="utf-8")
    checklist = (root / "docs" / "governance" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    changelog_policy = (root / "docs" / "governance" / "CHANGELOG_POLICY.md").read_text(
        encoding="utf-8"
    )
    assert "REL-CNC-" in policy
    assert "vMAJOR.MINOR.PATCH" in policy
    assert "msme-001-foundation-original" in policy
    assert "internal-only" in policy
    assert "CNC-RELEASE-EXECUTION-1" in policy
    assert "Human-executable" in checklist
    assert "Added" in changelog_policy
    assert "Governance" in changelog_policy
