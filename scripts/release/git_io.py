"""Read-only git helpers for release automation.

Refuses mutating verbs. Does not create tags, commits, or pushes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.release.model import ReleasePolicyError

_ALLOWED_VERBS = frozenset({"status", "rev-parse", "tag"})


def git_read(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command in ``root``."""
    if not args:
        raise ReleasePolicyError("git_read requires arguments")
    verb = args[0]
    if verb not in _ALLOWED_VERBS:
        raise ReleasePolicyError(
            f"git verb {verb!r} is not allowed in release automation (read-only)"
        )
    if verb == "tag" and "--list" not in args:
        raise ReleasePolicyError("git tag is only allowed as a listing command")
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def head_commit_sha(root: Path) -> str:
    """Return ``HEAD`` as a 40-character lowercase SHA, or fail closed."""
    from scripts.release.model import parse_commit_sha

    proc = git_read(root, "rev-parse", "HEAD")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise ReleasePolicyError(f"git rev-parse HEAD failed: {detail}")
    return parse_commit_sha(proc.stdout.strip().lower())


def list_tags(root: Path) -> set[str]:
    proc = git_read(root, "tag", "--list")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise ReleasePolicyError(f"git tag --list failed: {detail}")
    return {line for line in proc.stdout.splitlines() if line}


def peeled_tag_sha(root: Path, tag: str) -> str:
    """Return the commit SHA a tag points at. Does not create the tag."""
    from scripts.release.model import parse_commit_sha

    if tag.startswith("-"):
        raise ReleasePolicyError(f"refusing git option-like tag name: {tag!r}")
    proc = git_read(root, "rev-parse", f"{tag}^{{commit}}")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise ReleasePolicyError(f"git rev-parse {tag}^{{commit}} failed: {detail}")
    return parse_commit_sha(proc.stdout.strip().lower())
