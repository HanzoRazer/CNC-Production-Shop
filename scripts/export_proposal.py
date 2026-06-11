#!/usr/bin/env python3
"""Export a proposal JSON fixture to Markdown.

Usage:
    python scripts/export_proposal.py
    python scripts/export_proposal.py --input path/to/proposal.json
    python scripts/export_proposal.py --input proposal.json --output output.md

Default:
    Input:  fixtures/proposals/eco_loom_prototype_proposal_v1.json
    Output: exports/proposals/{proposal_id}.md

Exit codes:
    0 = success
    1 = failure
"""

import argparse
import json
import sys
from pathlib import Path

from business.proposals.markdown import export_proposal_markdown
from business.proposals.models import (
    ProposalAssumptionV1,
    ProposalPricingV1,
    ProposalSectionV1,
    ProposalTermV1,
    ProposalV1,
)

DEFAULT_INPUT = Path("fixtures/proposals/eco_loom_prototype_proposal_v1.json")


def load_proposal_from_json(path: Path) -> ProposalV1:
    """Load a ProposalV1 from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    pricing = ProposalPricingV1(
        total_price=data["pricing"]["total_price"],
        price_per_unit=data["pricing"]["price_per_unit"],
        quantity=data["pricing"]["quantity"],
        currency=data["pricing"].get("currency", "USD"),
        pricing_note=data["pricing"].get("pricing_note", ""),
    )

    sections = [
        ProposalSectionV1(
            title=s["title"],
            body=s["body"],
            bullets=s.get("bullets", []),
        )
        for s in data["sections"]
    ]

    assumptions = [
        ProposalAssumptionV1(
            statement=a["statement"],
            customer_visible=a.get("customer_visible", True),
        )
        for a in data["assumptions"]
    ]

    terms = [
        ProposalTermV1(
            title=t["title"],
            statement=t["statement"],
        )
        for t in data["terms"]
    ]

    return ProposalV1(
        proposal_id=data["proposal_id"],
        source_bid_id=data["source_bid_id"],
        project_name=data["project_name"],
        customer_name=data["customer_name"],
        revision=data["revision"],
        status=data["status"],
        created_at=data["created_at"],
        pricing=pricing,
        sections=sections,
        assumptions=assumptions,
        exclusions=data["exclusions"],
        terms=terms,
        next_steps=data["next_steps"],
        notes=data.get("notes", []),
        source_summary_ref=data.get("source_summary_ref"),
        project_ref=data.get("project_ref"),
    )


def main() -> int:
    """Export a proposal to Markdown."""
    parser = argparse.ArgumentParser(
        description="Export a proposal JSON fixture to Markdown"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input JSON file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output Markdown file (default: exports/proposals/{proposal_id}.md)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        proposal = load_proposal_from_json(args.input)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error: Failed to parse proposal: {e}", file=sys.stderr)
        return 1

    try:
        output_path = export_proposal_markdown(proposal, args.output)
        print(f"Exported: {output_path}")
        return 0
    except OSError as e:
        print(f"Error: Failed to write output: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
