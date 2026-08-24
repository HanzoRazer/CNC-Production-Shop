"""Authority tests for distribution vs. subsystem API versions.

Installed-wheel checks that need a real artifact live in ``test_packaging.py``
so they share that module-scoped wheel/venv harness. This module covers the
source-checkout contract: one project version, every packaged ``__version__``
following it, and ``MSME_API_VERSION`` remaining an independent named constant.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

import cnc_version as versioning
import musical_spatial_mapping as msme
from cnc_version import DISTRIBUTION_NAME, DistributionVersionError, distribution_version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
POLICY = ROOT / "docs/governance/VERSIONING_POLICY.md"
MSME_ROOT = ROOT / "musical_spatial_mapping"
GOLDEN = ROOT / "tests/golden/msme_v1_vectors.json"

PACKAGES = (
    "cam_assist",
    "business",
    "parametric",
    "fretboard",
    "materials",
    "acoustic",
    "musical_spatial_mapping",
)


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


def test_canonical_resolver_returns_project_version():
    assert distribution_version() == _project_table()["version"]


def test_all_feature_packages_expose_version():
    for name in PACKAGES:
        module = importlib.import_module(name)
        assert hasattr(module, "__version__")
        assert isinstance(module.__version__, str)
        assert module.__version__


@pytest.mark.parametrize("name", PACKAGES)
def test_feature_package_version_equals_distribution_version(name: str):
    module = importlib.import_module(name)
    assert module.__version__ == distribution_version()


def test_msme_api_version_is_0_2_0():
    assert msme.MSME_API_VERSION == "0.2.0"


def test_distribution_and_api_versions_are_allowed_to_differ():
    # Independence is the rule. They differ today; they may coincide later.
    assert isinstance(msme.__version__, str)
    assert isinstance(msme.MSME_API_VERSION, str)
    assert msme.__version__
    assert msme.MSME_API_VERSION
    assert msme.__version__ == distribution_version()


def test_msme_api_version_is_exported_from_package_root():
    assert "MSME_API_VERSION" in msme.__all__
    from musical_spatial_mapping import MSME_API_VERSION

    assert MSME_API_VERSION == "0.2.0"


def test_msme_version_remains_accessible():
    assert hasattr(msme, "__version__")
    assert isinstance(msme.__version__, str)


def test_internal_version_helper_is_not_exported_from_msme():
    assert "distribution_version" not in msme.__all__
    assert "_distribution_version" not in msme.__all__
    assert "_resolve_distribution_version" not in msme.__all__
    assert "DISTRIBUTION_NAME" not in msme.__all__


def test_existing_msme_public_imports_remain_valid():
    for name in msme.__all__:
        assert hasattr(msme, name), name
    assert len(msme.__all__) == 42


def test_cnc_version_public_surface_is_minimal():
    assert versioning.__all__ == [
        "DISTRIBUTION_NAME",
        "DistributionVersionError",
        "distribution_version",
    ]
    assert not hasattr(versioning, "__version__")


def test_fallback_reads_pyproject_when_metadata_is_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(versioning, "_installed_distribution_version", lambda: None)
    assert distribution_version() == _project_table()["version"]


def test_fallback_equals_project_version():
    resolved = versioning._project_version_from_toml(versioning._locate_pyproject())
    assert resolved == _project_table()["version"]


def test_missing_project_metadata_fails_clearly(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "cnc-production-shop"\n', encoding="utf-8")
    with pytest.raises(DistributionVersionError, match="version"):
        versioning._project_version_from_toml(path)


def test_missing_project_table_fails_clearly(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    with pytest.raises(DistributionVersionError, match=r"\[project\]"):
        versioning._project_version_from_toml(path)


def test_malformed_toml_fails_deterministically(tmp_path: Path):
    path = tmp_path / "pyproject.toml"
    path.write_text("this is not toml [[[", encoding="utf-8")
    with pytest.raises(DistributionVersionError, match="malformed"):
        versioning._project_version_from_toml(path)


def test_unreadable_project_file_fails_clearly(tmp_path: Path):
    path = tmp_path / "missing.toml"
    with pytest.raises(DistributionVersionError, match="could not read"):
        versioning._project_version_from_toml(path)


def test_absent_pyproject_fails_rather_than_fabricating(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(versioning, "_installed_distribution_version", lambda: None)

    def _missing() -> Path:
        raise DistributionVersionError("cnc-production-shop pyproject.toml was not found")

    monkeypatch.setattr(versioning, "_locate_pyproject", _missing)
    with pytest.raises(DistributionVersionError, match="was not found"):
        distribution_version()


def test_resolver_follows_monkeypatched_project_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "cnc-production-shop"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(versioning, "_installed_distribution_version", lambda: None)
    monkeypatch.setattr(versioning, "_locate_pyproject", lambda: pyproject)
    assert distribution_version() == "9.9.9"
    assert msme.MSME_API_VERSION == "0.2.0"


def test_msme_api_version_stays_independent_when_distribution_version_changes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(versioning, "_installed_distribution_version", lambda: "3.1.4")
    assert distribution_version() == "3.1.4"
    assert msme.MSME_API_VERSION == "0.2.0"
    assert msme.MSME_API_VERSION != distribution_version()


def test_no_feature_package_owns_a_distribution_version_literal():
    offenders: list[str] = []
    for name in PACKAGES:
        path = ROOT / name / "__init__.py"
        text = path.read_text(encoding="utf-8")
        if '"0.1.0"' in text or "'0.1.0'" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_resolver_python_has_no_distribution_version_literal():
    text = (ROOT / "cnc_version" / "__init__.py").read_text(encoding="utf-8")
    assert '"0.1.0"' not in text
    assert "'0.1.0'" not in text
    assert '"0.0.0"' not in text


def test_no_package_imports_version_from_another_feature_package():
    for name in PACKAGES:
        text = (ROOT / name / "__init__.py").read_text(encoding="utf-8")
        assert "from cnc_version import distribution_version" in text
        for other in PACKAGES:
            assert f"import {other}" not in text
            assert f"from {other}" not in text


def test_resolver_has_no_feature_domain_dependency():
    text = (ROOT / "cnc_version" / "__init__.py").read_text(encoding="utf-8")
    for banned in PACKAGES:
        assert banned not in text


def test_msme_local_helper_is_gone():
    assert not (MSME_ROOT / "_distribution_version.py").exists()


def test_msme_golden_vectors_file_is_unchanged_fixture():
    # This sprint must not rewrite the behavioral spec; pin presence only.
    assert GOLDEN.is_file()
    assert GOLDEN.stat().st_size > 0


def test_versioning_policy_exists_and_names_authorities():
    assert POLICY.is_file()
    text = POLICY.read_text(encoding="utf-8")
    assert "cnc-production-shop" in text
    assert "MSME_API_VERSION" in text
    assert "Distribution version" in text
    assert "Subsystem API version" in text
    assert "Schema version" in text
    assert "migration complete" in text.lower() or "CNC-VERSION-ALIGNMENT-2" in text
