#!/usr/bin/env python3
"""Render a human-readable release-candidate evidence report.

Usage:
    python scripts/release/generate_release_evidence.py --input evidence.json --output report.md

Does not create tags, mutate source, or publish.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.model import RESULT_BLOCKED, RESULT_READY  # noqa: E402


def render_evidence(payload: dict[str, object]) -> str:
    """Render Markdown from a machine-generated evidence payload."""
    result = str(payload.get("result") or RESULT_BLOCKED)
    version = str(payload.get("version") or "")
    lines = [
        f"# Release candidate evidence — {version}",
        "",
        f"RESULT: {result}",
        "",
        "## Identity",
        "",
        "```text",
        f"distribution: {payload.get('distribution', '')}",
        f"version:      {version}",
        f"release ID:   {payload.get('release_id', '')}",
        f"state:        {payload.get('release_state', '')}",
        "```",
        "",
        "## Source",
        "",
        "```text",
        f"commit SHA:   {payload.get('commit_sha', '')}",
        f"Python:       {payload.get('python_version', '')}",
        "```",
        "",
        "## Workflow",
        "",
        "```text",
        f"run:          {payload.get('workflow_run', 'local')}",
        f"test summary: {payload.get('test_summary', '')}",
        f"CI summary:   {payload.get('ci_summary', '')}",
        "```",
        "",
        "## Artifact",
        "",
        "```text",
        f"wheel:        {payload.get('wheel', '')}",
        f"SHA-256:      {payload.get('sha256', '')}",
        f"duplicates:   {payload.get('duplicate_members', [])}",
        "```",
        "",
        "## Verification",
        "",
        "```text",
        f"version authority: {payload.get('version_authority', '')}",
        f"tests:             {payload.get('tests', '')}",
        f"wheel build:       {payload.get('wheel_build', '')}",
        f"fresh install:     {payload.get('fresh_install', '')}",
        f"package parity:    {payload.get('package_parity', '')}",
        f"MSME resources:    {payload.get('msme_resources', '')}",
        f"MSME CLI:          {payload.get('msme_cli', '')}",
        f"MSME_API_VERSION:  {payload.get('msme_api_version', '')}",
        f"manifest:          {payload.get('manifest', '')}",
        "```",
        "",
        "## Tag eligibility",
        "",
        "```text",
        f"canonical tag: {payload.get('canonical_tag', '')}",
        f"eligibility:   {payload.get('tag_eligibility', '')}",
        "```",
        "",
    ]
    blockers = payload.get("blockers") or []
    if isinstance(blockers, list) and blockers:
        lines.extend(["## Blockers", ""])
        for item in blockers:
            lines.append(f"- {item}")
        lines.append("")
    if result == RESULT_READY:
        lines.extend(
            [
                "READY_FOR_TAG means verification evidence is complete. It is not",
                "authorization to create a tag, merge a PR, or publish an artifact.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "BLOCKED means this candidate must not be tagged or published on the",
                "basis of this run.",
                "",
            ]
        )
    return "\n".join(lines)


def format_compact_summary(payload: dict[str, object]) -> str:
    """Operator-facing compact summary. Never an ambiguous green."""
    result = str(payload.get("result") or RESULT_BLOCKED)
    lines = [
        f"RELEASE CANDIDATE: {payload.get('version', '')}",
        f"SOURCE SHA: {payload.get('commit_sha', '')}",
        f"VERSION AUTHORITY: {payload.get('version_authority', '')}",
        f"TESTS: {payload.get('tests', '')}",
        f"WHEEL BUILD: {payload.get('wheel_build', '')}",
        f"FRESH INSTALL: {payload.get('fresh_install', '')}",
        f"PACKAGE PARITY: {payload.get('package_parity', '')}",
        f"MANIFEST: {payload.get('manifest', '')}",
        f"SHA-256: {payload.get('sha256', '')}",
        f"TAG ELIGIBILITY: {payload.get('tag_eligibility', '')}",
        "",
        f"RESULT: {result}",
    ]
    blockers = payload.get("blockers") or []
    if result != RESULT_READY and isinstance(blockers, list) and blockers:
        lines.append("BLOCKERS:")
        for item in blockers:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("FAIL evidence input is not a JSON object", file=sys.stderr)
        return 1
    text = render_evidence(payload)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    sys.stdout.write("\n")
    sys.stdout.write(format_compact_summary(payload))
    return 0 if payload.get("result") == RESULT_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
