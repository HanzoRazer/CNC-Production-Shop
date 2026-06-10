"""Proposal generator from bid summaries.

Dev Order: CNC-BID-CORE-3

Generates customer-facing proposals from internal BidSummaryV1 records.
Does NOT expose internal margin, risk factors, or contingency calculations.
"""

import re
from datetime import UTC, datetime

from business.bids.summary import BidSummaryV1
from business.proposals.models import (
    ProposalAssumptionV1,
    ProposalPricingV1,
    ProposalSectionV1,
    ProposalTermV1,
    ProposalV1,
)


def _derive_project_slug(project_name: str) -> str:
    """Derive a short slug from project name for proposal ID."""
    words = re.sub(r"[^a-zA-Z0-9\s]", "", project_name).upper().split()
    if not words:
        return "PROJ"
    if len(words) == 1:
        return words[0][:8]
    return "".join(w[0] for w in words[:4])


def _generate_proposal_id(project_name: str) -> str:
    """Generate a proposal ID from project name."""
    slug = _derive_project_slug(project_name)
    year = datetime.now(UTC).year
    return f"PROP-{slug}-{year}-001"


def _create_executive_summary(summary: BidSummaryV1) -> ProposalSectionV1:
    """Create executive summary section."""
    body = (
        f"Texas Guitar Exchange is pleased to provide this manufacturing proposal "
        f"for the {summary.project_name} project. This proposal is based on the "
        f"current governed bid summary and is intended for customer review."
    )
    return ProposalSectionV1(
        title="Executive Summary",
        body=body,
        bullets=[],
    )


def _create_project_scope(summary: BidSummaryV1) -> ProposalSectionV1:
    """Create project scope section from line items."""
    body = (
        f"This proposal covers manufacturing of {summary.quantity} units "
        f"as specified in the current design documentation."
    )

    categories = set()
    for item in summary.line_items:
        categories.add(item.category)

    bullets = []
    if "machine" in categories:
        bullets.append("CNC machining operations")
    if "labor" in categories:
        bullets.append("Setup, finishing, and inspection labor")
    if "materials" in categories:
        bullets.append("Finishing materials and consumables")

    if not bullets:
        bullets = ["Manufacturing per specification"]

    return ProposalSectionV1(
        title="Project Scope",
        body=body,
        bullets=bullets,
    )


def _create_deliverables(summary: BidSummaryV1) -> ProposalSectionV1:
    """Create deliverables section."""
    body = "Upon completion, the following will be delivered:"
    bullets = [
        f"{summary.quantity} completed units per specification",
        "Final inspection documentation",
        "Packaging for safe transport",
    ]
    return ProposalSectionV1(
        title="Deliverables",
        body=body,
        bullets=bullets,
    )


def _create_pricing_summary(
    summary: BidSummaryV1, total_price: float, price_per_unit: float
) -> ProposalSectionV1:
    """Create pricing summary section."""
    body = "Pricing is based on the current design revision and stated quantity."
    bullets = [
        f"Total Price: ${total_price:,.2f}",
        f"Price Per Unit: ${price_per_unit:,.2f}",
        f"Quantity: {summary.quantity} units",
    ]
    return ProposalSectionV1(
        title="Pricing Summary",
        body=body,
        bullets=bullets,
    )


def _create_assumptions_section(
    assumptions: list[ProposalAssumptionV1],
) -> ProposalSectionV1:
    """Create assumptions section."""
    body = "This proposal is based on the following assumptions:"
    bullets = [a.statement for a in assumptions if a.customer_visible]
    return ProposalSectionV1(
        title="Assumptions",
        body=body,
        bullets=bullets,
    )


def _create_exclusions_section(exclusions: list[str]) -> ProposalSectionV1:
    """Create exclusions section."""
    body = "The following are not included in this proposal:"
    return ProposalSectionV1(
        title="Exclusions",
        body=body,
        bullets=exclusions,
    )


def _create_next_steps_section(next_steps: list[str]) -> ProposalSectionV1:
    """Create next steps section."""
    body = "To proceed with this project:"
    return ProposalSectionV1(
        title="Next Steps",
        body=body,
        bullets=next_steps,
    )


def _sanitize_assumptions(summary: BidSummaryV1) -> list[ProposalAssumptionV1]:
    """Convert internal assumptions to customer-safe wording."""
    sanitized = []

    sanitized.append(
        ProposalAssumptionV1(
            statement="Pricing is based on the current design revision.",
            customer_visible=True,
        )
    )
    sanitized.append(
        ProposalAssumptionV1(
            statement=(
                f"Pricing assumes the stated production quantity of "
                f"{summary.quantity} units."
            ),
            customer_visible=True,
        )
    )
    sanitized.append(
        ProposalAssumptionV1(
            statement="Material, finish, and schedule changes may require pricing revision.",
            customer_visible=True,
        )
    )

    for assumption in summary.assumptions:
        if assumption.field == "material_supply":
            if assumption.value == "customer-supplied":
                sanitized.append(
                    ProposalAssumptionV1(
                        statement="Customer will supply raw materials as agreed.",
                        customer_visible=True,
                    )
                )
            else:
                sanitized.append(
                    ProposalAssumptionV1(
                        statement="Shop will source materials per specification.",
                        customer_visible=True,
                    )
                )
        elif assumption.field == "delivery_date" and assumption.value:
            sanitized.append(
                ProposalAssumptionV1(
                    statement=f"Target delivery date: {assumption.value}.",
                    customer_visible=True,
                )
            )

    return sanitized


def _default_exclusions() -> list[str]:
    """Return default proposal exclusions."""
    return [
        "Shipping and freight charges",
        "Sales tax and duties",
        "Specialty packaging beyond standard",
        "Design revisions after approval",
        "Material substitutions",
        "Rush scheduling premiums",
    ]


def _default_terms() -> list[ProposalTermV1]:
    """Return default proposal terms."""
    return [
        ProposalTermV1(
            title="Proposal Validity",
            statement=(
                "This proposal is valid for review only while stated "
                "assumptions remain unchanged."
            ),
        ),
        ProposalTermV1(
            title="Revisions",
            statement="Design or quantity changes may require proposal revision.",
        ),
        ProposalTermV1(
            title="Scheduling",
            statement="Production scheduling begins after approval and material confirmation.",
        ),
    ]


def _default_next_steps() -> list[str]:
    """Return default next steps."""
    return [
        "Review proposal and confirm requirements",
        "Approve proposal to proceed",
        "Confirm material availability and delivery schedule",
        "Production begins upon approval",
    ]


def generate_proposal_from_summary(
    summary: BidSummaryV1,
    *,
    source_summary_ref: str | None = None,
    project_ref: str | None = None,
) -> ProposalV1:
    """Generate a customer-facing proposal from a BidSummaryV1.

    Args:
        summary: The internal bid summary to convert
        source_summary_ref: Optional path to source summary fixture
        project_ref: Optional path to project capture

    Returns:
        ProposalV1 suitable for customer review

    Notes:
        - Does not mutate input summary
        - Uses rounded pricing when present, otherwise canonical
        - Does not expose risk_factors or target_margin_pct
        - Creates conservative customer-safe prose
    """
    total_price = (
        summary.rounded_quote_price
        if summary.rounded_quote_price is not None
        else summary.canonical_quote_price
    )
    price_per_unit = (
        summary.rounded_price_per_unit
        if summary.rounded_price_per_unit is not None
        else summary.canonical_price_per_unit
    )

    pricing = ProposalPricingV1(
        total_price=total_price,
        price_per_unit=price_per_unit,
        quantity=summary.quantity,
        currency="USD",
        pricing_note="",
    )

    assumptions = _sanitize_assumptions(summary)
    exclusions = _default_exclusions()
    terms = _default_terms()
    next_steps = _default_next_steps()

    sections = [
        _create_executive_summary(summary),
        _create_project_scope(summary),
        _create_deliverables(summary),
        _create_pricing_summary(summary, total_price, price_per_unit),
        _create_assumptions_section(assumptions),
        _create_exclusions_section(exclusions),
        _create_next_steps_section(next_steps),
    ]

    proposal_id = _generate_proposal_id(summary.project_name)
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return ProposalV1(
        proposal_id=proposal_id,
        source_bid_id=summary.bid_id,
        project_name=summary.project_name,
        customer_name=summary.customer_name,
        revision=summary.revision,
        status=summary.status,
        created_at=created_at,
        pricing=pricing,
        sections=sections,
        assumptions=assumptions,
        exclusions=exclusions,
        terms=terms,
        next_steps=next_steps,
        notes=list(summary.notes),
        source_summary_ref=source_summary_ref,
        project_ref=project_ref,
    )
