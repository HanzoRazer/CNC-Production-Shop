"""Governed occupancy costing for non-CNC equipment.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1

Mirrors business/bids/machine_costing.py: explicit paths only, no directory
scanning, no default selection, no fallback by equipment_id, and repo-relative
POSIX refs so long-lived estimates stay portable.

Equipment occupancy is costed separately from CNC machine time on purpose. A
vacuum press holding a body for ninety minutes and a spindle cutting for nine
minutes are different economic events, and collapsing them hides the process
behavior the thin-skin estimate exists to expose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from business.calculators.equipment_cost_basis import derive_equipment_occupancy_cost
from business.calculators.machine_cost_basis import as_money
from business.estimates.models_v2 import EquipmentOccupancyCostingV1

COST_BASIS_ROLE_INTERNAL_TECHNICAL = "internal_technical_cost"
DERIVATION_FORMULA = "equipment_hour_rate * occupancy_minutes / 60"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COST_BASIS_ID_RE = re.compile(r"^EQUIPMENT-COST-BASIS-[A-Z0-9-]+$")
_EQUIPMENT_ID_RE = re.compile(r"^EQUIPMENT-[A-Z0-9-]+$")
_ALLOWED_PROVENANCE_STATUS = frozenset(
    {"draft", "reviewed", "approved", "superseded", "retired"}
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


def build_equipment_occupancy_costing(
    *,
    equipment_id: str,
    occupancy_minutes: float,
    equipment_profile_path: Path,
    cost_basis_path: Path,
    repo_root: Path | None = None,
) -> EquipmentOccupancyCostingV1:
    """Build an immutable occupancy derivation from explicit paths.

    Responsibilities:
        - resolve both paths under the repository root
        - load the equipment profile and cost-basis files from those paths
        - verify IDs and equipment agreement
        - read equipment_hour_rate from the governed cost basis
        - derive occupancy cost via the shared calculator
        - return EquipmentOccupancyCostingV1 with repo-relative refs

    Zero occupancy is permitted and yields a zero-cost record, so an equipment
    reference declared by an estimate stays visible even when the current
    operation set never loads it.
    """
    if isinstance(occupancy_minutes, bool) or occupancy_minutes < 0:
        raise ValueError("occupancy_minutes must be a non-negative number")
    if not _EQUIPMENT_ID_RE.match(equipment_id):
        raise ValueError(f"invalid equipment_id: {equipment_id!r}")

    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    profile_path = _resolve_under_repo(Path(equipment_profile_path), root)
    cost_basis_file = _resolve_under_repo(Path(cost_basis_path), root)

    profile = _load_json(profile_path)
    cost_basis = _load_json(cost_basis_file)

    profile_equipment_id = profile.get("equipment_id")
    if profile_equipment_id != equipment_id:
        raise ValueError(
            f"equipment profile equipment_id {profile_equipment_id!r} does not "
            f"match requested equipment_id {equipment_id!r}"
        )

    cost_basis_equipment_id = cost_basis.get("equipment_id")
    if cost_basis_equipment_id != equipment_id:
        raise ValueError(
            f"cost basis equipment_id {cost_basis_equipment_id!r} does not "
            f"match requested equipment_id {equipment_id!r}"
        )

    cost_basis_id = cost_basis.get("cost_basis_id")
    if not isinstance(cost_basis_id, str) or not _COST_BASIS_ID_RE.match(cost_basis_id):
        raise ValueError(
            f"cost basis at {cost_basis_path} has invalid cost_basis_id: "
            f"{cost_basis_id!r}"
        )

    rate = cost_basis.get("equipment_hour_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise ValueError(
            f"cost basis at {cost_basis_path} is missing equipment_hour_rate"
        )
    if rate < 0:
        raise ValueError("equipment_hour_rate must be non-negative")

    provenance_status = cost_basis.get("status")
    if (
        not isinstance(provenance_status, str)
        or provenance_status not in _ALLOWED_PROVENANCE_STATUS
    ):
        raise ValueError(
            f"cost basis at {cost_basis_path} has invalid status: "
            f"{provenance_status!r}"
        )

    derived = derive_equipment_occupancy_cost(float(rate), float(occupancy_minutes))

    return EquipmentOccupancyCostingV1(
        equipment_id=equipment_id,
        equipment_profile_ref=_to_repo_relative_ref(profile_path, root),
        cost_basis_id=cost_basis_id,
        cost_basis_ref=_to_repo_relative_ref(cost_basis_file, root),
        cost_basis_role=COST_BASIS_ROLE_INTERNAL_TECHNICAL,
        occupancy_minutes=float(occupancy_minutes),
        equipment_hour_rate=as_money(rate),
        derived_occupancy_cost=derived,
        derivation=DERIVATION_FORMULA,
        provenance_status=provenance_status,
    )
