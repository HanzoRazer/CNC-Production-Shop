"""Opt-in governed machine-cost derivation for BidV1.

Dev Order: CNC-MACHINE-COST-WIRING-1

This module constructs an auditable MachineCostingV1 record from explicit
machine-profile and cost-basis paths. It does not select a default machine,
apply margin/risk, or substitute commercial billing rates.

Persisted refs are always repository-relative POSIX paths so long-lived bids
remain portable across environments.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from business.bids.models import MachineCostingV1
from business.calculators.machine_cost_basis import (
    as_money,
)
from business.calculators.machine_cost_basis import (
    derive_machine_time_cost as _derive_machine_time_cost,
)

COST_BASIS_ROLE_INTERNAL_TECHNICAL = "internal_technical_cost"
DERIVATION_FORMULA = "machine_hour_rate * runtime_minutes / 60"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COST_BASIS_ID_RE = re.compile(r"^MACHINE-COST-BASIS-[A-Z0-9-]+$")
_MACHINE_ID_RE = re.compile(r"^MACHINE-[A-Z0-9-]+$")
_ALLOWED_PROVENANCE_STATUS = frozenset(
    {"draft", "reviewed", "approved", "superseded", "retired"}
)


def derive_machine_time_cost(
    machine_hour_rate: float,
    runtime_minutes: float,
) -> float:
    """Derive machine_time_cost for bid construction.

    Bid-facing wrapper around the calculator API. Maps runtime_minutes to the
    calculator's machine_minutes parameter without duplicating the math.
    """
    return _derive_machine_time_cost(
        machine_hour_rate=machine_hour_rate,
        machine_minutes=runtime_minutes,
    )


def _load_json(path: Path) -> dict[str, object]:
    """Load a JSON object from an explicit path."""
    if not path.is_file():
        raise FileNotFoundError(f"Referenced artifact not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _resolve_under_repo(path: Path, repo_root: Path) -> Path:
    """Resolve a path and require it to stay inside the repository root."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    root = repo_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"path must be inside repository root {root.as_posix()}: {path}"
        ) from exc
    return resolved


def _to_repo_relative_ref(path: Path, repo_root: Path) -> str:
    """Store a portable repo-relative POSIX ref (never an absolute path)."""
    resolved = _resolve_under_repo(path, repo_root)
    return resolved.relative_to(repo_root.resolve()).as_posix()


def build_machine_costing(
    *,
    machine_id: str,
    runtime_minutes: float,
    machine_profile_path: Path,
    cost_basis_path: Path,
    repo_root: Path | None = None,
) -> MachineCostingV1:
    """Build an immutable machine-costing derivation from explicit paths.

    Responsibilities:
        - resolve both paths under the repository root
        - load the machine profile and cost-basis files from those paths
        - verify IDs and machine agreement
        - read machine_hour_rate from the governed cost basis
        - derive machine-time cost via the shared calculator
        - return MachineCostingV1 with repo-relative provenance refs

    Does not scan directories, select defaults, or fall back by machine_id.
    Absolute paths are accepted only when they resolve inside repo_root; the
    persisted refs are always repo-relative.
    """
    if runtime_minutes <= 0:
        raise ValueError("runtime_minutes must be greater than 0")
    if not _MACHINE_ID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")

    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    profile_path = _resolve_under_repo(Path(machine_profile_path), root)
    cost_basis_file = _resolve_under_repo(Path(cost_basis_path), root)

    profile = _load_json(profile_path)
    cost_basis = _load_json(cost_basis_file)

    profile_machine_id = profile.get("machine_id")
    if profile_machine_id != machine_id:
        raise ValueError(
            f"machine profile machine_id {profile_machine_id!r} does not match "
            f"requested machine_id {machine_id!r}"
        )

    cost_basis_machine_id = cost_basis.get("machine_id")
    if cost_basis_machine_id != machine_id:
        raise ValueError(
            f"cost basis machine_id {cost_basis_machine_id!r} does not match "
            f"requested machine_id {machine_id!r}"
        )

    cost_basis_id = cost_basis.get("cost_basis_id")
    if not isinstance(cost_basis_id, str) or not _COST_BASIS_ID_RE.match(cost_basis_id):
        raise ValueError(
            f"cost basis at {cost_basis_path} has invalid cost_basis_id: "
            f"{cost_basis_id!r}"
        )

    rate = cost_basis.get("machine_hour_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise ValueError(f"cost basis at {cost_basis_path} is missing machine_hour_rate")
    if rate < 0:
        raise ValueError("machine_hour_rate must be non-negative")

    provenance_status = cost_basis.get("status")
    if (
        not isinstance(provenance_status, str)
        or provenance_status not in _ALLOWED_PROVENANCE_STATUS
    ):
        raise ValueError(
            f"cost basis at {cost_basis_path} has invalid status: "
            f"{provenance_status!r}"
        )

    derived = derive_machine_time_cost(float(rate), float(runtime_minutes))

    return MachineCostingV1(
        machine_id=machine_id,
        machine_profile_ref=_to_repo_relative_ref(profile_path, root),
        cost_basis_id=cost_basis_id,
        cost_basis_ref=_to_repo_relative_ref(cost_basis_file, root),
        cost_basis_role=COST_BASIS_ROLE_INTERNAL_TECHNICAL,
        runtime_minutes=float(runtime_minutes),
        machine_hour_rate=as_money(rate),
        derived_machine_time_cost=derived,
        derivation=DERIVATION_FORMULA,
        provenance_status=provenance_status,
    )
