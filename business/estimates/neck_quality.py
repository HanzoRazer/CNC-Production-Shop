"""Neck defect-mode taxonomy.

Dev Order: NECK-QUALITY-TAXONOMY-1

The cost model this sits beside spent an entire sprint comparing a $187.88
in-house neck to an $18-to-manufacture import as though the two were the same
object. They are not. The import the owner holds is basswood — a body wood,
janka 410 against khaya's 1070 — and every hardware interface on a neck is a
compression joint into the wood. So the comparison was never expensive-versus-
cheap. It was two different products sharing a silhouette.

This module retires the dimensionless "a neck". A neck is a set of DEFECT MODES
that a source either addresses or does not, and two necks may only be compared
on cost when their coverage matches.

Three distinctions carry the whole model.

ELIMINATION — what actually removes a defect, which is what decides its price:
    PROCESS        machine precision removes it, at zero marginal cost
    SPECIFICATION  buying the right material removes it, costing money not time
    LABOUR         a person removes it, costing minutes
Only the third competes with an import on cost. The first two are already paid
for, which is why "can quality be surpassed at a competitive price" is not the
same question as "can this shop match a factory's cost".

VISIBILITY — when the defect exists to be found:
    AT_RECEIPT     present and inspectable when the neck arrives
    LATENT         emerges in service, under string tension, after assembly
A latent defect cannot be inspected out at purchase. Basswood tuner holes are
drilled accurately and then wallow under load, so the hole moves after the
buyer has accepted the neck — and on a built instrument it returns as warranty.

REMEDIABILITY — whether money can buy parity at all:
    remediable     rework closes it; the cost is real and computable
    NOT remediable no spend closes it; the comparison is VOID, not expensive
Softness is not a defect you can pay to remove. A model that quietly prices
non-remediable defects as rework would report a number where it owes a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass

from business.calculators.machine_cost_basis import as_money

# What removes a defect. The order is deliberate: cost rises left to right.
ELIMINATION_PROCESS = "PROCESS"
ELIMINATION_SPECIFICATION = "SPECIFICATION"
ELIMINATION_LABOUR = "LABOUR"
ELIMINATIONS: tuple[str, ...] = (
    ELIMINATION_PROCESS,
    ELIMINATION_SPECIFICATION,
    ELIMINATION_LABOUR,
)

# When the defect can be found.
VISIBILITY_AT_RECEIPT = "AT_RECEIPT"
VISIBILITY_LATENT = "LATENT"
VISIBILITIES: tuple[str, ...] = (VISIBILITY_AT_RECEIPT, VISIBILITY_LATENT)

# How we know a defect mode is real. Nothing here is a measurement from a
# production run, because there has not been one; the strongest evidence in
# this file is a physical object the owner examined and a reference database.
EVIDENCE_OWNER_OBSERVED = "owner_observed"
EVIDENCE_FIELD_REPORTED = "field_reported_owner_relayed"
EVIDENCE_MATERIAL_DATA = "derived_from_species_data"
EVIDENCE_ASSUMED = "assumed"
EVIDENCE_CLASSES: tuple[str, ...] = (
    EVIDENCE_OWNER_OBSERVED,
    EVIDENCE_FIELD_REPORTED,
    EVIDENCE_MATERIAL_DATA,
    EVIDENCE_ASSUMED,
)


# Where in the build a defect can be caught. Ordered by value at risk, because
# that ordering IS the argument: a blank rejected at receipt costs the blank,
# and the same fault found on a finished neck costs the finished neck.
GATE_STAGES: tuple[str, ...] = ("MATERIAL_RECEIPT", "M1", "M2", "M3", "M4", "IN_SERVICE")

# What happens to a neck that fails. Not a judgement call: it follows from
# whether the failed mode is remediable.
DISPOSITION_ACCEPT = "ACCEPT"
DISPOSITION_REWORK = "REWORK"
DISPOSITION_SCRAP = "SCRAP"


@dataclass(frozen=True)
class AcceptanceCriterion:
    """How one defect mode is actually judged on a real neck.

    Mirrors the acceptance shape already used for the audio front end:
    a method you can hand to somebody, and a pass criterion that decides.

    `stage` is the earliest point the mode can be judged, and it is the whole
    economic argument. DEF-TRUSS-CHANNEL-CENTRING is classified latent and
    irremediable only because a fretboard gets glued over it — judged at M1 it
    is neither, and the loss is a $48.93 shaft instead of a warranty claim
    against a finished instrument.

    A threshold with owner_confirmed False is a PROPOSAL. The model may not
    treat it as a specification, and nothing here has been set by the owner.
    """

    defect_id: str
    stage: str
    method: str
    pass_criterion: str
    threshold: float | None = None
    units: str = ""
    threshold_source: str = "proposed_draft"
    owner_confirmed: bool = False

    def __post_init__(self) -> None:
        if self.stage not in GATE_STAGES:
            raise ValueError(f"unknown gate stage {self.stage!r}")
        if not self.method.strip():
            raise ValueError(
                f"{self.defect_id}: a criterion with no method is not a gate. "
                f"Somebody has to be able to perform it."
            )
        if not self.pass_criterion.strip():
            raise ValueError(f"{self.defect_id}: no pass criterion, so nothing decides")
        if self.owner_confirmed and self.threshold_source == "proposed_draft":
            raise ValueError(
                f"{self.defect_id}: marked owner_confirmed while the threshold is "
                f"still a draft proposal. Confirmation needs a source."
            )


@dataclass(frozen=True)
class Disposition:
    """What to do with one neck that failed one or more modes.

    Derived, never asserted: any non-remediable failure is SCRAP, because there
    is no work that recovers it. Everything else is REWORK at a computed cost.
    Calling a scrap neck 'rework' is how unrecoverable losses get buried in a
    rework budget.
    """

    verdict: str
    failed_modes: tuple[str, ...]
    unrecoverable_modes: tuple[str, ...]
    rework_minutes: float
    rework_material: float
    rework_cost: float
    loss_if_scrapped: float | None
    reason: str


def disposition_for(
    *,
    failed_modes: tuple[str, ...],
    taxonomy: tuple[DefectMode, ...],
    labour_rate: float,
    value_at_risk: float,
) -> Disposition:
    """Decide the fate of a neck from the modes it failed."""
    by_id = {d.defect_id: d for d in taxonomy}
    unknown = sorted(set(failed_modes) - set(by_id))
    if unknown:
        raise ValueError(f"failed modes not in the taxonomy: {unknown}")

    if not failed_modes:
        return Disposition(
            verdict=DISPOSITION_ACCEPT,
            failed_modes=(),
            unrecoverable_modes=(),
            rework_minutes=0.0,
            rework_material=0.0,
            rework_cost=0.0,
            loss_if_scrapped=None,
            reason="No mode failed.",
        )

    unrecoverable = tuple(sorted(m for m in failed_modes if not by_id[m].remediable))
    if unrecoverable:
        return Disposition(
            verdict=DISPOSITION_SCRAP,
            failed_modes=tuple(sorted(failed_modes)),
            unrecoverable_modes=unrecoverable,
            rework_minutes=0.0,
            rework_material=0.0,
            rework_cost=0.0,
            loss_if_scrapped=as_money(value_at_risk),
            reason=(
                f"SCRAP. {len(unrecoverable)} failed mode(s) cannot be recovered by any "
                f"work: {', '.join(unrecoverable)}. The loss is the value already in "
                f"the part, {as_money(value_at_risk)}, and no rework budget recovers it."
            ),
        )

    minutes = sum(by_id[m].remediation_minutes for m in failed_modes)
    material = sum(by_id[m].remediation_material for m in failed_modes)
    cost = as_money(minutes / 60.0 * labour_rate + material)
    return Disposition(
        verdict=DISPOSITION_REWORK,
        failed_modes=tuple(sorted(failed_modes)),
        unrecoverable_modes=(),
        rework_minutes=round(minutes, 1),
        rework_material=as_money(material),
        rework_cost=cost,
        loss_if_scrapped=as_money(value_at_risk),
        reason=(
            f"REWORK at {cost} against {as_money(value_at_risk)} already in the part. "
            f"Rework exceeds the part's value — scrap is cheaper."
            if cost > value_at_risk
            else f"REWORK at {cost}, below the {as_money(value_at_risk)} already in "
            f"the part."
        ),
    )


@dataclass(frozen=True)
class DefectMode:
    """One way a neck can be wrong.

    PREVENTING a defect and REPAIRING one are different prices and the model
    keeps them apart. labour_minutes and material_cost are what it costs to
    build the neck without the defect; remediation_minutes and
    remediation_material are what it costs to fix a neck that already has it.

    They diverge hardest exactly where it matters. A PROCESS mode costs nothing
    to prevent — the machine is already running and holding position is not an
    extra operation — but a misdrilled tuner hole in a delivered neck is plugged
    and redrilled by hand, or not fixed at all. Charging prevention cost as
    repair cost would make buying-and-fixing look free.
    """

    defect_id: str
    description: str
    elimination: str
    visibility: str
    remediable: bool
    labour_minutes: float = 0.0
    material_cost: float = 0.0
    remediation_minutes: float = 0.0
    remediation_material: float = 0.0
    evidence: str = EVIDENCE_ASSUMED
    note: str = ""

    def __post_init__(self) -> None:
        if self.elimination not in ELIMINATIONS:
            raise ValueError(f"unknown elimination {self.elimination!r}")
        if self.visibility not in VISIBILITIES:
            raise ValueError(f"unknown visibility {self.visibility!r}")
        if self.evidence not in EVIDENCE_CLASSES:
            raise ValueError(f"unknown evidence class {self.evidence!r}")
        if self.labour_minutes < 0 or self.material_cost < 0:
            raise ValueError("defect cost may not be negative")
        if self.elimination == ELIMINATION_PROCESS and (
            self.labour_minutes or self.material_cost
        ):
            raise ValueError(
                f"{self.defect_id}: a PROCESS mode costs nothing marginal. If it "
                f"costs minutes or money it is not eliminated by holding position, "
                f"and it belongs in LABOUR or SPECIFICATION."
            )
        if self.elimination == ELIMINATION_LABOUR and self.labour_minutes <= 0:
            raise ValueError(f"{self.defect_id}: a LABOUR mode must cost minutes")
        if self.elimination == ELIMINATION_SPECIFICATION and self.material_cost <= 0:
            raise ValueError(f"{self.defect_id}: a SPECIFICATION mode must cost money")
        if not self.remediable and self.elimination == ELIMINATION_LABOUR:
            raise ValueError(
                f"{self.defect_id}: labour-eliminated defects are remediable by "
                f"definition — someone can always do the work. Marking one "
                f"irremediable hides a material or process failure behind labour."
            )
        if self.remediation_minutes < 0 or self.remediation_material < 0:
            raise ValueError("remediation cost may not be negative")
        if not self.remediable and (self.remediation_minutes or self.remediation_material):
            raise ValueError(
                f"{self.defect_id}: marked irremediable but carries a repair price. "
                f"A repairable defect is remediable; pick one."
            )
        if self.remediable and not (self.remediation_minutes or self.remediation_material):
            raise ValueError(
                f"{self.defect_id}: claims to be remediable at no cost. Nothing is "
                f"repaired for free, and a zero here would make buy-and-fix look "
                f"costless against building it right."
            )

    def cost(self, labour_rate: float) -> float:
        """What it costs to BUILD this neck without the defect."""
        return as_money(self.labour_minutes / 60.0 * labour_rate + self.material_cost)

    def repair_cost(self, labour_rate: float) -> float | None:
        """What it costs to FIX a neck that already has it, or None if it can't be."""
        if not self.remediable:
            return None
        return as_money(
            self.remediation_minutes / 60.0 * labour_rate + self.remediation_material
        )


@dataclass(frozen=True)
class NeckSource:
    """A place a neck comes from, and the defect modes it addresses.

    `addresses` is the set of defect_ids this source is KNOWN to handle.
    Everything else in the taxonomy is presumed unaddressed, which is a
    deliberate asymmetry: a source earns coverage with evidence, it does not
    receive it by default. A source nobody has characterised gets no entry at
    all rather than an optimistic guess.

    `arrival_stage` is where the neck enters this shop's control, and it decides
    what can be CHECKED rather than what is true. A neck built here passes
    through every stage, so every criterion can be run. A finished neck bought
    in arrives at M4 with the truss channel under a glued fretboard and the
    blank's moisture history gone — those criteria cannot be run at all, and the
    honest verdict on them is UNVERIFIABLE, never "pass".
    """

    source_id: str
    description: str
    addresses: frozenset[str]
    evidence: str
    arrival_stage: str = "MATERIAL_RECEIPT"
    is_characterised: bool = True

    def __post_init__(self) -> None:
        if self.evidence not in EVIDENCE_CLASSES:
            raise ValueError(f"unknown evidence class {self.evidence!r}")
        if self.arrival_stage not in GATE_STAGES:
            raise ValueError(f"unknown arrival stage {self.arrival_stage!r}")

    def open_modes(self, taxonomy: tuple[DefectMode, ...]) -> tuple[DefectMode, ...]:
        """Modes this source leaves on the table."""
        return tuple(d for d in taxonomy if d.defect_id not in self.addresses)


@dataclass(frozen=True)
class CoverageComparison:
    """Whether two sources may be compared on cost, and what it would take.

    `comparable` is the gate. It is false whenever the two sources address
    different modes, because a cost difference between different products is
    not a saving. When the gap is closable the remediation figures say what
    closing it costs; when it is not, they are None and `blocking_modes` says
    why. A price is never reported alongside an open blocker.
    """

    source_id: str
    against_id: str
    comparable: bool
    shared_modes: tuple[str, ...]
    missing_modes: tuple[str, ...]
    blocking_modes: tuple[str, ...]
    remediation_minutes: float | None
    remediation_material: float | None
    remediation_cost: float | None
    verdict: str


def compare_coverage(
    *,
    source: NeckSource,
    against: NeckSource,
    taxonomy: tuple[DefectMode, ...],
    labour_rate: float,
) -> CoverageComparison:
    """Ask what `source` would need to match `against`.

    The interesting answer is not a number. If any mode `against` addresses is
    non-remediable and `source` leaves it open, no amount of rework reaches
    parity and the honest output is a refusal with the blockers named.
    """
    by_id = {d.defect_id: d for d in taxonomy}
    for holder in (source, against):
        unknown = sorted(holder.addresses - set(by_id))
        if unknown:
            raise ValueError(f"{holder.source_id} addresses unknown modes: {unknown}")

    missing = tuple(sorted(against.addresses - source.addresses))
    shared = tuple(sorted(source.addresses & against.addresses))
    blocking = tuple(m for m in missing if not by_id[m].remediable)

    if blocking:
        return CoverageComparison(
            source_id=source.source_id,
            against_id=against.source_id,
            comparable=False,
            shared_modes=shared,
            missing_modes=missing,
            blocking_modes=blocking,
            remediation_minutes=None,
            remediation_material=None,
            remediation_cost=None,
            verdict=(
                f"NOT COMPARABLE. {len(blocking)} defect mode(s) cannot be closed by "
                f"any spend: {', '.join(blocking)}. Cost parity is unpurchasable, so "
                f"no remediation figure is reported."
            ),
        )

    # Remediation prices, NOT prevention prices. The gap between them is the
    # whole reason buying-then-fixing loses to building correctly.
    minutes = sum(by_id[m].remediation_minutes for m in missing)
    material = sum(by_id[m].remediation_material for m in missing)
    cost = as_money(minutes / 60.0 * labour_rate + material)
    verdict = (
        f"Comparable after remediation: {round(minutes, 1)} labour minutes and "
        f"{as_money(material)} of material, {cost} in total."
        if missing
        else "Coverage matches; these two may be compared on cost directly."
    )
    return CoverageComparison(
        source_id=source.source_id,
        against_id=against.source_id,
        comparable=True,
        shared_modes=shared,
        missing_modes=missing,
        blocking_modes=(),
        remediation_minutes=round(minutes, 1),
        remediation_material=as_money(material),
        remediation_cost=cost,
        verdict=verdict,
    )


@dataclass(frozen=True)
class CoverageProfile:
    """What one source's coverage costs, split by what removes each defect."""

    source_id: str
    modes_addressed: int
    modes_open: int
    free_modes: int
    process_cost: float
    specification_cost: float
    labour_cost: float
    labour_minutes: float
    total_cost: float
    latent_open: tuple[str, ...]
    non_remediable_open: tuple[str, ...]


@dataclass(frozen=True)
class VerifiabilityProfile:
    """How much of the yardstick can actually be RUN against one source.

    This is the make-or-buy comparison the cost model could not make. Both
    sources are measured against the same criteria, and the difference is not
    that one scores worse — it is that most of the criteria cannot be applied to
    a purchased neck at all. Evidence that is buried under a glued fretboard is
    not evidence you can weigh against a price.

    `unverifiable_and_irrecoverable` is the pointed number: criteria you cannot
    check on arrival AND cannot fix once the fault shows itself. Those are the
    modes that reach a customer with your name on the headstock.
    """

    source_id: str
    arrival_stage: str
    criteria_total: int
    verifiable: tuple[str, ...]
    unverifiable: tuple[str, ...]
    unverifiable_and_irrecoverable: tuple[str, ...]
    verifiable_fraction: float
    note: str


def verifiability_profile(
    *,
    source: NeckSource,
    criteria: tuple[AcceptanceCriterion, ...],
    taxonomy: tuple[DefectMode, ...],
) -> VerifiabilityProfile:
    """Which criteria this shop can still run, given where the neck arrives.

    A criterion is runnable only if its stage is at or after the point the neck
    came under this shop's control. Earlier stages happened somewhere else, to
    somebody else's standard, with no record.
    """
    by_id = {d.defect_id: d for d in taxonomy}
    arrival = GATE_STAGES.index(source.arrival_stage)

    runnable: list[str] = []
    buried: list[str] = []
    for c in criteria:
        (runnable if GATE_STAGES.index(c.stage) >= arrival else buried).append(c.defect_id)

    blind = tuple(sorted(d for d in buried if not by_id[d].remediable))
    total = len(criteria)
    return VerifiabilityProfile(
        source_id=source.source_id,
        arrival_stage=source.arrival_stage,
        criteria_total=total,
        verifiable=tuple(sorted(runnable)),
        unverifiable=tuple(sorted(buried)),
        unverifiable_and_irrecoverable=blind,
        verifiable_fraction=round(len(runnable) / total, 4) if total else 0.0,
        note=(
            f"Arrives at {source.arrival_stage}. {len(runnable)} of {total} criteria "
            f"can be run; {len(buried)} describe stages that already happened "
            f"elsewhere. Of those, {len(blind)} are also irrecoverable, so they can "
            f"neither be found on arrival nor fixed afterwards."
        ),
    )


@dataclass(frozen=True)
class GateEconomics:
    """What gating one mode early is worth, against letting it escape."""

    defect_id: str
    stage: str
    value_at_risk_at_gate: float
    value_at_risk_if_escaped: float
    saving_per_catch: float
    is_ungated: bool
    escapes_to_service: bool
    note: str


def gate_economics(
    *,
    mode: DefectMode,
    criterion: AcceptanceCriterion | None,
    stage_values: dict[str, float],
    finished_value: float,
) -> GateEconomics:
    """Price the decision of WHERE to inspect for one defect mode.

    A mode with no criterion is not gated at all. It does not get a saving of
    zero — it gets flagged, because an ungated latent mode is the one that
    reaches a customer, and a yield figure computed without it is measuring
    only the defects somebody happened to look for.
    """
    if criterion is None:
        return GateEconomics(
            defect_id=mode.defect_id,
            stage="UNGATED",
            value_at_risk_at_gate=finished_value,
            value_at_risk_if_escaped=finished_value,
            saving_per_catch=0.0,
            is_ungated=True,
            escapes_to_service=mode.visibility == VISIBILITY_LATENT,
            note="No acceptance criterion, so nothing catches this mode. It cannot "
            "appear in a yield figure, which means the yield figure is an "
            "undercount of the ways a neck can be wrong.",
        )

    at_gate = stage_values.get(criterion.stage, finished_value)
    escaped = finished_value
    return GateEconomics(
        defect_id=mode.defect_id,
        stage=criterion.stage,
        value_at_risk_at_gate=as_money(at_gate),
        value_at_risk_if_escaped=as_money(escaped),
        saving_per_catch=as_money(escaped - at_gate),
        is_ungated=False,
        escapes_to_service=False,
        note=(
            f"Judged at {criterion.stage}, so a rejection costs {as_money(at_gate)} "
            f"rather than {as_money(escaped)}."
        ),
    )


def profile_source(
    *,
    source: NeckSource,
    taxonomy: tuple[DefectMode, ...],
    labour_rate: float,
) -> CoverageProfile:
    """Split a source's quality spend by elimination class.

    The split is the point. Everything under PROCESS is coverage the source
    gets for free, and a shop whose free column is large is competing on
    something an hourly rate cannot erode.
    """
    addressed = [d for d in taxonomy if d.defect_id in source.addresses]
    open_modes = source.open_modes(taxonomy)

    def _spend(kind: str) -> float:
        return as_money(sum(d.cost(labour_rate) for d in addressed if d.elimination == kind))

    labour_minutes = sum(
        d.labour_minutes for d in addressed if d.elimination == ELIMINATION_LABOUR
    )
    process = _spend(ELIMINATION_PROCESS)
    spec = _spend(ELIMINATION_SPECIFICATION)
    labour = _spend(ELIMINATION_LABOUR)
    return CoverageProfile(
        source_id=source.source_id,
        modes_addressed=len(addressed),
        modes_open=len(open_modes),
        free_modes=sum(1 for d in addressed if d.elimination == ELIMINATION_PROCESS),
        process_cost=process,
        specification_cost=spec,
        labour_cost=labour,
        labour_minutes=round(labour_minutes, 1),
        total_cost=as_money(process + spec + labour),
        latent_open=tuple(
            d.defect_id for d in open_modes if d.visibility == VISIBILITY_LATENT
        ),
        non_remediable_open=tuple(d.defect_id for d in open_modes if not d.remediable),
    )
