"""Customer-facing proposal generation.

Dev Order: CNC-BID-CORE-3
"""

from business.proposals.generator import generate_proposal_from_summary
from business.proposals.models import (
    ProposalAssumptionV1,
    ProposalPricingV1,
    ProposalSectionV1,
    ProposalStatus,
    ProposalTermV1,
    ProposalV1,
)

__all__ = [
    "ProposalAssumptionV1",
    "ProposalPricingV1",
    "ProposalSectionV1",
    "ProposalStatus",
    "ProposalTermV1",
    "ProposalV1",
    "generate_proposal_from_summary",
]
