"""Canonical ``cnc-production-shop`` distribution version.

All package-level ``__version__`` attributes shipped inside this wheel report
the containing distribution version. Subsystem API maturity uses an explicitly
named constant such as ``MSME_API_VERSION``, never ``__version__``.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

DISTRIBUTION_NAME = "cnc-production-shop"

__all__ = [
    "DISTRIBUTION_NAME",
    "DistributionVersionError",
    "distribution_version",
]


class DistributionVersionError(RuntimeError):
    """Raised when the distribution version cannot be resolved deterministically."""


def _installed_distribution_version() -> str | None:
    """Return the installed distribution version, or ``None`` if it is not installed."""
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return None


def _locate_pyproject() -> Path:
    """Find this repository's ``pyproject.toml`` by walking from this file."""
    for directory in Path(__file__).resolve().parents:
        candidate = directory / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            data = tomllib.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project")
        if isinstance(project, dict) and project.get("name") == DISTRIBUTION_NAME:
            return candidate
    raise DistributionVersionError(
        "cnc-production-shop pyproject.toml was not found; cannot resolve "
        "the distribution version from a source checkout"
    )


def _project_version_from_toml(path: Path) -> str:
    """Read ``[project].version`` from ``path``.

    Fails explicitly if the file is missing, malformed, or has no usable
    version. Does not fabricate a sentinel value.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DistributionVersionError(f"could not read project metadata at {path}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise DistributionVersionError(f"malformed pyproject.toml at {path}: {exc}") from exc
    project = data.get("project")
    if not isinstance(project, dict):
        raise DistributionVersionError(
            f"{path} has no [project] table; cannot resolve distribution version"
        )
    value = project.get("version")
    if not isinstance(value, str) or not value.strip():
        raise DistributionVersionError(
            f"{path} [project].version is missing or not a non-empty string"
        )
    return value


def _project_version_from_checkout() -> str:
    """Read ``[project].version`` from the repository ``pyproject.toml``."""
    return _project_version_from_toml(_locate_pyproject())


def distribution_version() -> str:
    """Return the ``cnc-production-shop`` distribution version.

    Prefers installed package metadata. In a source checkout where the
    distribution is not installed, reads ``[project].version`` from
    ``pyproject.toml``. Does not fabricate a version.
    """
    installed = _installed_distribution_version()
    if installed is not None:
        return installed
    return _project_version_from_checkout()
