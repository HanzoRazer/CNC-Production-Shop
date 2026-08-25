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
    is_witness_tag,
    parse_commit_sha,
    parse_distribution_version,
    tag_for_version,
)


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
            detail=f"canonical tag {canonical} already exists",
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
