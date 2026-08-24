"""Pure release-policy helpers: SemVer, tags, artifacts, hashes.

No Git writes. No network. No mutation of ``pyproject.toml``.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import datetime

DISTRIBUTION_NAME = "cnc-production-shop"
RELEASE_STATES = frozenset({"development", "release_candidate", "released", "withdrawn"})
CANONICAL_TAG_PREFIX = "v"
WITNESS_TAGS = frozenset({"msme-001-foundation-original"})
WHEEL_SUFFIX = "-py3-none-any.whl"
WHEEL_PREFIX = "cnc_production_shop-"
SHA256_PREFIX = "sha256:"
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RELEASE_ID_RE = re.compile(r"^REL-CNC-(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CREATED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2}))?$"
)
CHANGELOG_CATEGORIES = (
    "Added",
    "Changed",
    "Fixed",
    "Deprecated",
    "Removed",
    "Security",
    "Packaging",
    "Governance",
)


class ReleasePolicyError(ValueError):
    """Raised when a release-policy value is malformed."""


def parse_distribution_version(value: str) -> str:
    """Accept ``MAJOR.MINOR.PATCH`` only. Reject a leading ``v``."""
    if value.startswith("v") or value.startswith("V"):
        raise ReleasePolicyError(f"{value!r} is a tag form, not a project distribution version")
    if not VERSION_RE.fullmatch(value):
        raise ReleasePolicyError(f"malformed distribution version: {value!r}")
    return value


def tag_for_version(version: str) -> str:
    """Return the canonical distribution tag for ``version``."""
    return f"{CANONICAL_TAG_PREFIX}{parse_distribution_version(version)}"


def version_from_tag(tag: str) -> str:
    """Accept ``vMAJOR.MINOR.PATCH`` and return the version."""
    if not tag.startswith(CANONICAL_TAG_PREFIX):
        raise ReleasePolicyError(f"{tag!r} is not a canonical distribution tag")
    return parse_distribution_version(tag[len(CANONICAL_TAG_PREFIX) :])


def is_canonical_release_tag(tag: str) -> bool:
    try:
        version_from_tag(tag)
    except ReleasePolicyError:
        return False
    return True


def is_witness_tag(tag: str) -> bool:
    return tag in WITNESS_TAGS


def release_id_for_version(version: str) -> str:
    return f"REL-CNC-{parse_distribution_version(version)}"


def parse_release_id(release_id: str) -> str:
    match = RELEASE_ID_RE.fullmatch(release_id)
    if match is None:
        raise ReleasePolicyError(f"malformed release_id: {release_id!r}")
    return parse_distribution_version(release_id.removeprefix("REL-CNC-"))


def wheel_filename_for_version(version: str) -> str:
    return f"{WHEEL_PREFIX}{parse_distribution_version(version)}{WHEEL_SUFFIX}"


def version_from_wheel_filename(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1]
    if not name.startswith(WHEEL_PREFIX) or not name.endswith(WHEEL_SUFFIX):
        raise ReleasePolicyError(f"malformed wheel filename: {filename!r}")
    return parse_distribution_version(name[len(WHEEL_PREFIX) : -len(WHEEL_SUFFIX)])


def parse_artifact_hash(value: str) -> str:
    if not value.startswith(SHA256_PREFIX):
        raise ReleasePolicyError(f"artifact hash must start with {SHA256_PREFIX!r}")
    digest = value[len(SHA256_PREFIX) :]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ReleasePolicyError("artifact hash must be sha256: plus 64 lowercase hex chars")
    return value


def parse_commit_sha(value: str) -> str:
    if not COMMIT_SHA_RE.fullmatch(value):
        raise ReleasePolicyError(f"commit_sha must be 40 lowercase hex chars: {value!r}")
    return value


def parse_release_state(value: str) -> str:
    if value not in RELEASE_STATES:
        raise ReleasePolicyError(f"unknown release_state: {value!r}")
    return value


def parse_created_at(value: str) -> str:
    """Accept an ISO 8601 date or timezone-aware datetime."""
    if not CREATED_AT_RE.fullmatch(value):
        raise ReleasePolicyError("created_at must be an ISO 8601 date or timezone-aware datetime")
    try:
        if "T" in value:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            datetime.fromisoformat(normalized)
        else:
            datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ReleasePolicyError(f"created_at is not a valid ISO 8601 value: {value!r}") from exc
    return value


def select_wheel_metadata_member(names: list[str]) -> str:
    """Return the unique ``*.dist-info/METADATA`` member, or fail closed."""
    members = [name for name in names if name.endswith(".dist-info/METADATA")]
    if not members:
        raise ReleasePolicyError("wheel has no .dist-info/METADATA member")
    if len(members) != 1:
        raise ReleasePolicyError(f"wheel has {len(members)} METADATA members")
    return members[0]


def package_binds_distribution_version(source: str) -> bool:
    """True when ``__version__`` is assigned from ``cnc_version.distribution_version()``."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ReleasePolicyError(f"cannot parse package source: {exc}") from exc

    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "cnc_version":
            for alias in node.names:
                if alias.name == "distribution_version":
                    imported.add(alias.asname or alias.name)
    if not imported:
        return False

    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in targets
        ):
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in imported
            and not value.args
            and not value.keywords
        ):
            return True
    return False


def read_assigned_string_constant(source: str, name: str) -> str:
    """Read a module-level ``NAME = "..."`` assignment."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ReleasePolicyError(f"cannot parse source for {name}: {exc}") from exc
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
            return value.value
        raise ReleasePolicyError(f"{name} must be assigned a non-empty string literal")
    raise ReleasePolicyError(f"{name} assignment was not found")


@dataclass(frozen=True)
class ChangelogSection:
    heading: str
    categories: dict[str, tuple[str, ...]]


def parse_changelog(text: str) -> list[ChangelogSection]:
    """Split a Keep-a-Changelog-style document into heading sections."""
    sections: list[ChangelogSection] = []
    current_heading = ""
    current_category = ""
    categories: dict[str, list[str]] = {}
    items: list[str] = []

    def _flush_category() -> None:
        nonlocal items
        if current_category:
            categories[current_category] = list(items)
        items = []

    def _flush_section() -> None:
        nonlocal categories, current_heading, current_category
        _flush_category()
        if current_heading:
            sections.append(
                ChangelogSection(
                    heading=current_heading,
                    categories={k: tuple(v) for k, v in categories.items()},
                )
            )
        categories = {}
        current_category = ""

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            _flush_section()
            current_heading = line[3:].strip().strip("[]")
            continue
        if line.startswith("### "):
            _flush_category()
            current_category = line[4:].strip()
            continue
        if line.startswith("- ") and current_category:
            items.append(line[2:].strip())
    _flush_section()
    return sections


def changelog_has_version_section(text: str, version: str) -> bool:
    target = parse_distribution_version(version)
    return any(section.heading == target for section in parse_changelog(text))


def changelog_has_release_ready_unreleased(text: str) -> bool:
    for section in parse_changelog(text):
        if section.heading.lower() != "unreleased":
            continue
        for name in CHANGELOG_CATEGORIES:
            if section.categories.get(name):
                return True
    return False
