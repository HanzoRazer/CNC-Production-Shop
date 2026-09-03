#!/usr/bin/env python3
"""Canonical-tag eligibility and optional post-tag verification.

Release-candidate automation calls eligibility only. Eligibility fails closed
when ``v<VERSION>`` already exists. Witness tags are ignored.

Post-tag verification is a separate, explicit invocation after a human has
created the tag. This module never creates tags.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.git_io import list_tags, peeled_tag_sha  # noqa: E402
from scripts.release.model import (  # noqa: E402
    WITNESS_TAGS,
    ReleasePolicyError,
    is_canonical_release_tag,
    is_witness_tag,
    parse_commit_sha,
    parse_distribution_version,
    tag_for_version,
)

EXISTING_CANONICAL_TAG_KIND = "existing_canonical_tag"

# Only these kinds keep a verify job green when verification fields passed.
ELIGIBILITY_BLOCKER_KINDS: frozenset[str] = frozenset({EXISTING_CANONICAL_TAG_KIND})

# Known policy/source blockers that are not wheel-verification failures and
# must never be promoted to eligibility by prefix or suffix matching.
NON_ELIGIBILITY_POLICY_KINDS: frozenset[str] = frozenset(
    {
        "canonical_tag_absent_check",
        "dirty_working_tree",
        "missing_changelog",
        "changelog_unready",
        "missing_git_metadata",
        "expected_commit_mismatch",
        "tag_inspection_error",
    }
)

_CANONICAL_TAG_PREFIX = "canonical tag "
_EXISTING_TAG_SUFFIX = " already exists"
_ABSENT_TAG_SUFFIX = " does not exist"


def existing_canonical_tag_blocker(version: str) -> str:
    """Governed eligibility blocker: the canonical tag already exists."""
    return f"{_CANONICAL_TAG_PREFIX}{tag_for_version(version)}{_EXISTING_TAG_SUFFIX}"


def canonical_tag_absent_check_message(version: str) -> str:
    """Readiness check label. PASS when the canonical tag is absent."""
    return f"{_CANONICAL_TAG_PREFIX}{tag_for_version(version)}{_ABSENT_TAG_SUFFIX}"


def _canonical_tag_from_affixed_message(text: str, suffix: str) -> str | None:
    if not (text.startswith(_CANONICAL_TAG_PREFIX) and text.endswith(suffix)):
        return None
    tag = text[len(_CANONICAL_TAG_PREFIX) : len(text) - len(suffix)]
    if not is_canonical_release_tag(tag):
        return None
    return tag


def eligibility_blocker_kind(
    item: str,
    *,
    version: str = "",
    canonical_tag: str = "",
) -> str | None:
    """Return a catalog kind, or None when the string is not eligibility.

    Matching reconstructs the governed message. A valid ``vMAJOR.MINOR.PATCH``
    tag is required in the middle; optional ``version`` / ``canonical_tag``
    from the evidence payload must agree. Unknown wording fails closed.
    """
    text = item.strip()
    tag = _canonical_tag_from_affixed_message(text, _EXISTING_TAG_SUFFIX)
    if tag is None:
        return None
    if canonical_tag and tag != canonical_tag:
        return None
    if version:
        try:
            if text != existing_canonical_tag_blocker(version):
                return None
        except ReleasePolicyError:
            return None
    return EXISTING_CANONICAL_TAG_KIND


def is_existing_canonical_tag_blocker(
    item: str,
    *,
    version: str = "",
    canonical_tag: str = "",
) -> bool:
    return (
        eligibility_blocker_kind(item, version=version, canonical_tag=canonical_tag)
        == EXISTING_CANONICAL_TAG_KIND
    )


def is_canonical_tag_absent_check_blocker(item: str, *, version: str = "") -> bool:
    """True for the readiness FAIL label when the canonical tag is present."""
    text = item.strip()
    if version:
        try:
            return text == canonical_tag_absent_check_message(version)
        except ReleasePolicyError:
            return False
    return _canonical_tag_from_affixed_message(text, _ABSENT_TAG_SUFFIX) is not None


def policy_blocker_kind(item: str, *, version: str = "") -> str | None:
    """Classify a known policy blocker. Unknown strings return None."""
    text = item.strip()
    if is_existing_canonical_tag_blocker(text, version=version):
        return EXISTING_CANONICAL_TAG_KIND
    if is_canonical_tag_absent_check_blocker(text, version=version):
        return "canonical_tag_absent_check"
    if text == "working tree clean":
        return "dirty_working_tree"
    if text == "CHANGELOG.md exists":
        return "missing_changelog"
    if text.startswith("changelog has a ") and "section or release-ready Unreleased" in text:
        return "changelog_unready"
    if text == "git metadata present at --root":
        return "missing_git_metadata"
    if "does not match expected_commit" in text:
        return "expected_commit_mismatch"
    return None


@dataclass(frozen=True)
class TagEligibility:
    version: str
    canonical_tag: str
    exists: bool
    eligible: bool
    detail: str


def inspect_tag_eligibility(root: Path, version: str) -> TagEligibility:
    parsed = parse_distribution_version(version)
    canonical = tag_for_version(parsed)
    tags = list_tags(root)
    distribution_tags = {tag for tag in tags if tag not in WITNESS_TAGS}
    exists = canonical in distribution_tags
    if exists:
        return TagEligibility(
            version=parsed,
            canonical_tag=canonical,
            exists=True,
            eligible=False,
            detail=existing_canonical_tag_blocker(parsed),
        )
    witness_present = sorted(tag for tag in tags if is_witness_tag(tag))
    extra = (
        f"witness tags present and ignored: {', '.join(witness_present)}"
        if witness_present
        else "no canonical tag present"
    )
    return TagEligibility(
        version=parsed,
        canonical_tag=canonical,
        exists=False,
        eligible=True,
        detail=extra,
    )


@dataclass(frozen=True)
class PostTagVerification:
    ok: bool
    canonical_tag: str
    tag_sha: str
    expected_commit: str
    detail: str


def verify_post_tag(root: Path, version: str, expected_commit: str) -> PostTagVerification:
    """Confirm an already-created canonical tag points at ``expected_commit``.

    Does not create, move, or delete the tag.
    """
    parsed = parse_distribution_version(version)
    canonical = tag_for_version(parsed)
    expected = parse_commit_sha(expected_commit)
    eligibility = inspect_tag_eligibility(root, parsed)
    if eligibility.eligible:
        return PostTagVerification(
            ok=False,
            canonical_tag=canonical,
            tag_sha="",
            expected_commit=expected,
            detail=f"{canonical} does not exist; post-tag verification cannot run",
        )
    try:
        peeled = peeled_tag_sha(root, canonical)
    except ReleasePolicyError as exc:
        return PostTagVerification(
            ok=False,
            canonical_tag=canonical,
            tag_sha="",
            expected_commit=expected,
            detail=str(exc),
        )
    if peeled != expected:
        return PostTagVerification(
            ok=False,
            canonical_tag=canonical,
            tag_sha=peeled,
            expected_commit=expected,
            detail=f"{canonical} points at {peeled}, expected {expected}",
        )
    return PostTagVerification(
        ok=True,
        canonical_tag=canonical,
        tag_sha=peeled,
        expected_commit=expected,
        detail=f"{canonical} points at {peeled}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--post-tag",
        action="store_true",
        help="verify an existing canonical tag (does not create it)",
    )
    parser.add_argument("--expected-commit", default="")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.post_tag:
        if not args.expected_commit:
            print("FAIL --expected-commit is required with --post-tag", file=sys.stderr)
            return 1
        report = verify_post_tag(root, args.version, args.expected_commit)
        sys.stdout.write(
            json.dumps(
                {
                    "ok": report.ok,
                    "canonical_tag": report.canonical_tag,
                    "tag_sha": report.tag_sha,
                    "expected_commit": report.expected_commit,
                    "detail": report.detail,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return 0 if report.ok else 1
    eligibility = inspect_tag_eligibility(root, args.version)
    sys.stdout.write(
        json.dumps(
            {
                "version": eligibility.version,
                "canonical_tag": eligibility.canonical_tag,
                "exists": eligibility.exists,
                "eligible": eligibility.eligible,
                "detail": eligibility.detail,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if eligibility.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
