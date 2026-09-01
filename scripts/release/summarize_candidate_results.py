#!/usr/bin/env python3
"""Aggregate release-candidate evidence from workflow artifacts.

Usage:
    python scripts/release/summarize_candidate_results.py \\
        --artifacts-dir artifacts \\
        --verify-result success

Reads ``release_evidence_*.json`` files. Does not create tags, mutate
source, or publish. Exit 0 only for READY_FOR_TAG.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.candidate_result import (  # noqa: E402
    aggregate_candidate_results,
    format_workflow_summary,
)
from scripts.release.model import RESULT_READY  # noqa: E402


def load_evidence_payloads(artifacts_dir: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    if not artifacts_dir.is_dir():
        return payloads
    for path in sorted(artifacts_dir.rglob("release_evidence_*.json")):
        if path.name.endswith(".md"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and (
            "disposition" in data or "result" in data or "verification_status" in data
        ):
            payloads.append(data)
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--verify-result", required=True)
    args = parser.parse_args()
    payloads = load_evidence_payloads(args.artifacts_dir)
    combined = aggregate_candidate_results(payloads, verify_job_result=args.verify_result)
    sys.stdout.write(format_workflow_summary(combined))
    return 0 if combined.get("disposition") == RESULT_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
