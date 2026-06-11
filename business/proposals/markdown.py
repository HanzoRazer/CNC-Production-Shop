"""Proposal Markdown export.

Dev Order: CNC-BID-CORE-4

Exports ProposalV1 records to customer-facing Markdown documents.
Does NOT expose internal margin, risk factors, or contingency calculations.
"""

from pathlib import Path

from business.proposals.models import ProposalV1

DEFAULT_EXPORTS_DIR = Path("exports/proposals")


def _render_header(
    proposal: ProposalV1,
    include_header: bool = True,
) -> str:
    """Render the proposal header block."""
    if not include_header:
        return ""

    lines = [
        "# Texas Guitar Exchange / CNC Production Shop",
        "",
        f"**Proposal ID:** {proposal.proposal_id}  ",
        f"**Project:** {proposal.project_name}  ",
        f"**Customer:** {proposal.customer_name}  ",
        f"**Revision:** {proposal.revision}  ",
        f"**Created:** {proposal.created_at}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _render_pricing_table(proposal: ProposalV1) -> str:
    """Render the pricing summary as a Markdown table."""
    lines = [
        "| Item | Value |",
        "|------|-------|",
        f"| Total Price | ${proposal.pricing.total_price:,.2f} |",
        f"| Price Per Unit | ${proposal.pricing.price_per_unit:,.2f} |",
        f"| Quantity | {proposal.pricing.quantity} units |",
    ]
    if proposal.pricing.pricing_note:
        lines.append(f"| Note | {proposal.pricing.pricing_note} |")
    return "\n".join(lines)


def _render_section(title: str, body: str, bullets: list[str]) -> str:
    """Render a proposal section."""
    lines = [f"## {title}", "", body]
    if bullets:
        lines.append("")
        for bullet in bullets:
            lines.append(f"- {bullet}")
    lines.append("")
    return "\n".join(lines)


def _render_terms(proposal: ProposalV1) -> str:
    """Render proposal terms."""
    if not proposal.terms:
        return ""

    lines = ["## Terms and Conditions", ""]
    for term in proposal.terms:
        lines.append(f"### {term.title}")
        lines.append("")
        lines.append(term.statement)
        lines.append("")
    return "\n".join(lines)


def _render_next_steps(proposal: ProposalV1) -> str:
    """Render next steps as a numbered list."""
    if not proposal.next_steps:
        return ""

    lines = ["## Next Steps", ""]
    for i, step in enumerate(proposal.next_steps, 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    return "\n".join(lines)


def _render_signature_block(include_signature: bool = True) -> str:
    """Render the signature/acceptance block."""
    if not include_signature:
        return ""

    lines = [
        "---",
        "",
        "## Acceptance",
        "",
        "By signing below, Customer accepts this proposal as presented.",
        "",
        "**Customer Name:** _________________________",
        "",
        "**Authorized Signature:** _________________________",
        "",
        "**Date:** _________________________",
        "",
        "**Printed Name:** _________________________",
        "",
    ]
    return "\n".join(lines)


def _render_notes(proposal: ProposalV1) -> str:
    """Render proposal notes if present."""
    if not proposal.notes:
        return ""

    lines = ["---", "", "*Notes:*", ""]
    for note in proposal.notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def render_proposal_markdown(
    proposal: ProposalV1,
    *,
    include_header: bool = True,
    include_signature: bool = True,
) -> str:
    """Render a ProposalV1 to Markdown string.

    Args:
        proposal: The proposal to render
        include_header: Include shop header block (default True)
        include_signature: Include signature block (default True)

    Returns:
        Markdown string suitable for customer delivery

    Notes:
        - Pure function, no filesystem side effects
        - Does not expose internal margin or risk factors
        - Uses created_at from proposal, not runtime date
    """
    parts: list[str] = []

    parts.append(_render_header(proposal, include_header))

    for section in proposal.sections:
        # Skip "Next Steps" section - we render it separately as numbered list
        if section.title == "Next Steps":
            continue
        if section.title == "Pricing Summary":
            lines = [
                f"## {section.title}",
                "",
                section.body,
                "",
                _render_pricing_table(proposal),
                "",
            ]
            parts.append("\n".join(lines))
        else:
            parts.append(_render_section(section.title, section.body, section.bullets))

    parts.append(_render_terms(proposal))
    parts.append(_render_next_steps(proposal))
    parts.append(_render_signature_block(include_signature))
    parts.append(_render_notes(proposal))

    return "\n".join(part for part in parts if part)


def export_proposal_markdown(
    proposal: ProposalV1,
    output_path: Path | None = None,
    *,
    include_header: bool = True,
    include_signature: bool = True,
) -> Path:
    """Export a ProposalV1 to a Markdown file.

    Args:
        proposal: The proposal to export
        output_path: Output file path (default: exports/proposals/{proposal_id}.md)
        include_header: Include shop header block (default True)
        include_signature: Include signature block (default True)

    Returns:
        Path to the written file

    Raises:
        OSError: If file cannot be written
    """
    if output_path is None:
        output_path = DEFAULT_EXPORTS_DIR / f"{proposal.proposal_id}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = render_proposal_markdown(
        proposal,
        include_header=include_header,
        include_signature=include_signature,
    )

    output_path.write_text(markdown, encoding="utf-8")
    return output_path
