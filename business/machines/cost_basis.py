"""Resolve a governed machine cost basis by machine_id.

Dev Order: CNC-MACHINE-COST-BASIS-1

This is the connection layer between a bid's opt-in machine_id reference and the
governed machine-hour cost basis. It loads cost-basis fixtures from
fixtures/machines/cost_basis/ and exposes the true-cost machine_hour_rate.

Loading is filesystem-backed and read-only; it does not mutate fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

_COST_BASIS_DIR = Path(__file__).parent.parent.parent / "fixtures" / "machines" / "cost_basis"


class MachineCostBasisNotFoundError(LookupError):
    """Raised when no governed cost basis exists for a machine_id."""


def _iter_cost_basis_records(cost_basis_dir: Path) -> list[dict]:
    """Load all cost-basis JSON records from a directory."""
    records: list[dict] = []
    if not cost_basis_dir.exists():
        return records
    for path in sorted(cost_basis_dir.glob("*.json")):
        with open(path) as f:
            records.append(json.load(f))
    return records


def load_machine_cost_basis(
    machine_id: str,
    cost_basis_dir: Path | None = None,
) -> dict:
    """Load the governed cost basis for a machine.

    Args:
        machine_id: Machine profile identifier, e.g. MACHINE-BCM2030CA-ATC-V1
        cost_basis_dir: Optional override of the fixtures directory (for tests)

    Returns:
        The cost-basis record as a dict

    Raises:
        MachineCostBasisNotFoundError: If no record matches machine_id
    """
    directory = cost_basis_dir if cost_basis_dir is not None else _COST_BASIS_DIR
    matches = [r for r in _iter_cost_basis_records(directory) if r.get("machine_id") == machine_id]
    if not matches:
        raise MachineCostBasisNotFoundError(
            f"No machine cost basis found for machine_id={machine_id!r}"
        )
    if len(matches) > 1:
        raise MachineCostBasisNotFoundError(
            f"Multiple cost-basis records found for machine_id={machine_id!r}; "
            "expected exactly one governed record"
        )
    return matches[0]


def machine_hour_rate_for(
    machine_id: str,
    cost_basis_dir: Path | None = None,
) -> float:
    """Return the true-cost machine_hour_rate for a machine_id.

    Args:
        machine_id: Machine profile identifier
        cost_basis_dir: Optional override of the fixtures directory (for tests)

    Returns:
        The governed machine_hour_rate (currency/hour)

    Raises:
        MachineCostBasisNotFoundError: If no record matches machine_id
    """
    return float(load_machine_cost_basis(machine_id, cost_basis_dir)["machine_hour_rate"])
