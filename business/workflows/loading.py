"""Strict loading for a job quote request and its local sources.

Dev Orders: CNC-JOB-QUOTE-WORKFLOW-001 and CNC-JOB-QUOTE-WORKFLOW-002

Parsers reject duplicate keys, non-finite constants, and boolean numbers before
any existing loader can coerce them. Referenced files are read once.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend

from business.calculators.cnc_electricity import calculate_loaded_labor_rate
from business.calculators.machine_cost_basis import (
    assemble_machine_hour_rate,
    derive_electricity_cost_per_hour,
    money_equal,
)
from business.workflows.models import (
    ESTIMATE_INPUT_CONTRACT,
    ESTIMATE_INPUT_CONTRACT_V2,
    POLICY_ID,
    POLICY_VERSION,
    JobQuoteFailureError,
    JobQuoteRefusalError,
    JobQuoteRequestV1,
    LoadedJobQuote,
    PricingPolicyV1,
    SourceSnapshot,
)

_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
_ESTIMATE_ID_RE = re.compile(r"^GUITAR-BUILD-ESTIMATE-[A-Z0-9-]+$")
_CREATED_AT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

_SCHEMA_BY_ROLE = {
    "job_request": "workflows/job_quote_request_v1.schema.json",
    "estimate_input": "estimates/guitar_estimate_input_v1.schema.json",
    "product": "products/guitar_product_definition_v1.schema.json",
    "machine_profile": "machines/machine_profile_v1.schema.json",
    "machine_cost_basis": "machines/machine_cost_basis_v1.schema.json",
}

_REQUEST_SCHEMAS = {
    ("1.0.0", ESTIMATE_INPUT_CONTRACT): "workflows/job_quote_request_v1.schema.json",
    ("2.0.0", ESTIMATE_INPUT_CONTRACT_V2): "workflows/job_quote_request_v2.schema.json",
}


def _is_number(_checker: object, instance: object) -> bool:
    return isinstance(instance, (int, float)) and not isinstance(instance, bool)


def _is_integer(_checker: object, instance: object) -> bool:
    return isinstance(instance, int) and not isinstance(instance, bool)


_StrictValidator = extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine_many(
        {"number": _is_number, "integer": _is_integer}
    ),
)


def _reject_constant(name: str) -> NoReturn:
    raise JobQuoteRefusalError(f"non-finite JSON constant: {name}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise JobQuoteRefusalError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _reject_nonfinite(value: object, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise JobQuoteRefusalError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item, label)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite(item, label)


def parse_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    """Parse one JSON object. Duplicate keys and non-finite numbers are refused."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JobQuoteRefusalError(f"{label} is not UTF-8") from exc
    try:
        data = json.loads(
            text,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except JobQuoteRefusalError:
        raise
    except json.JSONDecodeError as exc:
        raise JobQuoteRefusalError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise JobQuoteRefusalError(f"{label} must be a JSON object")
    _reject_nonfinite(data, label)
    return data


@cache
def load_checkout_schema(relative: str) -> dict[str, Any]:
    """Load a canonical schema from this source checkout."""
    path = _CHECKOUT_ROOT / "schemas" / relative
    if not path.is_file():
        raise JobQuoteFailureError(f"canonical schema is not in this checkout: {relative}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobQuoteFailureError(f"canonical schema could not be read: {relative}") from exc
    if not isinstance(payload, dict):
        raise JobQuoteFailureError(f"canonical schema is not an object: {relative}")
    return payload


def validate_instance(instance: object, schema_relative: str, *, label: str) -> None:
    """Validate one instance with format checking and boolean numbers refused."""
    schema = load_checkout_schema(schema_relative)
    validator = _StrictValidator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.absolute_path))
    if not errors:
        return
    err: ValidationError = errors[0]
    location = "/".join(str(part) for part in err.absolute_path) or "$"
    raise JobQuoteRefusalError(f"{label} failed schema at {location}: {err.message}")


def resolve_workspace(root: Path | str) -> Path:
    """Resolve an explicit source workspace directory."""
    candidate = Path(root)
    if not candidate.exists():
        raise JobQuoteRefusalError(f"workspace root does not exist: {root}")
    if not candidate.is_dir():
        raise JobQuoteRefusalError("workspace root must be a directory")
    return candidate.resolve()


def _posix_parts(raw: str, *, label: str) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw.strip():
        raise JobQuoteRefusalError(f"{label} is required")
    if "://" in raw or "\\" in raw:
        raise JobQuoteRefusalError(f"{label} must be a workspace-relative POSIX path")
    if raw.startswith("/"):
        raise JobQuoteRefusalError(f"{label} must be workspace-relative")
    parts = tuple(part for part in raw.split("/") if part != ".")
    if not parts or any(part in {"", ".."} for part in parts):
        raise JobQuoteRefusalError(f"{label} must not contain parent traversal or empty segments")
    return parts


def resolve_workspace_file(root: Path, raw: str, *, label: str) -> tuple[str, Path]:
    """Resolve one workspace-relative file. The returned ref keeps the caller's path."""
    if "://" in raw:
        raise JobQuoteRefusalError(f"{label} must be a local workspace file, not a URL")
    path = Path(raw)
    if path.is_absolute() or (len(raw) >= 2 and raw[1] == ":"):
        raise JobQuoteRefusalError(f"{label} must be workspace-relative")
    parts = _posix_parts(raw, label=label)
    ref = "/".join(parts)
    lexical = root.joinpath(*parts)
    if lexical.is_symlink():
        target = lexical.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise JobQuoteRefusalError(f"{label} symlink escapes the workspace root") from exc
    try:
        resolved = lexical.resolve()
        resolved.relative_to(root)
    except ValueError as exc:
        raise JobQuoteRefusalError(f"{label} escapes the workspace root") from exc
    if not resolved.is_file():
        raise JobQuoteRefusalError(f"{label} does not exist: {ref}")
    return ref, resolved


def resolve_output_dir(root: Path, raw: str | Path) -> Path:
    """Return a new in-workspace directory path. Existing paths and symlinks are refused."""
    text = raw if isinstance(raw, str) else raw.as_posix()
    if not text or not str(text).strip():
        raise JobQuoteRefusalError("output directory is required")
    if "://" in text:
        raise JobQuoteRefusalError("output directory must be a local path inside the workspace")
    candidate = Path(text)
    if ".." in candidate.parts:
        raise JobQuoteRefusalError("output directory must stay inside the workspace")
    lexical = candidate if candidate.is_absolute() else root / candidate
    if lexical.is_symlink():
        raise JobQuoteRefusalError("output directory must not be a symlink")
    if lexical.exists():
        raise JobQuoteRefusalError("output directory already exists")
    try:
        resolved = lexical.resolve()
        resolved.relative_to(root)
    except ValueError as exc:
        raise JobQuoteRefusalError("output directory must stay inside the workspace") from exc
    if resolved == root:
        raise JobQuoteRefusalError("output directory must be a new directory inside the workspace")
    return resolved


def _read_once(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise JobQuoteRefusalError(f"{label} could not be read") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _effective_date(created_at: str) -> str:
    if not _CREATED_AT_RE.fullmatch(created_at):
        raise JobQuoteRefusalError("created_at must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise JobQuoteRefusalError("created_at must be a real UTC timestamp ending in Z") from exc
    return parsed.date().isoformat()


def _request_from_payload(payload: dict[str, Any]) -> JobQuoteRequestV1:
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
            "estimate_id must match GUITAR-BUILD-ESTIMATE-... for guitar_estimate_input_v1"
        )
    if payload["estimate_input_contract"] != ESTIMATE_INPUT_CONTRACT:
        raise JobQuoteRefusalError("unsupported estimate input contract")
    if policy["policy_id"] != POLICY_ID or policy["policy_version"] != POLICY_VERSION:
        raise JobQuoteRefusalError("unsupported pricing policy")
    created_at = str(payload["created_at"])
    return JobQuoteRequestV1(
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


def _check_labor_rates(estimate_input: dict[str, Any]) -> None:
    seen: set[str] = set()
    for rate in estimate_input["labor_rate_inputs"]:
        rate_id = str(rate["labor_rate_id"])
        if rate_id in seen:
            raise JobQuoteRefusalError(f"duplicate labor_rate_id: {rate_id}")
        seen.add(rate_id)
        try:
            expected = calculate_loaded_labor_rate(
                float(rate["base_wage_per_hour"]),
                float(rate["payroll_burden_pct"]),
            )
        except ValueError as exc:
            raise JobQuoteRefusalError(str(exc)) from exc
        if not money_equal(expected, rate["loaded_rate_per_hour"]):
            raise JobQuoteRefusalError(
                f"labor rate {rate_id} loaded_rate_per_hour does not match its derivation"
            )


def _check_machine_derivation(profile: dict[str, Any], basis: dict[str, Any]) -> None:
    electricity = basis["electricity"]
    profile_kw = profile["connected_load_estimate"]["total_kw"]
    if isinstance(profile_kw, bool) or not isinstance(profile_kw, (int, float)):
        raise JobQuoteRefusalError("machine profile connected load is not a finite number")
    if not math.isfinite(float(profile_kw)):
        raise JobQuoteRefusalError("machine profile connected load is not finite")
    if float(profile_kw) != float(electricity["connected_load_kw"]):
        raise JobQuoteRefusalError(
            "machine cost basis connected_load_kw does not match the machine profile"
        )
    try:
        derived_electricity = derive_electricity_cost_per_hour(
            float(electricity["connected_load_kw"]),
            float(electricity["load_factor"]),
            float(electricity["price_per_kwh"]),
        )
        assembled = assemble_machine_hour_rate(
            float(basis["machine_burden_rate_per_hour"]),
            float(electricity["electricity_cost_per_hour"]),
            float(basis["tooling_cost_per_hour"]),
        )
    except ValueError as exc:
        raise JobQuoteRefusalError(f"machine rate derivation is inconsistent: {exc}") from exc
    if not money_equal(derived_electricity, electricity["electricity_cost_per_hour"]):
        raise JobQuoteRefusalError(
            "machine cost basis electricity_cost_per_hour does not match its derivation"
        )
    if not money_equal(assembled.machine_hour_rate, basis["machine_hour_rate"]):
        raise JobQuoteRefusalError(
            "machine_hour_rate does not match burden + electricity + tooling"
        )


def _load_role(
    root: Path,
    ref: str,
    *,
    role: str,
    record_id_field: str,
    schema_relative: str | None = None,
) -> tuple[SourceSnapshot, dict[str, Any]]:
    original_ref, path = resolve_workspace_file(root, ref, label=role)
    raw = _read_once(path, label=role)
    payload = parse_json_object(raw, label=role)
    schema = schema_relative if schema_relative is not None else _SCHEMA_BY_ROLE[role]
    validate_instance(payload, schema, label=role)
    record_id = payload.get(record_id_field)
    if not isinstance(record_id, str) or not record_id.strip():
        raise JobQuoteRefusalError(f"{role} is missing {record_id_field}")
    snapshot = SourceSnapshot(
        role=role,
        record_id=record_id,
        original_ref=original_ref,
        raw_bytes=raw,
        sha256=_sha256(raw),
    )
    return snapshot, payload


def load_job_quote(root: Path | str, job: str) -> LoadedJobQuote:
    """Read and validate the job request and the records it names."""
    workspace = resolve_workspace(root)
    job_ref, job_path = resolve_workspace_file(workspace, job, label="job")
    job_bytes = _read_once(job_path, label="job request")
    job_payload = parse_json_object(job_bytes, label="job request")
    version = job_payload.get("record_version")
    contract = job_payload.get("estimate_input_contract")
    if not isinstance(version, str) or not isinstance(contract, str):
        raise JobQuoteRefusalError("unsupported request version and contract pair")
    schema = _REQUEST_SCHEMAS.get((version, contract))
    if schema is None:
        raise JobQuoteRefusalError(
            f"unsupported request version and contract pair: {version} / {contract}"
        )
    validate_instance(job_payload, schema, label="job request")
    if (version, contract) == ("1.0.0", ESTIMATE_INPUT_CONTRACT):
        return _load_guitar_job_quote(workspace, job_ref, job_path, job_bytes, job_payload)
    from business.workflows.loading_v2 import load_thin_skin_job_quote

    return load_thin_skin_job_quote(workspace, job_ref, job_path, job_bytes, job_payload)


def _load_guitar_job_quote(
    workspace: Path,
    job_ref: str,
    job_path: Path,
    job_bytes: bytes,
    job_payload: dict[str, Any],
) -> LoadedJobQuote:
    """Load a guitar_estimate_input_v1 request. The job payload is already validated."""
    del job_path
    request = _request_from_payload(job_payload)

    estimate_snapshot, estimate_payload = _load_role(
        workspace,
        request.estimate_input_ref,
        role="estimate_input",
        record_id_field="estimate_input_id",
    )
    if estimate_payload["quantity"] != request.quantity:
        raise JobQuoteRefusalError("estimate input quantity does not match the job request")
    if estimate_payload["currency"] != request.currency:
        raise JobQuoteRefusalError("estimate input currency does not match the job request")
    if request.currency != "USD" or request.quantity != 1:
        raise JobQuoteRefusalError("this workflow only supports quantity 1 and currency USD")

    product_snapshot, product_payload = _load_role(
        workspace,
        str(estimate_payload["product_ref"]),
        role="product",
        record_id_field="product_id",
    )
    profile_snapshot, profile_payload = _load_role(
        workspace,
        str(estimate_payload["machine_profile_ref"]),
        role="machine_profile",
        record_id_field="machine_id",
    )
    basis_snapshot, basis_payload = _load_role(
        workspace,
        str(estimate_payload["cost_basis_ref"]),
        role="machine_cost_basis",
        record_id_field="cost_basis_id",
    )

    if product_payload["product_id"] != estimate_payload["product_id"]:
        raise JobQuoteRefusalError("product_id does not match the product record")
    if profile_payload["machine_id"] != estimate_payload["machine_id"]:
        raise JobQuoteRefusalError("machine_id does not match the machine profile")
    if basis_payload["machine_id"] != estimate_payload["machine_id"]:
        raise JobQuoteRefusalError("machine_id does not match the machine cost basis")
    if basis_payload["cost_basis_id"] != estimate_payload["cost_basis_id"]:
        raise JobQuoteRefusalError("cost_basis_id does not match the machine cost basis")
    if basis_payload.get("currency") != request.currency:
        raise JobQuoteRefusalError("machine cost basis currency does not match the job request")

    _check_labor_rates(estimate_payload)
    _check_machine_derivation(profile_payload, basis_payload)

    job_snapshot = SourceSnapshot(
        role="job_request",
        record_id=request.job_id,
        original_ref=job_ref,
        raw_bytes=job_bytes,
        sha256=_sha256(job_bytes),
    )
    sources = (
        job_snapshot,
        estimate_snapshot,
        product_snapshot,
        profile_snapshot,
        basis_snapshot,
    )
    return LoadedJobQuote(request=request, job_ref=job_ref, sources=sources)
