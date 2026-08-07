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

from collections.abc import Sequence
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

# The purchased mirror of the four make states. Each B state exists ONLY to be
# compared with the M state of the same index; the mapping is data rather than
# convention so that a cross-state comparison is a raised error and not a
# plausible-looking number.
BUY_STATES: tuple[str, ...] = ("B1", "B2", "B3", "B4")

BUY_TO_MAKE: dict[str, str] = {"B1": "M1", "B2": "M2", "B3": "M3", "B4": "M4"}

# A purchased neck is not free the moment it arrives, and it is not free even
# when it is perfect. These are the reasons a landed price is not a delivered
# cost, and they are retained by the shop at every completion state.
PRICE_STATUS_UNRESOLVED = "unresolved"


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


@dataclass(frozen=True)
class ChannelScenario:
    """One route from a factory to a retail shelf.

    Margins are industry rules of thumb, not observations. Their spread is the
    point: a single assumed markup would produce a false precision, whereas
    four plausible routes bracket the manufacturing cost and the bracket is
    the answer.
    """

    scenario_id: str
    description: str
    retail_margin: float
    distributor_margin: float
    manufacturer_margin: float

    def __post_init__(self) -> None:
        for name in ("retail_margin", "distributor_margin", "manufacturer_margin"):
            value = getattr(self, name)
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{name} must be in [0, 1)")

    def manufacturing_cost(self, retail_price: float) -> float:
        """Work backwards from the shelf to the factory gate."""
        if retail_price <= 0:
            raise ValueError("retail_price must be > 0")
        wholesale = retail_price * (1 - self.retail_margin)
        to_distributor = wholesale * (1 - self.distributor_margin)
        return as_money(to_distributor * (1 - self.manufacturer_margin))


@dataclass(frozen=True)
class BackCalculatedTarget:
    """What a derived manufacturing cost demands of this shop.

    Reported two ways because they are the same constraint seen from opposite
    ends: the labour MINUTES that fit the target at the shop's rate, and the
    labour RATE that fits the target at the shop's current minutes. Neither is
    a recommendation; together they say whether the gap is process or wages.
    """

    scenario_id: str
    retail_price: float
    manufacturing_cost: float
    shop_material_cost: float
    shop_machine_cost: float
    budget_for_labour: float
    labour_minutes_affordable: float | None
    implied_labour_rate: float | None
    reachable: bool
    note: str


def back_calculate_target(
    *,
    scenario: ChannelScenario,
    retail_price: float,
    shop_material_cost: float,
    shop_machine_minutes: float,
    shop_labour_minutes: float,
    loaded_labour_rate: float,
    machine_rate: float,
) -> BackCalculatedTarget:
    """Solve the shop against one channel scenario.

    The interesting failure is when materials and machine time alone exceed the
    manufacturing cost. That is not a labour problem and no shop-floor change
    reaches it, so it is reported as unreachable rather than as a negative
    labour budget.
    """
    mfg = scenario.manufacturing_cost(retail_price)
    machine_cost = shop_machine_minutes / 60.0 * machine_rate
    budget = mfg - shop_material_cost - machine_cost

    if budget <= 0:
        return BackCalculatedTarget(
            scenario_id=scenario.scenario_id,
            retail_price=retail_price,
            manufacturing_cost=mfg,
            shop_material_cost=as_money(shop_material_cost),
            shop_machine_cost=as_money(machine_cost),
            budget_for_labour=as_money(budget),
            labour_minutes_affordable=None,
            implied_labour_rate=None,
            reachable=False,
            note="Materials and machine time alone exceed the manufacturing cost. "
            "No change to labour reaches this target.",
        )

    minutes = budget / loaded_labour_rate * 60.0
    rate = budget / (shop_labour_minutes / 60.0) if shop_labour_minutes > 0 else None
    return BackCalculatedTarget(
        scenario_id=scenario.scenario_id,
        retail_price=retail_price,
        manufacturing_cost=mfg,
        shop_material_cost=as_money(shop_material_cost),
        shop_machine_cost=as_money(machine_cost),
        budget_for_labour=as_money(budget),
        labour_minutes_affordable=round(minutes, 1),
        implied_labour_rate=None if rate is None else as_money(rate),
        reachable=True,
        note=f"Reachable at {round(minutes, 1)} labour minutes against "
        f"{shop_labour_minutes} today, or at a labour rate of "
        f"{as_money(rate) if rate else 0} against {loaded_labour_rate}.",
    )


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


# --------------------------------------------------------------------- buy side
#
# Everything below was added by NECK-MAKE-OR-BUY-GAP-CLOSURE-1. The accepted
# sprint compared in-house cost against two purchase references that both sat at
# M4, which meant three of the four completion states had no buy side at all and
# the like-for-like rule was a comment rather than a constraint.


@dataclass(frozen=True)
class RetainedShopOperation:
    """Shop work that survives the decision to buy.

    A delivered price is not a delivered cost. Someone still opens the box,
    measures the neck against the pocket it has to sit in, and corrects what
    does not fit. Those minutes are charged at the loaded rate to the BUY side,
    which is why the maximum competitive purchase price is below the in-house
    cost rather than equal to it.
    """

    operation: str
    minutes: float
    rationale: str

    def __post_init__(self) -> None:
        if self.minutes < 0:
            raise ValueError(f"{self.operation}: retained minutes must be non-negative")


@dataclass(frozen=True)
class BuyCompletionState:
    """A purchased-neck completion state.

    This is a definition of what would have to be true of a purchased neck, not
    an assertion that one can be bought. `compatible_supplier_identified` is the
    field that keeps those two apart: the Smart Guitar is headless with a
    locking clamp nut at a 628.65 mm scale, and every purchase reference on
    record is a conventional headstock neck. The economics still calculate — a
    threshold is a threshold — but a comparison against a source that does not
    exist is not commercially actionable, and the record has to say so.
    """

    state_id: str
    description: str
    make_equivalent: str
    completion_requirements: tuple[str, ...]
    retained_shop_operations: tuple[RetainedShopOperation, ...]
    inspection_requirements: tuple[str, ...]
    compatibility_requirements: tuple[str, ...]
    purchase_price_status: str = PRICE_STATUS_UNRESOLVED
    compatible_supplier_identified: bool = False
    source: str = "engineering_estimate"
    confidence: str = "draft"

    def __post_init__(self) -> None:
        if self.state_id not in BUY_STATES:
            raise ValueError(f"unknown buy state {self.state_id!r}")
        expected = BUY_TO_MAKE[self.state_id]
        if self.make_equivalent != expected:
            raise ValueError(
                f"{self.state_id} must map to {expected}, not {self.make_equivalent!r}: "
                f"a buy state may only be compared with the make state of the same "
                f"completion, and this mapping is the guard against comparing a "
                f"machined shaft with a finished neck"
            )
        if not self.completion_requirements:
            raise ValueError(f"{self.state_id}: completion requirements must be stated")
        if not self.inspection_requirements:
            raise ValueError(f"{self.state_id}: inspection requirements must be stated")
        if self.compatible_supplier_identified and (
            self.purchase_price_status == PRICE_STATUS_UNRESOLVED
        ):
            raise ValueError(
                f"{self.state_id}: a state cannot claim an identified compatible "
                f"supplier while its purchase price remains unresolved"
            )

    @property
    def retained_minutes(self) -> float:
        return float(sum(o.minutes for o in self.retained_shop_operations))

    def retained_completion_cost(self, loaded_labour_rate: float) -> float:
        """Loaded cost of the work buying does not remove."""
        return as_money(self.retained_minutes / 60.0 * loaded_labour_rate)


def assert_like_for_like(make_state: str, buy_state: str) -> None:
    """Refuse any comparison that is not at a single completion state.

    Comparing M1 with B4 is the specific error the completion-state taxonomy
    was built to prevent, and it is the error the accepted sprint's own report
    records having made once already.
    """
    if make_state not in COMPLETION_STATES:
        raise ValueError(f"unknown make state {make_state!r}")
    if buy_state not in BUY_STATES:
        raise ValueError(f"unknown buy state {buy_state!r}")
    if BUY_TO_MAKE[buy_state] != make_state:
        raise ValueError(
            f"{make_state} may not be compared with {buy_state}; "
            f"{buy_state} is equivalent to {BUY_TO_MAKE[buy_state]}"
        )


@dataclass(frozen=True)
class ThresholdComparison:
    """One purchase-price threshold judged against one completion state.

    `maximum_compatible_delivered_purchase_price` is the number the sprint was
    called to produce: the most a delivered equivalent neck may cost before
    buying it beats building it, net of the shop work buying does not remove.

    `commercially_actionable` is deliberately separate from the arithmetic. The
    comparison can be correct and still be unusable, because no supplier of a
    headless clamp-nut neck has been identified. Collapsing those two into one
    verdict is how a threshold becomes mistaken for a quote.
    """

    make_state: str
    buy_state: str
    threshold_price: float
    make_cost_per_saleable: float
    retained_buy_side_completion_cost: float
    maximum_compatible_delivered_purchase_price: float
    difference_versus_threshold: float
    result: str
    commercially_actionable: bool
    reason: str
    compatibility_caveat: str


def evaluate_threshold(
    *,
    make_scenario: MakeScenario,
    buy_state: BuyCompletionState,
    threshold_price: float,
    loaded_labour_rate: float,
    tolerance: float = 0.005,
) -> ThresholdComparison:
    """Judge one threshold price at one completion state.

    The sign convention is stated here because it inverts easily. Total buy cost
    is the delivered price PLUS retained shop work; total make cost is the
    in-house figure. So

        difference = threshold - (make_cost - retained)

    and a POSITIVE difference means buying at that price costs more than
    building, i.e. make is lower cost.
    """
    if threshold_price <= 0:
        raise ValueError("threshold price must be > 0")
    assert_like_for_like(make_scenario.completion_state, buy_state.state_id)

    retained = buy_state.retained_completion_cost(loaded_labour_rate)
    ceiling = as_money(make_scenario.cost_per_saleable - retained)
    difference = as_money(threshold_price - ceiling)

    if abs(difference) < tolerance:
        result = "break_even"
    elif difference > 0:
        result = "make_lower_cost"
    else:
        result = "buy_lower_cost"

    if buy_state.compatible_supplier_identified:
        actionable = True
        reason = "a compatible purchased-neck source is identified"
    else:
        actionable = False
        reason = "no compatible purchased-neck source identified"

    return ThresholdComparison(
        make_state=make_scenario.completion_state,
        buy_state=buy_state.state_id,
        threshold_price=threshold_price,
        make_cost_per_saleable=make_scenario.cost_per_saleable,
        retained_buy_side_completion_cost=retained,
        maximum_compatible_delivered_purchase_price=ceiling,
        difference_versus_threshold=difference,
        result=result,
        commercially_actionable=actionable,
        reason=reason,
        compatibility_caveat=(
            "The threshold is analytical. It is not a supplier offer, and no "
            "source of a headless clamp-nut neck at this completion state has "
            "been identified."
        ),
    )


def union_sweep(existing: Sequence[float], added: Sequence[float]) -> list[float]:
    """Union two sweep grids into a sorted, deduplicated axis.

    Deterministic by construction: sorted ascending, duplicates collapsed. The
    accepted points survive so every previously computed cell still recomputes;
    the added points extend the domain. Values that differ only by float noise
    would produce two near-identical axis entries, so they are keyed on a
    rounded value.
    """
    seen: dict[float, float] = {}
    for value in list(existing) + list(added):
        v = float(value)
        seen.setdefault(round(v, 6), v)
    return [seen[k] for k in sorted(seen)]
