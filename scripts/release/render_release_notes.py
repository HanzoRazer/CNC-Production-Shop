#!/usr/bin/env python3
"""Render deterministic Markdown release notes from governed inputs.

Usage:
    python scripts/release/render_release_notes.py \\
        --version 0.1.0 \\
        --manifest fixtures/releases/release_manifest_example_v1.json

Output only. No GitHub writes. No publishing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import (  # noqa: E402
    CHANGELOG_CATEGORIES,
    parse_changelog,
    parse_distribution_version,
    tag_for_version,
)


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} is not a JSON object")
    return data


def render(
    version: str,
    *,
    changelog_text: str,
    manifest: dict | None,
    date: str | None,
) -> str:
    parsed = parse_distribution_version(version)
    sections = parse_changelog(changelog_text)
    chosen = None
    for section in sections:
        if section.heading == parsed:
            chosen = section
            break
    if chosen is None:
        for section in sections:
            if section.heading.lower() == "unreleased":
                chosen = section
                break

    lines = [f"# cnc-production-shop {parsed}", ""]
    if manifest and manifest.get("example_only"):
        lines.extend(["This is synthetic example output, not a production release.", ""])
    if date:
        lines.extend([f"Date: {date}", ""])
    if manifest:
        lines.extend(
            [
                f"Release ID: {manifest.get('release_id', '')}",
                f"State: {manifest.get('release_state', '')}",
                f"Commit: {manifest.get('commit_sha', '')}",
            ]
        )
        tag = str(manifest.get("tag") or "")
        lines.append(f"Tag: {tag or tag_for_version(parsed) + ' (proposed)'}")
        artifacts = manifest.get("artifacts") or []
        if artifacts:
            first = artifacts[0]
            lines.append(f"Artifact: {first.get('filename', '')}")
            lines.append(f"SHA-256: {first.get('sha256', '')}")
        subsystems = manifest.get("subsystem_versions") or {}
        if subsystems:
            lines.append("")
            lines.append("## Subsystem API versions")
            for key in sorted(subsystems):
                lines.append(f"- `{key}`: {subsystems[key]}")
        lines.append("")

    if chosen is None:
        lines.append("No changelog section was supplied for this version.")
        return "\n".join(lines).rstrip() + "\n"

    emitted_any = False
    for category in CHANGELOG_CATEGORIES:
        items = chosen.categories.get(category)
        if not items:
            continue
        emitted_any = True
        lines.append(f"## {category}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    if not emitted_any:
        lines.append("No categorized changelog entries were present.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    changelog_text = args.changelog.read_text(encoding="utf-8") if args.changelog.is_file() else ""
    manifest = _load_json(args.manifest) if args.manifest else None
    sys.stdout.write(
        render(
            args.version,
            changelog_text=changelog_text,
            manifest=manifest,
            date=args.date,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
