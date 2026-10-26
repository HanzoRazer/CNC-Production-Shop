"""Stable serializers, internal reporting, and atomic packet publication.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-001
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from business.bids.models import BidV1
from business.bids.summary import BidSummaryV1
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.models import GuitarBuildEstimateV1
from business.proposals.markdown import render_proposal_markdown
from business.proposals.models import ProposalV1
from business.workflows.models import (
    DRAFT_FOR_REVIEW_NOTICE,
    MAPPING_VERSION,
    WORKFLOW_VERSION,
    EstimateToBidResult,
    JobQuoteFailureError,
    JobQuoteRefusalError,
    JobQuoteRequestV1,
    SourceSnapshot,
)


def dumps_json(payload: object) -> bytes:
    """Serialize JSON as UTF-8, sorted keys, two-space indent, and a trailing newline."""
    try:
        text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise JobQuoteFailureError("workflow JSON could not be serialized") from exc
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def estimate_payload(estimate: GuitarBuildEstimateV1) -> dict[str, Any]:
    payload = _jsonable(asdict(estimate))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("estimate payload was not an object")
    return payload


def bid_payload(bid: BidV1) -> dict[str, Any]:
    """Serialize BidV1, including the computed base_manufacturing_cost property."""
    payload = _jsonable(asdict(bid))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("bid payload was not an object")
    basis = payload["cost_basis"]
    if not isinstance(basis, dict):
        raise JobQuoteFailureError("bid cost basis payload was not an object")
    component_sum = as_money(
        basis["direct_material_cost"]
        + basis["direct_labor_cost"]
        + basis["machine_time_cost"]
        + basis["tooling_cost"]
        + basis["setup_cost"]
        + basis["finishing_cost"]
        + basis["finishing_material_cost"]
        + basis["engineering_cost"]
    )
    property_value = as_money(bid.cost_basis.base_manufacturing_cost)
    if not money_equal(component_sum, property_value):
        raise JobQuoteFailureError("bid base_manufacturing_cost does not match its component sum")
    basis["base_manufacturing_cost"] = property_value
    return payload


def summary_payload(summary: BidSummaryV1) -> dict[str, Any]:
    payload = _jsonable(asdict(summary))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("bid summary payload was not an object")
    payload["base_manufacturing_cost"] = as_money(summary.base_manufacturing_cost)
    return payload


def proposal_payload(proposal: ProposalV1) -> dict[str, Any]:
    payload = _jsonable(asdict(proposal))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("proposal payload was not an object")
    return payload


def render_customer_draft_markdown(proposal: ProposalV1) -> str:
    """Render the customer draft with a review notice and no signature block."""
    body = render_proposal_markdown(
        proposal,
        include_header=True,
        include_signature=False,
    )
    text = f"> **{DRAFT_FOR_REVIEW_NOTICE}**\n\n{body}"
    if not text.endswith("\n"):
        text += "\n"
    return text


def _money(value: float) -> str:
    return f"{as_money(value):.2f}"


def render_internal_cost_report(
    *,
    request: JobQuoteRequestV1,
    estimate: GuitarBuildEstimateV1,
    mapping: EstimateToBidResult,
    sources: tuple[SourceSnapshot, ...],
) -> str:
    """Internal cost report. This document is not a customer deliverable."""
    summary = estimate.cost_summary
    bid = mapping.bid
    lines = [
        "# Internal job quote cost report",
        "",
        "This report is internal. It is not a customer document, a price approval, "
        "or a manufacturing release.",
        "",
        f"**Status:** {bid.status}  ",
        f"**Job ID:** {request.job_id}  ",
        f"**Estimate ID:** {estimate.estimate_id}  ",
        f"**Bid ID:** {bid.bid_id}  ",
        f"**Proposal ID:** {request.proposal_id}  ",
        f"**Created:** {request.created_at}  ",
        f"**Effective date:** {request.effective_date}  ",
        f"**Contract:** {request.estimate_input_contract}  ",
        f"**Workflow:** {WORKFLOW_VERSION}  ",
        f"**Mapping:** {MAPPING_VERSION}  ",
        f"**Calculator:** {estimate.calculation.calculator_id}",
        "",
        "## Direct manufacturing cost",
        "",
        "| Category | Amount |",
        "| --- | --- |",
        f"| wood_material_cost | {_money(summary.wood_material_cost)} |",
        f"| hardware_cost | {_money(summary.hardware_cost)} |",
        f"| electronics_cost | {_money(summary.electronics_cost)} |",
        f"| consumables_cost | {_money(summary.consumables_cost)} |",
        f"| scrap_allowance | {_money(summary.scrap_allowance)} |",
        f"| direct_labor_cost | {_money(summary.direct_labor_cost)} |",
        f"| machine_time_cost | {_money(summary.machine_time_cost)} |",
        f"| inspection_and_setup_cost | {_money(summary.inspection_and_setup_cost)} |",
        f"| finishing_cost | {_money(summary.finishing_cost)} |",
        f"| total_direct_manufacturing_cost | {_money(summary.total_direct_manufacturing_cost)} |",
        "",
        "## Bid mapping",
        "",
        "Setup cost is labelled setup and inspection. Tooling, finishing materials, "
        "and engineering are mapped at 0. Tool wear stays inside the technical "
        "machine rate. Scrap is the estimate scrap allowance and is not added again.",
        "",
        "| Source category | Source amount | Bid field | Mapped amount |",
        "| --- | --- | --- | --- |",
    ]
    for line in mapping.lines:
        lines.append(
            f"| {line.source_category} | {_money(line.source_amount)} | "
            f"{line.bid_field} | {_money(line.mapped_amount)} |"
        )
    lines.extend(
        [
            "",
            "## Mapped bid amounts",
            "",
        ]
    )
    for field, amount in mapping.mapped_amounts:
        lines.append(f"- {field}: {_money(amount)}")
    machine = bid.machine_costing
    machine_lines = ["", "## Machine costing", ""]
    if machine is None:
        machine_lines.append("- Machine costing was not copied.")
    else:
        machine_lines.extend(
            [
                f"- Machine: {machine.machine_id}",
                f"- Profile ref: {machine.machine_profile_ref}",
                f"- Cost basis: {machine.cost_basis_id}",
                f"- Cost basis ref: {machine.cost_basis_ref}",
                f"- Runtime minutes: {machine.runtime_minutes}",
                f"- Machine hour rate: {_money(machine.machine_hour_rate)}",
                f"- Derived machine time cost: {_money(machine.derived_machine_time_cost)}",
                f"- Derivation: {machine.derivation}",
                f"- Provenance status: {machine.provenance_status}",
            ]
        )
    lines.extend(machine_lines)
    lines.extend(
        [
            "",
            "## Pricing",
            "",
            "- Basis: direct_manufacturing_cost_only",
            "- tool_wear_pct: 0",
            "- manufacturing_contingency_pct: 0",
            "- business_overhead_pct: 0",
            "- engineering_recovery_pct: 0",
            f"- Risked cost: {_money(bid.pricing.risked_cost)}",
            f"- Target margin pct: {bid.pricing.target_margin_pct}",
            f"- Quote price: {_money(bid.pricing.quote_price)}",
            f"- Price per unit: {_money(bid.pricing.price_per_unit)}",
            f"- Quantity: {bid.pricing.quantity}",
            f"- Currency: {estimate.currency}",
            f"- Rounding difference: {_money(mapping.difference)}",
            "",
            "## Audit lines",
            "",
        ]
    )
    for item in bid.line_items:
        lines.append(
            f"- {item.name} ({item.category}): quantity {item.quantity:g} "
            f"unit_cost {_money(item.unit_cost)} total_cost {_money(item.total_cost)}"
        )
    lines.extend(["", "## Bid notes", ""])
    for note in bid.notes:
        lines.append(f"- {note}")
    lines.extend(["", "## Internal notes", ""])
    if request.internal_notes:
        for note in request.internal_notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Sources", ""])
    for source in sources:
        lines.append(
            f"- {source.role}: {source.original_ref} "
            f"snapshot {source.snapshot_ref} sha256 {source.sha256} "
            f"record {source.record_id}"
        )
    lines.append("")
    return "\n".join(lines)


def manifest_payload(
    *,
    request: JobQuoteRequestV1,
    estimate: GuitarBuildEstimateV1,
    mapping: EstimateToBidResult,
    sources: tuple[SourceSnapshot, ...],
    artifacts: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    """Build the lineage manifest. The manifest file itself is not hashed here."""
    return {
        "record_type": "cnc_job_quote_manifest",
        "record_version": "1.0.0",
        "status": "draft",
        "job_id": request.job_id,
        "estimate_id": request.estimate_id,
        "bid_id": request.bid_id,
        "proposal_id": request.proposal_id,
        "created_at": request.created_at,
        "effective_date": request.effective_date,
        "calculator_id": estimate.calculation.calculator_id,
        "estimate_input_contract": request.estimate_input_contract,
        "workflow_version": WORKFLOW_VERSION,
        "mapping_version": MAPPING_VERSION,
        "pricing_policy": {
            "policy_id": request.pricing_policy.policy_id,
            "policy_version": request.pricing_policy.policy_version,
            "target_margin_pct": request.pricing_policy.target_margin_pct,
        },
        "sources": [
            {
                "role": source.role,
                "record_id": source.record_id,
                "original_ref": source.original_ref,
                "snapshot_ref": source.snapshot_ref,
                "sha256": source.sha256,
            }
            for source in sources
        ],
        "artifacts": list(artifacts),
        "category_mapping": {
            "mapping_version": MAPPING_VERSION,
            "lines": [
                {
                    "source_category": line.source_category,
                    "source_amount": line.source_amount,
                    "bid_field": line.bid_field,
                    "mapped_amount": line.mapped_amount,
                }
                for line in mapping.lines
            ],
            "mapped_amounts": {field: amount for field, amount in mapping.mapped_amounts},
            "rounding_reconciliation": {
                "policy": estimate.calculation.rounding_policy,
                "estimate_total_direct_manufacturing_cost": mapping.estimate_total,
                "mapped_category_total": mapping.mapped_total,
                "audit_line_total": mapping.audit_total,
                "base_manufacturing_cost": as_money(mapping.bid.cost_basis.base_manufacturing_cost),
                "difference": mapping.difference,
            },
        },
        "cost_basis_disclosure": {
            "basis": "direct_manufacturing_cost_only",
            "tool_wear_pct": 0,
            "manufacturing_contingency_pct": 0,
            "business_overhead_pct": 0,
            "engineering_recovery_pct": 0,
        },
        "reference_namespaces": {
            "packet_refs": {
                "base": "packet_root",
                "manufacturing_ref": mapping.bid.manufacturing_ref,
                "description": (
                    "Packet references resolve relative to the output packet root."
                ),
            },
            "source_refs": {
                "base": "source_workspace",
                "snapshot_root": "internal/sources",
                "description": (
                    "Machine profile and cost-basis references keep their "
                    "source-workspace meaning and resolve through the packet "
                    "source snapshot root. They are not packet-root paths."
                ),
            },
        },
    }


def _safe_relative(relative: str) -> Path:
    if not relative or relative.startswith("/") or "\\" in relative:
        raise JobQuoteFailureError(f"refusing to publish unsafe path: {relative}")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise JobQuoteFailureError(f"refusing to publish unsafe path: {relative}")
    return Path(*parts)


def publish_packet(output_dir: Path, files: dict[str, bytes]) -> None:
    """Stage the packet beside its destination and publish it only when complete."""
    if output_dir.is_symlink() or output_dir.exists():
        raise JobQuoteRefusalError("output directory already exists")
    parent = output_dir.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise JobQuoteFailureError(f"could not prepare the output directory: {exc}") from exc
    try:
        staging_name = tempfile.mkdtemp(prefix=".job-quote-", dir=parent)
    except OSError as exc:
        raise JobQuoteFailureError(f"could not stage the packet: {exc}") from exc
    staging = Path(staging_name)
    published = False
    try:
        for relative, raw in files.items():
            destination = staging / _safe_relative(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        if output_dir.is_symlink() or output_dir.exists():
            raise JobQuoteRefusalError("output directory already exists")
        os.rename(staging, output_dir)
        published = True
    except JobQuoteRefusalError:
        raise
    except OSError as exc:
        raise JobQuoteFailureError(f"could not publish packet: {exc}") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)

