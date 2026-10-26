"""Orchestrate a draft job quote without adding cost math.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-001
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from business.bids.generator import generate_bid_summary
from business.bids.summary import BidSummaryV1
from business.calculators.machine_cost_basis import as_money, money_equal
from business.estimates.guitar import CALCULATOR_ID, calculate_guitar_build_estimate
from business.estimates.loading import load_guitar_estimate_input
from business.estimates.models import GuitarBuildEstimateV1
from business.proposals.generator import generate_proposal_from_summary
from business.proposals.models import ProposalSectionV1, ProposalTermV1, ProposalV1
from business.workflows.estimate_to_bid import build_bid_from_estimate
from business.workflows.loading import (
    load_job_quote,
    parse_json_object,
    resolve_output_dir,
    resolve_workspace,
    validate_instance,
)
from business.workflows.models import (
    DEFAULT_PACKAGING_PROMISE,
    DRAFT_FOR_REVIEW_NOTICE,
    DRAFT_STATUS,
    PACKET_MANUFACTURING_REF,
    SOURCE_SNAPSHOT_ROOT,
    EstimateToBidResult,
    JobQuoteFailureError,
    JobQuotePacket,
    JobQuoteRefusalError,
    JobQuoteRequestV1,
    JobQuoteResult,
    LoadedJobQuote,
    SourceSnapshot,
)
from business.workflows.reporting import (
    bid_payload,
    dumps_json,
    estimate_payload,
    manifest_payload,
    proposal_payload,
    publish_packet,
    render_customer_draft_markdown,
    render_internal_cost_report,
    summary_payload,
)

_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "target_margin_pct",
        "risked_cost",
        "base_manufacturing_cost",
        "machine_hour_rate",
        "machine_costing",
        "cost_basis",
        "tool_wear_pct",
        "manufacturing_contingency_pct",
        "business_overhead_pct",
        "engineering_recovery_pct",
        "direct_material_cost",
        "direct_labor_cost",
        "machine_time_cost",
        "internal_notes",
        "line_items",
        "risk_factors",
        "wood_material_cost",
        "hardware_cost",
        "electronics_cost",
        "consumables_cost",
        "scrap_allowance",
        "inspection_and_setup_cost",
        "finishing_cost",
        "tooling_cost",
        "setup_cost",
        "finishing_material_cost",
        "engineering_cost",
    }
)

_ARTIFACTS = (
    ("internal/job_request.json", "job_request", "internal"),
    ("internal/estimate.json", "estimate", "internal"),
    ("internal/bid.json", "bid", "internal"),
    ("internal/bid_summary.json", "bid_summary", "internal"),
    ("internal/cost_report.md", "cost_report", "internal"),
    ("customer/proposal.json", "proposal_json", "customer"),
    ("customer/proposal.md", "proposal_markdown", "customer"),
)

_DRAFT_NEXT_STEPS = (
    "Review this draft and request any corrections to scope or assumptions.",
    "Obtain separate price approval before making a customer commitment.",
    "Obtain a separate manufacturing release before scheduling or starting production.",
)


def _section(proposal: ProposalV1, title: str) -> ProposalSectionV1:
    for section in proposal.sections:
        if section.title == title:
            return section
    raise JobQuoteFailureError(f"proposal is missing the {title} section")


def _replace_public_sections(
    proposal: ProposalV1,
    request: JobQuoteRequestV1,
) -> None:
    deliverables = list(request.customer_deliverables)
    exclusions = list(request.customer_exclusions)
    updated: list[ProposalSectionV1] = []
    saw_deliverables = False
    saw_exclusions = False
    saw_next_steps = False
    for section in proposal.sections:
        if section.title == "Deliverables":
            saw_deliverables = True
            updated.append(
                ProposalSectionV1(
                    title="Deliverables",
                    body="The following items are included in this draft proposal:",
                    bullets=deliverables,
                )
            )
        elif section.title == "Exclusions":
            saw_exclusions = True
            updated.append(
                ProposalSectionV1(
                    title="Exclusions",
                    body="The following are not included in this proposal:",
                    bullets=exclusions,
                )
            )
        elif section.title == "Next Steps":
            saw_next_steps = True
            updated.append(
                ProposalSectionV1(
                    title="Next Steps",
                    body=(
                        "This draft supports review only. "
                        "No approval or release is recorded here."
                    ),
                    bullets=list(_DRAFT_NEXT_STEPS),
                )
            )
        else:
            updated.append(section)
    if not saw_deliverables or not saw_exclusions or not saw_next_steps:
        raise JobQuoteFailureError("proposal generator did not emit the required public sections")
    proposal.sections = updated
    proposal.exclusions = exclusions
    proposal.next_steps = list(_DRAFT_NEXT_STEPS)
    proposal.terms = [
        ProposalTermV1(
            title=term.title,
            statement=(
                "This draft does not schedule production. "
                "Scheduling requires a separate manufacturing release."
            ),
        ) if term.title == "Scheduling" else term
        for term in proposal.terms
    ]


def project_public_proposal(
    summary: BidSummaryV1,
    request: JobQuoteRequestV1,
) -> ProposalV1:
    """Build a customer draft from prices only. Internal notes and assumptions stay off it."""
    public = BidSummaryV1(
        bid_id=summary.bid_id,
        project_name=summary.project_name,
        customer_name=summary.customer_name,
        revision=summary.revision,
        status=DRAFT_STATUS,
        quantity=summary.quantity,
        canonical_quote_price=summary.canonical_quote_price,
        canonical_price_per_unit=summary.canonical_price_per_unit,
        base_manufacturing_cost=summary.base_manufacturing_cost,
        risked_cost=summary.risked_cost,
        target_margin_pct=summary.target_margin_pct,
        line_items=[],
        risk_factors=[],
        assumptions=[],
        notes=[],
        rounded_quote_price=None,
        rounded_price_per_unit=None,
    )
    proposal = generate_proposal_from_summary(
        public,
        proposal_id=request.proposal_id,
        created_at=request.created_at,
    )
    proposal.status = DRAFT_STATUS
    proposal.notes = [DRAFT_FOR_REVIEW_NOTICE]
    proposal.source_summary_ref = None
    proposal.project_ref = None
    _replace_public_sections(proposal, request)
    return proposal


def _forbid_public_keys(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_PUBLIC_KEYS:
                raise JobQuoteFailureError(f"public proposal contains internal field {path}.{key}")
            _forbid_public_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbid_public_keys(item, f"{path}[{index}]")


def _assert_private_text_stays_internal(
    customer_text: str,
    *,
    request: JobQuoteRequestV1,
    estimate: GuitarBuildEstimateV1,
    mapping: EstimateToBidResult,
    sources: tuple[SourceSnapshot, ...],
) -> None:
    public_text = "\n".join(
        (
            request.project_name,
            request.customer_name,
            request.revision,
            *request.customer_deliverables,
            *request.customer_exclusions,
        )
    )
    private_values = [
        *request.internal_notes,
        *mapping.bid.notes,
        *estimate.notes,
        *(item.note for item in mapping.bid.line_items),
    ]
    for private in private_values:
        if private and private not in public_text and private in customer_text:
            raise JobQuoteFailureError("internal text was copied into the customer draft")
    for source in sources:
        if source.original_ref and source.original_ref in customer_text:
            raise JobQuoteFailureError("a source path was copied into the customer draft")


def _assert_public_projection(
    proposal: ProposalV1,
    markdown: str,
    *,
    request: JobQuoteRequestV1,
    estimate: GuitarBuildEstimateV1,
    mapping: EstimateToBidResult,
    sources: tuple[SourceSnapshot, ...],
) -> None:
    if proposal.status != DRAFT_STATUS:
        raise JobQuoteFailureError("proposal status must remain draft")
    if proposal.proposal_id != request.proposal_id or proposal.source_bid_id != request.bid_id:
        raise JobQuoteFailureError("proposal identity does not match the job request")
    if proposal.created_at != request.created_at:
        raise JobQuoteFailureError("proposal created_at does not match the job request")
    if proposal.source_summary_ref is not None or proposal.project_ref is not None:
        raise JobQuoteFailureError("public proposal must not carry source or project refs")
    if proposal.notes != [DRAFT_FOR_REVIEW_NOTICE]:
        raise JobQuoteFailureError("public proposal notes must be only the draft-for-review notice")
    if proposal.exclusions != list(request.customer_exclusions):
        raise JobQuoteFailureError("proposal exclusions do not match the job request")
    deliverables = _section(proposal, "Deliverables")
    exclusions = _section(proposal, "Exclusions")
    if deliverables.bullets != list(request.customer_deliverables):
        raise JobQuoteFailureError("proposal deliverables do not match the job request")
    if exclusions.bullets != list(request.customer_exclusions):
        raise JobQuoteFailureError("proposal exclusion section does not match the job request")
    if proposal.next_steps != list(_DRAFT_NEXT_STEPS):
        raise JobQuoteFailureError("proposal next steps must require separate approval and release")
    if _section(proposal, "Next Steps").bullets != proposal.next_steps:
        raise JobQuoteFailureError("proposal next steps section does not match its review steps")
    if proposal.pricing.quantity != 1 or proposal.pricing.currency != "USD":
        raise JobQuoteFailureError("public pricing must stay quantity 1 and currency USD")
    if not money_equal(proposal.pricing.total_price, mapping.bid.pricing.quote_price):
        raise JobQuoteFailureError("proposal price does not match the bid")
    if not money_equal(proposal.pricing.price_per_unit, proposal.pricing.total_price):
        raise JobQuoteFailureError("quantity 1 requires price_per_unit to equal the quote price")
    payload = proposal_payload(proposal)
    _forbid_public_keys(payload)
    rendered = markdown
    if "Authorized Signature" in rendered:
        raise JobQuoteFailureError("customer draft must not include a signature block")
    if DRAFT_FOR_REVIEW_NOTICE not in rendered:
        raise JobQuoteFailureError("customer draft is missing the draft-for-review notice")
    promised = DEFAULT_PACKAGING_PROMISE in rendered or any(
        DEFAULT_PACKAGING_PROMISE in bullet for bullet in deliverables.bullets
    )
    requested = any(DEFAULT_PACKAGING_PROMISE in item for item in request.customer_deliverables)
    if promised and not requested:
        raise JobQuoteFailureError("customer draft inherited the uncosted packaging promise")
    customer_json = dumps_json(payload).decode("utf-8")
    _assert_private_text_stays_internal(
        customer_json + "\n" + rendered,
        request=request,
        estimate=estimate,
        mapping=mapping,
        sources=sources,
    )


def _assert_links(
    *,
    request: JobQuoteRequestV1,
    estimate: GuitarBuildEstimateV1,
    input_confidence: str,
    mapping: EstimateToBidResult,
    summary: BidSummaryV1,
) -> None:
    bid = mapping.bid
    if estimate.estimate_id != request.estimate_id:
        raise JobQuoteFailureError("estimate identity does not match the job request")
    if estimate.estimate_input_ref != request.estimate_input_ref:
        raise JobQuoteFailureError("estimate input ref does not match the job request")
    if estimate.calculation.effective_date != request.effective_date:
        raise JobQuoteFailureError("estimate effective_date does not match the request timestamp")
    if estimate.calculation.calculator_id != CALCULATOR_ID:
        raise JobQuoteFailureError("estimate calculator identity changed")
    statuses = (estimate.status, bid.status, summary.status)
    if any(status != DRAFT_STATUS for status in statuses):
        raise JobQuoteFailureError("economic outputs must remain draft")
    if estimate.provenance.confidence != input_confidence:
        raise JobQuoteFailureError("workflow changed estimate confidence")
    if estimate.quantity != 1 or estimate.currency != "USD":
        raise JobQuoteFailureError("calculated estimate left the supported quantity or currency")
    if bid.bid_id != request.bid_id or summary.bid_id != request.bid_id:
        raise JobQuoteFailureError("bid identity does not match the job request")
    if bid.manufacturing_ref != PACKET_MANUFACTURING_REF:
        raise JobQuoteFailureError("bid manufacturing_ref is not the packet estimate reference")
    if bid.project_ref is not None or bid.scenario_ref is not None:
        raise JobQuoteFailureError("bid must not invent project or scenario refs")
    if bid.machine_costing is None:
        raise JobQuoteFailureError("bid is missing the copied machine costing")
    if not money_equal(
        bid.machine_costing.derived_machine_time_cost,
        bid.cost_basis.machine_time_cost,
    ):
        raise JobQuoteFailureError("copied machine costing does not equal bid machine_time_cost")
    if not money_equal(
        bid.machine_costing.derived_machine_time_cost,
        estimate.machine_costing.derived_machine_time_cost,
    ):
        raise JobQuoteFailureError("bid machine costing does not match the estimate")
    base = as_money(bid.cost_basis.base_manufacturing_cost)
    if not money_equal(base, estimate.cost_summary.total_direct_manufacturing_cost):
        raise JobQuoteFailureError("bid base does not equal the estimate total")
    if not money_equal(base, mapping.mapped_total) or not money_equal(base, mapping.audit_total):
        raise JobQuoteFailureError("category mapping does not reconcile")
    if mapping.difference != 0:
        raise JobQuoteFailureError("rounding reconciliation was not zero")
    pricing = bid.pricing
    if (
        pricing.tool_wear_pct != 0
        or pricing.manufacturing_contingency_pct != 0
        or pricing.business_overhead_pct != 0
        or pricing.engineering_recovery_pct != 0
    ):
        raise JobQuoteFailureError("additional pricing percentages must stay zero")
    if not money_equal(pricing.risked_cost, base):
        raise JobQuoteFailureError("risked cost changed with zero additional percentages")
    if pricing.quantity != 1 or not money_equal(pricing.price_per_unit, pricing.quote_price):
        raise JobQuoteFailureError("quantity 1 pricing did not stay consistent")
    if float(pricing.target_margin_pct) != float(request.pricing_policy.target_margin_pct):
        raise JobQuoteFailureError("bid margin does not match the job request")
    if not money_equal(summary.canonical_quote_price, pricing.quote_price):
        raise JobQuoteFailureError("bid summary price does not match the bid")
    if not money_equal(summary.base_manufacturing_cost, base):
        raise JobQuoteFailureError("bid summary base does not match the bid")
    if summary.notes != list(bid.notes):
        raise JobQuoteFailureError("bid summary dropped internal notes")
    assumption_fields = {item.field for item in bid.assumptions}
    if "material_supply" in assumption_fields or "delivery_date" in assumption_fields:
        raise JobQuoteFailureError("workflow invented material-supply or delivery-date assumptions")


def _write_snapshot_tree(sources: tuple[SourceSnapshot, ...], snapshot_root: Path) -> None:
    for source in sources:
        destination = snapshot_root.joinpath(*source.original_ref.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.raw_bytes)


def _artifact_entries(files: dict[str, bytes]) -> tuple[dict[str, str], ...]:
    entries: list[dict[str, str]] = []
    for path, role, audience in _ARTIFACTS:
        raw = files[path]
        entries.append(
            {
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "role": role,
                "audience": audience,
            }
        )
    return tuple(entries)


def _validate_generated_json(raw: bytes, schema: str, label: str) -> dict[str, Any]:
    try:
        payload = parse_json_object(raw, label=label)
        validate_instance(payload, schema, label=label)
    except JobQuoteRefusalError as exc:
        raise JobQuoteFailureError(f"generated {label} failed validation: {exc}") from exc
    return payload


def _validate_generated(files: dict[str, bytes]) -> None:
    checks = (
        ("internal/estimate.json", "estimates/guitar_build_estimate_v1.schema.json", "estimate"),
        ("internal/bid.json", "bids/bid_v1.schema.json", "bid"),
        ("internal/bid_summary.json", "bids/bid_summary_v1.schema.json", "bid summary"),
        ("customer/proposal.json", "proposals/proposal_v1.schema.json", "proposal"),
    )
    for path, schema, label in checks:
        _validate_generated_json(files[path], schema, label)


def build_job_quote_packet(loaded: LoadedJobQuote) -> JobQuotePacket:
    """Calculate from captured source bytes and return a validated, unpublished packet."""
    request = loaded.request
    snapshot_root = Path(tempfile.mkdtemp(prefix="job-quote-snapshot-"))
    try:
        _write_snapshot_tree(loaded.sources, snapshot_root)
        try:
            estimate_input = load_guitar_estimate_input(
                snapshot_root / request.estimate_input_ref
            )
            input_confidence = estimate_input.provenance.confidence
            estimate = calculate_guitar_build_estimate(
                estimate_input,
                estimate_id=request.estimate_id,
                estimate_input_ref=request.estimate_input_ref,
                effective_date=request.effective_date,
                repo_root=snapshot_root,
            )
        except ValueError as exc:
            from business.workflows.models import JobQuoteRefusalError

            raise JobQuoteRefusalError(str(exc)) from exc
        estimate = replace(estimate, status=DRAFT_STATUS)
        try:
            mapping = build_bid_from_estimate(
                estimate,
                bid_id=request.bid_id,
                project_name=request.project_name,
                customer_name=request.customer_name,
                revision=request.revision,
                created_at=request.created_at,
                target_margin_pct=request.pricing_policy.target_margin_pct,
                manufacturing_ref=PACKET_MANUFACTURING_REF,
                internal_notes=request.internal_notes,
            )
        except ValueError as exc:
            raise JobQuoteFailureError(f"estimate to bid mapping failed: {exc}") from exc
        summary = generate_bid_summary(mapping.bid)
        proposal = project_public_proposal(summary, request)
        markdown = render_customer_draft_markdown(proposal)
        _assert_links(
            request=request,
            estimate=estimate,
            input_confidence=input_confidence,
            mapping=mapping,
            summary=summary,
        )
        _assert_public_projection(
            proposal,
            markdown,
            request=request,
            estimate=estimate,
            mapping=mapping,
            sources=loaded.sources,
        )

        files: dict[str, bytes] = {}
        job_source = loaded.sources[0]
        files["internal/job_request.json"] = job_source.raw_bytes
        for source in loaded.sources:
            files[f"{SOURCE_SNAPSHOT_ROOT}/{source.original_ref}"] = source.raw_bytes
        files["internal/estimate.json"] = dumps_json(estimate_payload(estimate))
        files["internal/bid.json"] = dumps_json(bid_payload(mapping.bid))
        files["internal/bid_summary.json"] = dumps_json(summary_payload(summary))
        files["internal/cost_report.md"] = render_internal_cost_report(
            request=request,
            estimate=estimate,
            mapping=mapping,
            sources=loaded.sources,
        ).encode("utf-8")
        files["customer/proposal.json"] = dumps_json(proposal_payload(proposal))
        files["customer/proposal.md"] = markdown.encode("utf-8")
        _validate_generated(files)

        artifacts = _artifact_entries(files)
        manifest = manifest_payload(
            request=request,
            estimate=estimate,
            mapping=mapping,
            sources=loaded.sources,
            artifacts=artifacts,
        )
        manifest_bytes = dumps_json(manifest)
        parsed_manifest = _validate_generated_json(
            manifest_bytes,
            "workflows/job_quote_manifest_v1.schema.json",
            "manifest",
        )
        _assert_manifest_hashes(parsed_manifest, files)
        files["manifest.json"] = manifest_bytes
        return JobQuotePacket(
            files=files,
            job_id=request.job_id,
            direct_manufacturing_cost=as_money(
                estimate.cost_summary.total_direct_manufacturing_cost
            ),
            quote_price=as_money(mapping.bid.pricing.quote_price),
        )
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)


def _assert_manifest_hashes(manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    listed = {entry["path"] for entry in manifest["artifacts"]}
    if "manifest.json" in listed:
        raise JobQuoteFailureError("manifest must not hash itself")
    for entry in manifest["artifacts"]:
        path = entry["path"]
        if path not in files:
            raise JobQuoteFailureError(f"manifest lists missing artifact {path}")
        digest = hashlib.sha256(files[path]).hexdigest()
        if digest != entry["sha256"]:
            raise JobQuoteFailureError(f"manifest digest does not match {path}")
    for entry in manifest["sources"]:
        path = entry["snapshot_ref"]
        if path not in files or hashlib.sha256(files[path]).hexdigest() != entry["sha256"]:
            raise JobQuoteFailureError(f"manifest source digest does not match {path}")
    customer = json.loads(files["customer/proposal.json"].decode("utf-8"))
    if customer["status"] != DRAFT_STATUS:
        raise JobQuoteFailureError("published proposal status is not draft")


def run_job_quote(*, root: Path | str, job: str, output_dir: str | Path) -> JobQuoteResult:
    """Validate, calculate, and publish one draft packet. Sources are not modified."""
    workspace = resolve_workspace(root)
    destination = resolve_output_dir(workspace, output_dir)
    loaded = load_job_quote(workspace, job)
    packet = build_job_quote_packet(loaded)
    publish_packet(destination, packet.files)
    return JobQuoteResult(
        job_id=packet.job_id,
        status=DRAFT_STATUS,
        direct_manufacturing_cost=packet.direct_manufacturing_cost,
        quote_price=packet.quote_price,
        output_dir=destination,
        customer_proposal_json=destination / "customer" / "proposal.json",
        customer_proposal_markdown=destination / "customer" / "proposal.md",
    )
