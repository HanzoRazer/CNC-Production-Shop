"""The public spatial mapping facade.

Dev Order: MSME-002 Phase F

Assembles stages that were each characterized on their own::

    validate -> generate -> score -> select -> annotate -> MappingResult

and introduces no policy of its own. No scoring rule, no candidate semantics, no
annotation vocabulary lives here; if a behaviour is not visible in one of those
modules it is not happening.

**The mapper is stateless, and the type system enforces it.** It is a frozen
dataclass, so it cannot cache a last result or accumulate a prior position even
by accident. ``previous_position`` is an explicit argument to every call. A
sequence mapper is a loop over this method, feeding the previous selection
forward; that loop belongs to a later order and deliberately not here.

Orchestration owns exactly one decision the stages refuse to make: whether the
pitch is playable at all. Generation reports what it rejected and why, and this
module turns "nothing survived" into ``SelectionStatus.UNPLAYABLE`` **without
calling selection**, which is why selection is free to treat an empty candidate
set as a programming error.

A valid event on a valid profile with nowhere to go is an OUTCOME here, never an
``UnsupportedPitchError``. That exception is reserved for input that cannot be
interpreted at all, and the distinction is pinned by a test at this boundary
because this is where a caller actually feels it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .annotation import annotate
from .candidates import CandidateRejection, generate_candidates
from .enums import SelectionStatus
from .models import (
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    MappingResult,
    MusicalEvent,
    PositionCandidate,
    SpatialPosition,
)
from .scoring import score_candidates
from .selection import select_candidate
from .validation import (
    validate_instrument_profile,
    validate_mapping_constraints,
    validate_mapping_preferences,
    validate_musical_event,
)


def _rejection_lines(rejections: tuple[CandidateRejection, ...]) -> tuple[str, ...]:
    """Rejection evidence as diagnostics.

    An UNPLAYABLE result that says only "none" is useless to whoever has to fix
    it. These lines say which unit failed, under which category, and why — so a
    caller can tell "your capo is in the way" from "this neck is too short".
    """
    return tuple(
        f"{r.code.value}: {r.unit_id} ({', '.join(r.string_ids)}) — {r.detail}"
        for r in rejections
    )


@dataclass(frozen=True)
class MusicalSpatialMapper:
    """Maps canonical musical events onto playable spatial locations.

    Holds configuration — the instrument and the caller's constraints and
    preferences — and no evolving state. Frozen on purpose: a mapper that could
    remember its last answer would make identical calls stop returning identical
    results, and sequence behaviour would appear without anyone asking for it.
    """

    profile: InstrumentProfile
    constraints: MappingConstraints = field(default_factory=MappingConstraints)
    preferences: MappingPreferences = field(default_factory=MappingPreferences)

    def map(
        self,
        event: MusicalEvent,
        *,
        previous_position: SpatialPosition | None = None,
    ) -> MappingResult:
        """Map one event. Same inputs always produce the same result.

        ``previous_position`` is the only way movement and string-change costs
        enter, and the only way ``maximum_string_jump`` becomes active. Passing
        None is the ordinary single-note case and costs nothing extra.
        """
        # Fail closed before computing anything: a malformed profile or event is
        # a caller error and must not be answered with a plausible-looking map.
        validate_musical_event(event)
        validate_instrument_profile(self.profile)
        validate_mapping_constraints(self.profile, self.constraints)
        validate_mapping_preferences(self.preferences)

        generated = generate_candidates(
            event=event,
            profile=self.profile,
            constraints=self.constraints,
            previous_position=previous_position,
        )
        diagnostics = _rejection_lines(generated.rejections)

        if not generated.candidates:
            # The one branch orchestration owns. Selection is never called, which
            # is what lets it treat an empty set as a programming error.
            return MappingResult(
                event=event,
                instrument_id=self.profile.instrument_id,
                status=SelectionStatus.UNPLAYABLE,
                candidates=(),
                selected=None,
                annotation=None,
                diagnostics=diagnostics,
            )

        scored = score_candidates(
            candidates=generated.candidates,
            profile=self.profile,
            constraints=self.constraints,
            preferences=self.preferences,
            previous_position=previous_position,
        )
        outcome = select_candidate(candidates=scored, profile=self.profile)

        if outcome.is_ambiguous:
            # The equal-best set is recoverable from `candidates` by filtering on
            # the winning total, since every candidate here is scored. Naming it
            # explicitly saves every consumer from rediscovering that.
            diagnostics = diagnostics + (
                f"ambiguous: {len(outcome.equal_best)} candidates tie at "
                f"{outcome.winner.score.total if outcome.winner.score else 0.0}; "
                f"chose {', '.join(c.position.string_id for c in outcome.equal_best)}"
                f" in tie-break order",
            )

        return MappingResult(
            event=event,
            instrument_id=self.profile.instrument_id,
            status=(
                SelectionStatus.AMBIGUOUS if outcome.is_ambiguous else SelectionStatus.SELECTED
            ),
            candidates=scored,
            selected=outcome.winner,
            annotation=annotate(position=outcome.winner.position, profile=self.profile),
            diagnostics=diagnostics,
        )


def equal_best_of(result: MappingResult) -> tuple[PositionCandidate, ...]:
    """The candidates that tied for best in a finished result.

    ``MappingResult`` has no dedicated field for the tied set, and it does not
    need one: every candidate it carries is scored, so the set is exactly those
    matching the selected candidate's total. Provided as a helper rather than a
    new field so no parallel result type appears.
    """
    if result.selected is None or result.selected.score is None:
        return ()
    best = result.selected.score.total
    return tuple(
        c for c in result.candidates if c.score is not None and c.score.total == best
    )
