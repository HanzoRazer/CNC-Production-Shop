"""Opt-in governed machine-cost derivation for BidV1.

Dev Order: CNC-MACHINE-COST-WIRING-1

This module constructs an auditable MachineCostingV1 record from explicit
machine-profile and cost-basis paths. It does not select a default machine,
apply margin/risk, or substitute commercial billing rates.
"""

from __future__ import annotations

import json
from pathlib import Path

from business.bids.models import MachineCostingV1
from business.calculators.machine_cost_basis import (
    derive_machine_time_cost as _derive_machine_time_cost,
)

COST_BASIS_ROLE_INTERNAL_TECHNICAL = "internal_technical_cost"
DERIVATION_FORMULA = "machine_hour_rate * runtime_minutes / 60"


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


def _path_ref(path: Path) -> str:
    """Preserve the caller-provided path as a portable POSIX ref string."""
    return path.as_posix()


def build_machine_costing(
    *,
    machine_id: str,
    runtime_minutes: float,
    machine_profile_path: Path,
    cost_basis_path: Path,
) -> MachineCostingV1:
    """Build an immutable machine-costing derivation from explicit paths.

    Responsibilities:
        - load the machine profile and cost-basis files from the given paths
        - verify the profile machine_id
        - verify the cost-basis machine_id and cost_basis_id presence
        - verify both artifacts reference the same machine
        - read machine_hour_rate from the governed cost basis
        - derive machine-time cost via the shared calculator
        - return MachineCostingV1 with full provenance fields

    Does not scan directories, select defaults, or fall back by machine_id.
    """
    if runtime_minutes <= 0:
        raise ValueError("runtime_minutes must be greater than 0")

    profile = _load_json(Path(machine_profile_path))
    cost_basis = _load_json(Path(cost_basis_path))

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
    if not isinstance(cost_basis_id, str) or not cost_basis_id:
        raise ValueError(f"cost basis at {cost_basis_path} is missing cost_basis_id")

    rate = cost_basis.get("machine_hour_rate")
    if not isinstance(rate, (int, float)):
        raise ValueError(f"cost basis at {cost_basis_path} is missing machine_hour_rate")
    if rate < 0:
        raise ValueError("machine_hour_rate must be non-negative")

    provenance_status = cost_basis.get("status")
    if not isinstance(provenance_status, str) or not provenance_status:
        raise ValueError(f"cost basis at {cost_basis_path} is missing status")

    derived = derive_machine_time_cost(float(rate), float(runtime_minutes))

    return MachineCostingV1(
        machine_id=machine_id,
        machine_profile_ref=_path_ref(Path(machine_profile_path)),
        cost_basis_id=cost_basis_id,
        cost_basis_ref=_path_ref(Path(cost_basis_path)),
        cost_basis_role=COST_BASIS_ROLE_INTERNAL_TECHNICAL,
        runtime_minutes=float(runtime_minutes),
        machine_hour_rate=float(rate),
        derived_machine_time_cost=derived,
        derivation=DERIVATION_FORMULA,
        provenance_status=provenance_status,
    )
