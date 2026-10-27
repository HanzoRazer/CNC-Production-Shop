"""V2 bid serialization, internal report, and lineage manifest.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-002

V1 serializers stay in reporting.py. This module reuses the stable JSON writer.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from business.bids.models_v2 import BidV2
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.models_v2 import ThinSkinBuildEstimateV2
from business.workflows.models import (
    MAPPING_VERSION_V2,
    WORKFLOW_VERSION_V2,
    EstimateToBidResultV2,
    JobQuoteFailureError,
    JobQuoteRequestV2,
    SourceSnapshot,
)
from business.workflows.reporting import _jsonable, _money

_BASIS_FIELDS = (
    "direct_material_cost",
    "direct_labor_cost",
    "machine_time_cost",
    "tooling_cost",
    "setup_cost",
    "finishing_cost",
    "finishing_material_cost",
    "engineering_cost",
    "equipment_occupancy_cost",
    "process_rework_and_yield_reserve",
)

_CATEGORY_FIELDS = (
    "core_material_cost",
    "skin_material_cost",
    "adhesive_and_lamination_consumables",
    "neck_and_fretboard_cost",
    "hardware_cost",
    "electronics_cost",
    "other_consumables_cost",
    "material_scrap_allowance",
    "lamination_labor_cost",
    "direct_build_labor_cost",
    "assembly_labor_cost",
    "machine_time_cost",
    "equipment_occupancy_cost",
    "setup_and_inspection_cost",
    "finishing_labor_cost",
    "finish_material_cost",
    "process_rework_and_yield_reserve",
)


def estimate_payload_v2(estimate: ThinSkinBuildEstimateV2) -> dict[str, Any]:
    payload = _jsonable(asdict(estimate))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("estimate payload was not an object")
    return payload


def bid_payload_v2(bid: BidV2) -> dict[str, Any]:
    """Serialize BidV2, including the computed ten-field base."""
    payload = _jsonable(asdict(bid))
    if not isinstance(payload, dict):
        raise JobQuoteFailureError("bid payload was not an object")
    basis = payload["cost_basis"]
    if not isinstance(basis, dict):
        raise JobQuoteFailureError("bid cost basis payload was not an object")
    component_sum = as_money(sum(basis[field] for field in _BASIS_FIELDS))
    property_value = as_money(bid.cost_basis.base_manufacturing_cost)
    if not money_equal(component_sum, property_value):
        raise JobQuoteFailureError("bid base_manufacturing_cost does not match its component sum")
    basis["base_manufacturing_cost"] = property_value
    payload["record_type"] = "cnc_bid"
    payload["record_version"] = "2.0.0"
    if payload.get("machine_costing") is None:
        payload.pop("machine_costing", None)
    return payload


def manifest_payload_v2(
    *,
    request: JobQuoteRequestV2,
    estimate: ThinSkinBuildEstimateV2,
    mapping: EstimateToBidResultV2,
    sources: tuple[SourceSnapshot, ...],
    artifacts: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    """Build the V2 lineage manifest. The manifest file itself is not hashed here."""
    detail = mapping.detail
    return {
        "record_type": "cnc_job_quote_manifest",
        "record_version": "2.0.0",
        "status": "draft",
        "job_id": request.job_id,
        "estimate_id": request.estimate_id,
        "bid_id": request.bid_id,
        "proposal_id": request.proposal_id,
        "created_at": request.created_at,
        "effective_date": request.effective_date,
        "calculator_id": estimate.calculation.calculator_id,
        "estimate_input_contract": request.estimate_input_contract,
        "estimate_output_contract": "thin_skin_build_estimate_v2",
        "bid_contract": "bid_v2",
        "bid_summary_contract": "bid_summary_v1",
        "proposal_contract": "proposal_v1",
        "workflow_version": WORKFLOW_VERSION_V2,
        "mapping_version": MAPPING_VERSION_V2,
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
            "mapping_version": MAPPING_VERSION_V2,
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
                "equipment_record_total": detail.equipment_record_total,
                "equipment_operation_detail_total": detail.equipment_operation_detail_total,
                "equipment_detail_difference": detail.equipment_detail_difference,
                "machine_record_total": detail.machine_record_total,
                "machine_operation_detail_total": detail.machine_operation_detail_total,
                "machine_detail_difference": detail.machine_detail_difference,
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
                "description": ("Packet references resolve relative to the output packet root."),
            },
            "source_refs": {
                "base": "source_workspace",
                "snapshot_root": "internal/sources",
                "description": (
                    "Machine profile, machine cost basis, equipment profile, and "
                    "equipment cost-basis references keep their source-workspace "
                    "meaning and resolve through the packet source snapshot root. "
                    "They are not packet-root paths."
                ),
            },
        },
    }


def render_internal_cost_report_v2(
    *,
    request: JobQuoteRequestV2,
    estimate: ThinSkinBuildEstimateV2,
    mapping: EstimateToBidResultV2,
    sources: tuple[SourceSnapshot, ...],
) -> str:
    """Internal thin-skin cost report. This document is not a customer deliverable."""
    summary = estimate.cost_summary
    bid = mapping.bid
    detail = mapping.detail
    lines = [
        "# Internal job quote cost report",
        "",
        "This report is internal. It is not a customer document, a price approval, "
        "or a manufacturing release.",
        "",
        f"**Status:** {bid.status}  ",
        f"**Job ID:** {request.job_id}  ",
        f"**Estimate ID:** {estimate.estimate_id}  ",
        f"**Variant:** {estimate.variant_id}  ",
        f"**Bid ID:** {bid.bid_id}  ",
        f"**Proposal ID:** {request.proposal_id}  ",
        f"**Created:** {request.created_at}  ",
        f"**Effective date:** {request.effective_date}  ",
        f"**Contract:** {request.estimate_input_contract}  ",
        f"**Workflow:** {WORKFLOW_VERSION_V2}  ",
        f"**Mapping:** {MAPPING_VERSION_V2}  ",
        f"**Calculator:** {estimate.calculation.calculator_id}  ",
        f"**Confidence:** {estimate.provenance.confidence}",
        "",
        "## Direct manufacturing cost",
        "",
        "Seventeen source categories are listed. "
        "total_direct_manufacturing_cost is their total, not an eighteenth category.",
        "",
        "| Category | Amount |",
        "| --- | --- |",
    ]
    for field in _CATEGORY_FIELDS:
        lines.append(f"| {field} | {_money(getattr(summary, field))} |")
    lines.append(
        f"| total_direct_manufacturing_cost | {_money(summary.total_direct_manufacturing_cost)} |"
    )
    lines.extend(
        [
            "",
            "## Bid mapping",
            "",
            "Finish material stays in finishing_material_cost. "
            "Equipment occupancy and the process reserve stay in their own fields. "
            "Tooling and engineering are mapped at 0. "
            "Scrap and the process reserve are not applied again as pricing percentages.",
            "",
            "| Source category | Source amount | Bid field | Mapped amount |",
            "| --- | --- | --- | --- |",
        ]
    )
    for line in mapping.lines:
        lines.append(
            f"| {line.source_category} | {_money(line.source_amount)} | "
            f"{line.bid_field} | {_money(line.mapped_amount)} |"
        )
    lines.extend(["", "## Mapped bid amounts", ""])
    for field, amount in mapping.mapped_amounts:
        lines.append(f"- {field}: {_money(amount)}")
    lines.extend(["", "## Machine costing", ""])
    machine = bid.machine_costing
    if machine is None:
        lines.append("- Machine costing was not copied.")
    else:
        lines.extend(
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
    lines.extend(["", "## Equipment occupancy", ""])
    if not bid.equipment_costing:
        lines.append("- No equipment records were copied.")
    for equipment in bid.equipment_costing:
        lines.extend(
            [
                f"- Equipment: {equipment.equipment_id}",
                f"  - Profile ref: {equipment.equipment_profile_ref}",
                f"  - Cost basis: {equipment.cost_basis_id}",
                f"  - Cost basis ref: {equipment.cost_basis_ref}",
                f"  - Occupancy minutes: {equipment.occupancy_minutes}",
                f"  - Equipment hour rate: {_money(equipment.equipment_hour_rate)}",
                f"  - Derived occupancy cost: {_money(equipment.derived_occupancy_cost)}",
                f"  - Derivation: {equipment.derivation}",
                f"  - Provenance status: {equipment.provenance_status}",
            ]
        )
    lines.extend(
        [
            "",
            "## Detail reconciliation",
            "",
            "Equipment records and per-operation amounts may round at different stages. "
            "The difference is reported and is not added to the bid.",
            "",
            f"- Equipment record total: {_money(detail.equipment_record_total)}",
            "- Equipment operation detail total: "
            f"{_money(detail.equipment_operation_detail_total)}",
            f"- Equipment detail difference: {_money(detail.equipment_detail_difference)}",
            f"- Machine record total: {_money(detail.machine_record_total)}",
            f"- Machine operation detail total: {_money(detail.machine_operation_detail_total)}",
            f"- Machine detail difference: {_money(detail.machine_detail_difference)}",
            "",
            "## Time summary",
            "",
            f"- Operator labor minutes: {estimate.time_summary.total_labor_minutes}",
            f"- CNC runtime minutes: {estimate.time_summary.total_machine_runtime_minutes}",
            "- Equipment occupancy minutes: "
            f"{estimate.time_summary.total_equipment_occupancy_minutes}",
            f"- Elapsed wait minutes: {estimate.time_summary.total_elapsed_wait_minutes}",
            f"- Rework minutes: {estimate.time_summary.total_rework_minutes}",
            "",
            "## Risk basis",
            "",
            f"- Material scrap rate: {estimate.risk_basis.material_scrap_rate}",
            f"- Material scrap base: {_money(estimate.risk_basis.material_scrap_base)}",
            f"- Process reserve rate: {estimate.risk_basis.process_reserve_rate}",
            f"- Process reserve base: {_money(estimate.risk_basis.process_reserve_base)}",
            f"- Compounding: {estimate.risk_basis.compounding}",
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
    lines.extend(["", "## Estimate notes", ""])
    if estimate.notes:
        for note in estimate.notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None.")
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
