"""Authority tests for distribution vs. subsystem API versions.

Installed-wheel checks that need a real artifact live in ``test_packaging.py``
so they share that module-scoped wheel/venv harness. This module covers the
source-checkout contract: one project version, MSME ``__version__`` following
it, and ``MSME_API_VERSION`` remaining an independent named constant.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import musical_spatial_mapping as msme
import musical_spatial_mapping._distribution_version as versioning
from musical_spatial_mapping._distribution_version import (
    DISTRIBUTION_NAME,
    DistributionVersionError,
    distribution_version,
    installed_distribution_version,
    locate_pyproject,
    project_version_from_toml,
)

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
POLICY = ROOT / "docs/governance/VERSIONING_POLICY.md"
MSME_ROOT = ROOT / "musical_spatial_mapping"


def _project_table() -> dict:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def test_pyproject_has_exactly_one_project_distribution_version():
    project = _project_table()
    assert "version" in project
    dynamic = project.get("dynamic", [])
    assert "version" not in dynamic
    text = PYPROJECT.read_text(encoding="utf-8")
    project_block = text.split("[project]", 1)[1].split("\n[", 1)[0]
    version_lines = [
        line.strip() for line in project_block.splitlines() if line.strip().startswith("version")
    ]
    assert len(version_lines) == 1
    assert isinstance(project["version"], str)
    assert project["version"]


def test_distribution_name_is_cnc_production_shop():
    assert _project_table()["name"] == "cnc-production-shop"
    assert DISTRIBUTION_NAME == "cnc-production-shop"


def test_msme_runtime_version_equals_project_version_in_checkout():
    assert msme.__version__ == _project_table()["version"]
    assert msme.__version__ == distribution_version()


def test_msme_api_version_is_0_2_0():
    assert msme.MSME_API_VERSION == "0.2.0"


def test_distribution_and_api_versions_are_allowed_to_differ():
    # Independence is the rule. They differ today; they may coincide later.
    assert isinstance(msme.__version__, str)
    assert isinstance(msme.MSME_API_VERSION, str)
    assert msme.__version__
    assert msme.MSME_API_VERSION


def test_msme_api_version_is_exported_from_package_root():
    assert "MSME_API_VERSION" in msme.__all__
    from musical_spatial_mapping import MSME_API_VERSION

    assert MSME_API_VERSION == "0.2.0"


def test_version_remains_accessible():
    assert hasattr(msme, "__version__")
    assert isinstance(msme.__version__, str)


def test_internal_version_helper_is_not_exported():
    assert "distribution_version" not in msme.__all__
    assert "_distribution_version" not in msme.__all__
    assert "_resolve_distribution_version" not in msme.__all__
    assert "DISTRIBUTION_NAME" not in msme.__all__


def test_existing_msme_public_imports_remain_valid():
    for name in msme.__all__:
        assert hasattr(msme, name), name
    assert len(msme.__all__) == 42


def test_fallback_reads_pyproject_when_metadata_is_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(versioning, "installed_distribution_version", lambda: None)
    assert distribution_version() == _project_table()["version"]


def test_fallback_equals_project_version():
    assert project_version_from_toml(locate_pyproject()) == _project_table()["version"]


def test_missing_project_metadata_fails_clearly(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "cnc-production-shop"\n', encoding="utf-8")
    with pytest.raises(DistributionVersionError, match="version"):
        project_version_from_toml(path)


def test_missing_project_table_fails_clearly(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    with pytest.raises(DistributionVersionError, match=r"\[project\]"):
        project_version_from_toml(path)


def test_malformed_toml_fails_deterministically(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text("this is not toml [[[", encoding="utf-8")
    with pytest.raises(DistributionVersionError, match="malformed"):
        project_version_from_toml(path)


def test_unreadable_project_file_fails_clearly(tmp_path: Path):
    path = tmp_path / "missing.toml"
    with pytest.raises(DistributionVersionError, match="could not read"):
        project_version_from_toml(path)


def test_absent_pyproject_fails_rather_than_fabricating(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(versioning, "installed_distribution_version", lambda: None)

    def _missing() -> Path:
        raise DistributionVersionError("cnc-production-shop pyproject.toml was not found")

    monkeypatch.setattr(versioning, "locate_pyproject", _missing)
    with pytest.raises(DistributionVersionError, match="was not found"):
        distribution_version()


def test_resolver_follows_monkeypatched_project_version_not_an_msme_literal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "cnc-production-shop"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(versioning, "installed_distribution_version", lambda: None)
    monkeypatch.setattr(versioning, "locate_pyproject", lambda: pyproject)
    assert distribution_version() == "9.9.9"
    assert msme.MSME_API_VERSION == "0.2.0"


def test_msme_api_version_stays_independent_when_distribution_version_changes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(versioning, "installed_distribution_version", lambda: "3.1.4")
    assert distribution_version() == "3.1.4"
    assert msme.MSME_API_VERSION == "0.2.0"
    assert msme.MSME_API_VERSION != distribution_version()


def test_msme_python_has_no_distribution_version_literal():
    offenders: list[str] = []
    for path in MSME_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '"0.1.0"' in text or "'0.1.0'" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_installed_metadata_is_readable_in_this_checkout():
    installed = installed_distribution_version()
    assert installed == _project_table()["version"]


def test_versioning_policy_exists_and_names_authorities():
    # Lightweight pin of the policy artifact, not a documentation framework.
    assert POLICY.is_file()
    text = POLICY.read_text(encoding="utf-8")
    assert "cnc-production-shop" in text
    assert "MSME_API_VERSION" in text
    assert "Distribution version" in text
    assert "Subsystem API version" in text
    assert "Schema version" in text
    assert "CNC-VERSION-ALIGNMENT-2" in text
