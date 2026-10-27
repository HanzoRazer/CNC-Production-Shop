"""Strict loading for a thin-skin job quote and its equipment dependencies.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-002

The V1 parser, ref resolver, and labor/machine derivation checks are reused.
Equipment derivations use the existing equipment calculators. Source bytes are
read once.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from business.calculators.equipment_cost_basis import (
    assemble_equipment_hour_rate,
    derive_equipment_electricity_cost_per_hour,
)
from business.calculators.machine_cost_basis import money_equal
from business.workflows.loading import (
    _check_labor_rates,
    _check_machine_derivation,
    _effective_date,
    _sha256,
    parse_json_object,
    resolve_workspace_file,
    validate_instance,
)
from business.workflows.models import (
    ESTIMATE_INPUT_CONTRACT_V2,
    POLICY_ID,
    POLICY_VERSION,
    JobQuoteRefusalError,
    JobQuoteRequestV2,
    LoadedJobQuote,
    PricingPolicyV1,
    SourceSnapshot,
)

_ESTIMATE_ID_RE = re.compile(r"^THIN-SKIN-GUITAR-BUILD-ESTIMATE-[A-Z0-9-]+$")

_ESTIMATE_SCHEMA = "estimates/thin_skin_estimate_input_v2.schema.json"
_PRODUCT_SCHEMA = "products/thin_skin_guitar_product_definition_v1.schema.json"
_MACHINE_PROFILE_SCHEMA = "machines/machine_profile_v1.schema.json"
_MACHINE_BASIS_SCHEMA = "machines/machine_cost_basis_v1.schema.json"
_EQUIPMENT_PROFILE_SCHEMA = "equipment/equipment_profile_v1.schema.json"
_EQUIPMENT_BASIS_SCHEMA = "equipment/equipment_cost_basis_v1.schema.json"


@dataclass(frozen=True)
class _HeldSource:
    snapshot: SourceSnapshot
    payload: dict[str, Any]


class _SourceCaptor:
    """Read each workspace file once and refuse conflicting claims for one path."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._by_ref: dict[str, _HeldSource] = {}
        self._by_resolved: dict[str, _HeldSource] = {}

    def adopt(
        self,
        *,
        original_ref: str,
        resolved: Path,
        raw: bytes,
        role: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> SourceSnapshot:
        snapshot = SourceSnapshot(
            role=role,
            record_id=record_id,
            original_ref=original_ref,
            raw_bytes=raw,
            sha256=_sha256(raw),
        )
        held = _HeldSource(snapshot=snapshot, payload=payload)
        self._remember(original_ref, str(resolved), held)
        return snapshot

    def capture(
        self,
        ref: str,
        *,
        role: str,
        record_id_field: str,
        schema_relative: str,
        expected_id: str | None = None,
    ) -> tuple[SourceSnapshot, dict[str, Any]]:
        original_ref, resolved = resolve_workspace_file(self._root, ref, label=role)
        resolved_key = str(resolved)
        prior = self._by_ref.get(original_ref)
        if prior is None and resolved_key in self._by_resolved:
            prior = self._by_resolved[resolved_key]
            if prior.snapshot.role != role or (
                expected_id is not None and prior.snapshot.record_id != expected_id
            ):
                raise JobQuoteRefusalError(
                    f"conflicting role, schema, or identity for one source file: {original_ref}"
                )
            if prior.snapshot.original_ref == original_ref:
                return prior.snapshot, prior.payload
            reused = SourceSnapshot(
                role=role,
                record_id=prior.snapshot.record_id,
                original_ref=original_ref,
                raw_bytes=prior.snapshot.raw_bytes,
                sha256=prior.snapshot.sha256,
            )
            held = _HeldSource(snapshot=reused, payload=prior.payload)
            self._by_ref[original_ref] = held
            return reused, prior.payload
        if prior is not None:
            if prior.snapshot.role != role or (
                expected_id is not None and prior.snapshot.record_id != expected_id
            ):
                raise JobQuoteRefusalError(
                    f"conflicting role, schema, or identity for {original_ref}"
                )
            return prior.snapshot, prior.payload

        try:
            raw = resolved.read_bytes()
        except OSError as exc:
            raise JobQuoteRefusalError(f"{role} could not be read") from exc
        payload = parse_json_object(raw, label=role)
        validate_instance(payload, schema_relative, label=role)
        record_id = payload.get(record_id_field)
        if not isinstance(record_id, str) or not record_id.strip():
            raise JobQuoteRefusalError(f"{role} is missing {record_id_field}")
        if expected_id is not None and record_id != expected_id:
            raise JobQuoteRefusalError(
                f"{role} {record_id_field} does not match the referencing record"
            )
        snapshot = self.adopt(
            original_ref=original_ref,
            resolved=resolved,
            raw=raw,
            role=role,
            record_id=record_id,
            payload=payload,
        )
        return snapshot, payload

    def _remember(self, original_ref: str, resolved_key: str, held: _HeldSource) -> None:
        existing = self._by_resolved.get(resolved_key)
        if existing is not None and (
            existing.snapshot.role != held.snapshot.role
            or existing.snapshot.record_id != held.snapshot.record_id
        ):
            raise JobQuoteRefusalError(
                f"conflicting role, schema, or identity for one source file: {original_ref}"
            )
        self._by_ref[original_ref] = held
        self._by_resolved[resolved_key] = held


def _request_from_payload(payload: dict[str, Any]) -> JobQuoteRequestV2:
    quantity = payload["quantity"]
    if type(quantity) is not int or quantity != 1:
        raise JobQuoteRefusalError("quantity must be the integer 1")
    policy = payload["pricing_policy"]
    margin = policy["target_margin_pct"]
    margin_is_number = isinstance(margin, (int, float)) and not isinstance(margin, bool)
    if not margin_is_number or not math.isfinite(margin):
        raise JobQuoteRefusalError("target_margin_pct must be a finite number")
    if not 0 <= float(margin) < 100:
        raise JobQuoteRefusalError("target_margin_pct must be >= 0 and < 100")
    estimate_id = str(payload["estimate_id"])
    if not _ESTIMATE_ID_RE.fullmatch(estimate_id):
        raise JobQuoteRefusalError(
            "estimate_id must match THIN-SKIN-GUITAR-BUILD-ESTIMATE-... "
            "for thin_skin_estimate_input_v2"
        )
    if payload["estimate_input_contract"] != ESTIMATE_INPUT_CONTRACT_V2:
        raise JobQuoteRefusalError("unsupported estimate input contract")
    if policy["policy_id"] != POLICY_ID or policy["policy_version"] != POLICY_VERSION:
        raise JobQuoteRefusalError("unsupported pricing policy")
    created_at = str(payload["created_at"])
    return JobQuoteRequestV2(
        job_id=str(payload["job_id"]),
        estimate_id=estimate_id,
        bid_id=str(payload["bid_id"]),
        proposal_id=str(payload["proposal_id"]),
        project_name=str(payload["project_name"]),
        customer_name=str(payload["customer_name"]),
        revision=str(payload["revision"]),
        created_at=created_at,
        effective_date=_effective_date(created_at),
        estimate_input_contract=str(payload["estimate_input_contract"]),
        estimate_input_ref=str(payload["estimate_input_ref"]),
        quantity=1,
        currency=str(payload["currency"]),
        pricing_policy=PricingPolicyV1(
            policy_id=str(policy["policy_id"]),
            policy_version=str(policy["policy_version"]),
            target_margin_pct=float(margin),
        ),
        customer_deliverables=tuple(str(item) for item in payload["customer_deliverables"]),
        customer_exclusions=tuple(str(item) for item in payload["customer_exclusions"]),
        internal_notes=tuple(str(item) for item in payload["internal_notes"]),
    )


def _duplicate(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise JobQuoteRefusalError(f"duplicate {label}: {value}")
        seen.add(value)


def _check_identities(estimate: dict[str, Any]) -> None:
    input_ids = [
        str(item["input_id"])
        for collection in ("material_inputs", "purchased_component_inputs")
        for item in estimate[collection]
    ]
    _duplicate(input_ids, "input_id")
    _duplicate(
        [str(item["operation_id"]) for item in estimate["operations"]],
        "operation_id",
    )
    equipment_ids = [str(item["equipment_id"]) for item in estimate["equipment_refs"]]
    _duplicate(equipment_ids, "equipment_id")
    declared = set(equipment_ids)
    for operation in estimate["operations"]:
        equipment_id = str(operation.get("equipment_id") or "")
        occupancy = operation["time_model"].get("equipment_occupancy_minutes", 0)
        if isinstance(occupancy, bool) or not isinstance(occupancy, (int, float)):
            raise JobQuoteRefusalError(
                f"operation {operation['operation_id']} occupancy is not a finite number"
            )
        if not math.isfinite(float(occupancy)) or float(occupancy) < 0:
            raise JobQuoteRefusalError(
                f"operation {operation['operation_id']} occupancy is not finite"
            )
        if equipment_id and equipment_id not in declared:
            raise JobQuoteRefusalError(f"undeclared equipment_id: {equipment_id}")
        if float(occupancy) > 0 and not equipment_id:
            raise JobQuoteRefusalError(
                f"operation {operation['operation_id']} occupies undeclared equipment"
            )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise JobQuoteRefusalError(f"{label} is not a finite number")
    return float(value)


def _check_equipment_derivation(profile: dict[str, Any], basis: dict[str, Any]) -> None:
    electricity = basis["electricity"]
    profile_kw = _finite_number(
        profile["connected_load_estimate"]["total_kw"],
        "equipment profile connected load",
    )
    connected = _finite_number(electricity["connected_load_kw"], "equipment connected_load_kw")
    if profile_kw != connected:
        raise JobQuoteRefusalError(
            "equipment cost basis connected_load_kw does not match the equipment profile"
        )
    try:
        derived = derive_equipment_electricity_cost_per_hour(
            connected,
            _finite_number(electricity["load_factor"], "equipment load_factor"),
            _finite_number(electricity["price_per_kwh"], "equipment price_per_kwh"),
        )
        assembled = assemble_equipment_hour_rate(
            _finite_number(basis["equipment_burden_rate_per_hour"], "equipment burden"),
            _finite_number(electricity["electricity_cost_per_hour"], "equipment electricity"),
            _finite_number(basis["consumables_cost_per_hour"], "equipment consumables"),
        )
    except ValueError as exc:
        raise JobQuoteRefusalError(f"equipment rate derivation is inconsistent: {exc}") from exc
    except JobQuoteRefusalError:
        raise
    if not money_equal(derived, electricity["electricity_cost_per_hour"]):
        raise JobQuoteRefusalError(
            "equipment electricity_cost_per_hour does not match its derivation"
        )
    if not money_equal(assembled.equipment_hour_rate, basis["equipment_hour_rate"]):
        raise JobQuoteRefusalError(
            "equipment_hour_rate does not match burden + electricity + consumables"
        )


def load_thin_skin_job_quote(
    workspace: Path,
    job_ref: str,
    job_path: Path,
    job_bytes: bytes,
    job_payload: dict[str, Any],
) -> LoadedJobQuote:
    """Capture a validated thin-skin request and every declared dependency."""
    request = _request_from_payload(job_payload)
    captor = _SourceCaptor(workspace)
    job_snapshot = captor.adopt(
        original_ref=job_ref,
        resolved=job_path,
        raw=job_bytes,
        role="job_request",
        record_id=request.job_id,
        payload=job_payload,
    )
    estimate_snapshot, estimate_payload = captor.capture(
        request.estimate_input_ref,
        role="estimate_input",
        record_id_field="estimate_input_id",
        schema_relative=_ESTIMATE_SCHEMA,
    )
    if estimate_payload["quantity"] != request.quantity:
        raise JobQuoteRefusalError("estimate input quantity does not match the job request")
    if estimate_payload["currency"] != request.currency:
        raise JobQuoteRefusalError("estimate input currency does not match the job request")
    if request.currency != "USD" or request.quantity != 1:
        raise JobQuoteRefusalError("this workflow only supports quantity 1 and currency USD")
    _check_identities(estimate_payload)
    _check_labor_rates(estimate_payload)

    product_snapshot, product_payload = captor.capture(
        str(estimate_payload["product_ref"]),
        role="product",
        record_id_field="product_id",
        schema_relative=_PRODUCT_SCHEMA,
        expected_id=str(estimate_payload["product_id"]),
    )
    profile_snapshot, profile_payload = captor.capture(
        str(estimate_payload["machine_profile_ref"]),
        role="machine_profile",
        record_id_field="machine_id",
        schema_relative=_MACHINE_PROFILE_SCHEMA,
        expected_id=str(estimate_payload["machine_id"]),
    )
    basis_snapshot, basis_payload = captor.capture(
        str(estimate_payload["cost_basis_ref"]),
        role="machine_cost_basis",
        record_id_field="cost_basis_id",
        schema_relative=_MACHINE_BASIS_SCHEMA,
        expected_id=str(estimate_payload["cost_basis_id"]),
    )
    if basis_payload["machine_id"] != estimate_payload["machine_id"]:
        raise JobQuoteRefusalError("machine_id does not match the machine cost basis")
    if basis_payload.get("currency") != request.currency:
        raise JobQuoteRefusalError("machine cost basis currency does not match the job request")
    _check_machine_derivation(profile_payload, basis_payload)

    equipment_snapshots: list[SourceSnapshot] = []
    for ref in sorted(
        estimate_payload["equipment_refs"], key=lambda item: str(item["equipment_id"])
    ):
        equipment_id = str(ref["equipment_id"])
        profile_snap, equipment_profile = captor.capture(
            str(ref["equipment_profile_ref"]),
            role="equipment_profile",
            record_id_field="equipment_id",
            schema_relative=_EQUIPMENT_PROFILE_SCHEMA,
            expected_id=equipment_id,
        )
        basis_snap, equipment_basis = captor.capture(
            str(ref["cost_basis_ref"]),
            role="equipment_cost_basis",
            record_id_field="cost_basis_id",
            schema_relative=_EQUIPMENT_BASIS_SCHEMA,
            expected_id=str(ref["cost_basis_id"]),
        )
        if equipment_basis["equipment_id"] != equipment_id:
            raise JobQuoteRefusalError(
                f"equipment_id does not match the cost basis for {equipment_id}"
            )
        if equipment_basis.get("currency") != request.currency:
            raise JobQuoteRefusalError(
                f"equipment cost basis currency does not match the job request: {equipment_id}"
            )
        _check_equipment_derivation(equipment_profile, equipment_basis)
        equipment_snapshots.append(profile_snap)
        equipment_snapshots.append(basis_snap)

    if product_payload["product_id"] != estimate_payload["product_id"]:
        raise JobQuoteRefusalError("product_id does not match the product record")
    if profile_payload["machine_id"] != estimate_payload["machine_id"]:
        raise JobQuoteRefusalError("machine_id does not match the machine profile")

    sources = (
        job_snapshot,
        estimate_snapshot,
        product_snapshot,
        profile_snapshot,
        basis_snapshot,
        *equipment_snapshots,
    )
    return LoadedJobQuote(request=request, job_ref=job_ref, sources=sources)
