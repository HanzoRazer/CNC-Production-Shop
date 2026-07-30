"""Neck make-or-buy cost model.

Dev Order: NECK-MAKE-OR-BUY-BATCH-COSTING-1

The question this answers is not "does batching help" — it does, by $8.62 per
neck at any quantity, because only one operation carries setup at all. It is:

    at what fretboard price and fretwork time does an in-house neck cost less
    than a delivered one?

Two things follow from that framing and shape everything here.

Costs are reported BOTH per unit started and per saleable unit. Necks that fail
inspection consumed their material and their machine time, and dividing only at
the end would hide that. Batch setup amortises across SALEABLE units, so a poor
yield makes fixed cost worse, not neutral.

The buy side is deliberately structured rather than priced. A catalog figure is
not a landed cost: freight, duty, incoming inspection, corrective work and
reject rate all sit between them, and on the one import considered here those
roughly double it. Where a value is unknown the field exists and says so, so
the model cannot present a placeholder as an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from business.calculators.machine_cost_basis import as_money

# Completion states, least to most complete. A purchased neck may only be
# compared with an in-house neck at the SAME state; comparing a machined shaft
# with a delivered production-ready neck is the error this enum exists to stop.
COMPLETION_STATES: tuple[str, ...] = ("M1", "M2", "M3", "M4")

COMPLETION_DESCRIPTIONS: dict[str, str] = {
    "M1": "CNC-machined shaft, truss rod channel cut, fretboard not attached",
    "M2": "Fretboard installed over the truss rod, levelled and radiused",
    "M3": "Frets installed, levelled, crowned and dressed",
    "M4": "Nut cut, relief set, neck finished — ready to hang on a body",
}


@dataclass(frozen=True)
class NeckOperation:
    """One operation in the neck subsystem.

    Carries the V2 six-field distinction rather than collapsing it. The first
    version of this class had only setup, touch and machine, so clamp time and
    cure time had nowhere to go and were charged as operator labour — 29
    minutes per neck of somebody watching glue dry at the loaded rate. That is
    precisely the error the six-field model exists to prevent, and it was
    introduced while extending that model.

    elapsed_wait_minutes is calendar time and costs nothing at all.
    equipment_occupancy_minutes costs the equipment rate, never labour.
    Only setup, touch and rework are ever operator-present.

    setup_per_batch is the only route to any batching benefit in this model,
    and exactly one operation uses it.
    """

    operation_id: str
    description: str
    setup_minutes: float = 0.0
    touch_minutes: float = 0.0
    machine_minutes: float = 0.0
    equipment_occupancy_minutes: float = 0.0
    elapsed_wait_minutes: float = 0.0
    equipment_rate_per_hour: float = 0.0
    setup_per_batch: bool = False
    from_state: str = "M1"
    is_draft_addition: bool = False

    def __post_init__(self) -> None:
        for name in (
            "setup_minutes",
            "touch_minutes",
            "machine_minutes",
            "equipment_occupancy_minutes",
            "elapsed_wait_minutes",
            "equipment_rate_per_hour",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def labour_minutes(self, quantity: int, saleable: float) -> float:
        """Operator minutes attributable to ONE saleable neck.

        Batch setup divides by saleable rather than by quantity: a neck that
        fails still consumed its share of the fixture setup, and the units that
        survive have to carry it.
        """
        if quantity < 1:
            raise ValueError("quantity must be >= 1")
        if saleable <= 0:
            raise ValueError("saleable quantity must be > 0")
        if saleable > quantity:
            raise ValueError("saleable cannot exceed quantity started")
        setup = (
            self.setup_minutes / saleable
            if self.setup_per_batch
            else self.setup_minutes * quantity / saleable
        )
        return float(setup + self.touch_minutes * quantity / saleable)

    def machine_minutes_per_saleable(self, quantity: int, saleable: float) -> float:
        """Runtime is per part; failures consumed theirs and it is not recovered."""
        if saleable <= 0:
            raise ValueError("saleable quantity must be > 0")
        return float(self.machine_minutes * quantity / saleable)

    def occupancy_cost_per_saleable(self, quantity: int, saleable: float) -> float:
        """Equipment held by the job. A cost, but never a labour cost."""
        if saleable <= 0:
            raise ValueError("saleable quantity must be > 0")
        minutes = self.equipment_occupancy_minutes * quantity / saleable
        return float(minutes / 60.0 * self.equipment_rate_per_hour)

    def elapsed_wait_per_saleable(self, quantity: int, saleable: float) -> float:
        """Calendar time. Reported so it is visible, costed at nothing."""
        if saleable <= 0:
            raise ValueError("saleable quantity must be > 0")
        return float(self.elapsed_wait_minutes * quantity / saleable)


@dataclass(frozen=True)
class NeckMaterial:
    material_id: str
    description: str
    cost: float
    from_state: str = "M1"


@dataclass(frozen=True)
class YieldPolicy:
    """Saleable units out of units started.

    Expressed as a rate with an explicit derivation rather than a bare
    percentage, because nothing here is measured and the record should not
    pretend otherwise.
    """

    rate: float
    basis: str
    source: str = "engineering_estimate"
    confidence: str = "draft"

    def __post_init__(self) -> None:
        if not 0.0 < self.rate <= 1.0:
            raise ValueError("yield rate must be in (0, 1]")

    def saleable(self, quantity: int) -> float:
        if quantity < 1:
            raise ValueError("quantity must be >= 1")
        return float(quantity) * self.rate


@dataclass(frozen=True)
class MakeScenario:
    """One in-house build at one completion state and quantity."""

    completion_state: str
    quantity: int
    saleable: float
    material_cost: float
    setup_cost: float
    touch_cost: float
    machine_cost: float
    occupancy_cost: float
    cost_per_saleable: float
    cost_per_started: float
    yield_loss_per_saleable: float
    # Reported so the split is auditable: labour must never include the last two.
    labour_minutes: float
    machine_minutes: float
    occupancy_minutes: float
    elapsed_wait_minutes: float

    @property
    def max_competitive_purchase_price(self) -> float:
        """The most a delivered equivalent neck may cost before buying wins."""
        return self.cost_per_saleable


@dataclass(frozen=True)
class BuyReference:
    """A purchase option.

    catalog_price is what a supplier lists. Everything else is what stands
    between that and a neck you can actually hang on a body. Unknown fields are
    None on purpose: the model reports what it cannot compute rather than
    substituting a guess.
    """

    reference_id: str
    description: str
    completion_state: str
    catalog_price: float
    source: str
    confidence: str
    freight_per_unit: float | None = None
    duty_percent: float | None = None
    incoming_inspection_minutes: float | None = None
    corrective_work_minutes: float | None = None
    reject_percent: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_fully_landed(self) -> bool:
        return all(
            v is not None
            for v in (
                self.freight_per_unit,
                self.duty_percent,
                self.incoming_inspection_minutes,
                self.corrective_work_minutes,
                self.reject_percent,
            )
        )

    def landed_cost_per_good(self, loaded_labour_rate: float) -> float | None:
        """Delivered cost per USABLE neck, or None when inputs are unknown."""
        if not self.is_fully_landed:
            return None
        assert self.duty_percent is not None
        assert self.freight_per_unit is not None
        assert self.incoming_inspection_minutes is not None
        assert self.corrective_work_minutes is not None
        assert self.reject_percent is not None
        landed = self.catalog_price * (1 + self.duty_percent / 100) + self.freight_per_unit
        minutes = self.incoming_inspection_minutes + self.corrective_work_minutes
        labour = minutes / 60.0 * loaded_labour_rate
        survivors = 1 - self.reject_percent / 100
        if survivors <= 0:
            raise ValueError(f"{self.reference_id}: reject_percent must be < 100")
        return as_money((landed + labour) / survivors)


def _states_up_to(state: str) -> tuple[str, ...]:
    if state not in COMPLETION_STATES:
        raise ValueError(f"unknown completion state {state!r}")
    return COMPLETION_STATES[: COMPLETION_STATES.index(state) + 1]


def build_make_scenario(
    *,
    completion_state: str,
    quantity: int,
    operations: tuple[NeckOperation, ...],
    materials: tuple[NeckMaterial, ...],
    yield_policy: YieldPolicy,
    loaded_labour_rate: float,
    machine_rate: float,
) -> MakeScenario:
    """Cost one in-house neck at a completion state and batch quantity."""
    included = _states_up_to(completion_state)
    saleable = yield_policy.saleable(quantity)

    material_total = sum(m.cost for m in materials if m.from_state in included)
    material_per_saleable = material_total * quantity / saleable

    setup_min = touch_min = machine_min = 0.0
    occupancy_min = wait_min = occupancy_cost = 0.0
    for op in operations:
        if op.from_state not in included:
            continue
        if op.setup_per_batch:
            setup_min += op.setup_minutes / saleable
        else:
            setup_min += op.setup_minutes * quantity / saleable
        touch_min += op.touch_minutes * quantity / saleable
        machine_min += op.machine_minutes_per_saleable(quantity, saleable)
        occupancy_min += op.equipment_occupancy_minutes * quantity / saleable
        wait_min += op.elapsed_wait_per_saleable(quantity, saleable)
        occupancy_cost += op.occupancy_cost_per_saleable(quantity, saleable)

    # Labour is setup + touch ONLY. Occupancy and elapsed wait are deliberately
    # absent from this line and must stay absent.
    setup_cost = setup_min / 60.0 * loaded_labour_rate
    touch_cost = touch_min / 60.0 * loaded_labour_rate
    machine_cost = machine_min / 60.0 * machine_rate
    per_saleable = (
        material_per_saleable + setup_cost + touch_cost + machine_cost + occupancy_cost
    )

    # What the same build would cost if nothing were ever rejected. The gap is
    # the yield loss, and it is reported rather than folded away.
    perfect = yield_policy.__class__(rate=1.0, basis="no-loss reference")
    if yield_policy.rate == 1.0:
        per_started = per_saleable
    else:
        ideal = build_make_scenario(
            completion_state=completion_state,
            quantity=quantity,
            operations=operations,
            materials=materials,
            yield_policy=perfect,
            loaded_labour_rate=loaded_labour_rate,
            machine_rate=machine_rate,
        )
        per_started = ideal.cost_per_saleable

    return MakeScenario(
        completion_state=completion_state,
        quantity=quantity,
        saleable=round(saleable, 4),
        material_cost=as_money(material_per_saleable),
        setup_cost=as_money(setup_cost),
        touch_cost=as_money(touch_cost),
        machine_cost=as_money(machine_cost),
        occupancy_cost=as_money(occupancy_cost),
        cost_per_saleable=as_money(per_saleable),
        cost_per_started=as_money(per_started),
        yield_loss_per_saleable=as_money(per_saleable - per_started),
        labour_minutes=round(setup_min + touch_min, 2),
        machine_minutes=round(machine_min, 2),
        occupancy_minutes=round(occupancy_min, 2),
        elapsed_wait_minutes=round(wait_min, 2),
    )


def fretwork_threshold(
    *,
    target_price: float,
    completion_state: str,
    quantity: int,
    operations: tuple[NeckOperation, ...],
    materials: tuple[NeckMaterial, ...],
    yield_policy: YieldPolicy,
    loaded_labour_rate: float,
    machine_rate: float,
    fretwork_operation_id: str,
) -> float | None:
    """Fretwork minutes at which in-house cost equals target_price.

    Returns None when the target is unreachable even with fretwork at zero,
    which is the honest answer where material cost alone exceeds the price.
    Solved directly rather than by search: cost is linear in fretwork minutes.
    """
    baseline = build_make_scenario(
        completion_state=completion_state,
        quantity=quantity,
        operations=operations,
        materials=materials,
        yield_policy=yield_policy,
        loaded_labour_rate=loaded_labour_rate,
        machine_rate=machine_rate,
    )
    fret = next((o for o in operations if o.operation_id == fretwork_operation_id), None)
    if fret is None or fret.from_state not in _states_up_to(completion_state):
        return None

    saleable = yield_policy.saleable(quantity)
    # Cost contributed per fretwork minute, per saleable neck.
    per_minute = (quantity / saleable) / 60.0 * loaded_labour_rate
    if per_minute <= 0:
        return None
    reducible = baseline.cost_per_saleable - target_price
    threshold = fret.touch_minutes - reducible / per_minute
    if threshold < 0:
        return None
    return round(threshold, 2)
