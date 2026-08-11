"""Candidate scoring for the Musical Spatial Mapping Engine.

Dev Order: MSME-002 Phase C

Scoring turns ``PositionCandidate(score=None)`` into
``PositionCandidate(score=CandidateScore(...))`` and does nothing else. It never
adds, removes, reorders or filters candidates: a location that scores appallingly
is still a location, and deleting it here would let a preference silently change
what the engine believes is playable. Generation decides what exists; scoring
decides only what it costs.

**Every component is a cost, and the lowest total wins.** The engine never
reports an opaque number — each contribution is named in ``CandidateScore``
components, and an ordered explanation is retained, so a later stage can say why
one location outranked another instead of asserting that it did.

One documented exception to "every contribution is a penalty".
``MappingPreferences.lower_position_bias`` is described by MSME-001 as "an
intentionally signed bias", and ``validate_mapping_preferences`` enforces
non-negativity on the other five weights while requiring only that the bias be
finite. A negative bias therefore contributes a NEGATIVE cost and a total may go
below zero. That is the shipped contract, so it is honoured rather than silently
clamped; see ``lower_position_bias`` below.

Movement is measured with the NORMALIZED coordinate, never fret numbers and
never millimetres. Fret numbers do not exist on a fretless instrument.
Millimetres would make the same musical movement cost roughly six hundred times
more on a profile that happens to declare its scale length than on one that does
not, which would let a documentation detail dominate a musical judgement.
"""

from __future__ import annotations

import math

from .candidates import playable_units, unit_index_of
from .enums import OpenStringPolicy
from .models import (
    CandidateScore,
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    PositionCandidate,
    SpatialPosition,
)

# Component names are a public contract: they appear in CandidateScore.components
# and in serialized results, so they live here rather than as scattered literals.
MOVEMENT = "movement"
STRING_CHANGE = "string_change"
POSITION = "position"
PREFERRED_REGION = "preferred_region"
OPEN_STRING = "open_string"
LOWER_POSITION_BIAS = "lower_position_bias"

# Fixed order, so components and explanations are byte-identical run to run.
COMPONENT_ORDER: tuple[str, ...] = (
    MOVEMENT,
    STRING_CHANGE,
    POSITION,
    PREFERRED_REGION,
    OPEN_STRING,
    LOWER_POSITION_BIAS,
)


def _movement_cost(
    position: SpatialPosition,
    previous_position: SpatialPosition | None,
    weight: float,
) -> tuple[float, str | None]:
    """How far the hand travelled along the neck, as normalized fretboard distance.

    With no previous position there is no distance to travel and the cost is
    exactly zero — not a small number, and not an assumption that the hand
    started at the nut.
    """
    if previous_position is None or weight == 0.0:
        return 0.0, None
    travelled = abs(
        position.physical.normalized_position - previous_position.physical.normalized_position
    )
    cost = weight * travelled
    if cost == 0.0:
        return 0.0, None
    return cost, f"moved {travelled:.4f} of the scale length from the previous position"


def _string_change_cost(
    position: SpatialPosition,
    previous_position: SpatialPosition | None,
    profile: InstrumentProfile,
    weight: float,
) -> tuple[float, str | None]:
    """Cost of crossing to a different playable unit.

    Charged once for changing units rather than scaled by how many units were
    crossed: how FAR the crossing went is governed by ``maximum_string_jump``,
    which is a hard constraint in generation and deliberately never a weight.
    Comparison is by playable unit, so moving between the two wires of one
    mandolin course is not a string change — the player never moved.
    """
    if previous_position is None or weight == 0.0:
        return 0.0, None
    units = playable_units(profile)
    here = unit_index_of(units, position)
    before = unit_index_of(units, previous_position)
    if here is None or before is None or here == before:
        return 0.0, None
    return weight, f"changed playable unit from index {before} to {here}"


def _position_cost(position: SpatialPosition, weight: float) -> tuple[float, str | None]:
    """Cost of playing further from the nut, as a normalized fraction.

    Uses the PHYSICAL coordinate: this is where the hand actually sits on the
    neck, which is what makes a position awkward, and it stays true under a capo.
    """
    if weight == 0.0:
        return 0.0, None
    cost = weight * position.physical.normalized_position
    if cost == 0.0:
        return 0.0, None
    return cost, f"sits {position.physical.normalized_position:.4f} of the way up the neck"


def _preferred_region_cost(
    position: SpatialPosition,
    constraints: MappingConstraints,
    weight: float,
) -> tuple[float, str | None]:
    """Cost of falling outside the caller's preferred region, in semitones.

    A miss is a PENALTY and never a rejection: the candidate stays in the set and
    can still win if everything else is worse. Measured against the playing
    offset, because the preferred region is expressed from the effective open
    string exactly as the hard window is.
    """
    if weight == 0.0:
        return 0.0, None
    offset = position.playing.semitone_offset_from_open
    low = constraints.preferred_minimum_position
    high = constraints.preferred_maximum_position
    if low is not None and offset < low:
        outside = low - offset
        return weight * outside, f"{outside:.2f} semitones below the preferred region"
    if high is not None and offset > high:
        outside = offset - high
        return weight * outside, f"{outside:.2f} semitones above the preferred region"
    return 0.0, None


def _open_string_cost(
    position: SpatialPosition,
    constraints: MappingConstraints,
    weight: float,
) -> tuple[float, str | None]:
    """Cost applied by the open-string policy.

    PREFER charges every FRETTED location, so open strings win by costing less.
    AVOID charges every open location. ALLOW charges nothing, and EXCLUDE never
    reaches scoring because generation already removed those candidates.
    """
    if weight == 0.0:
        return 0.0, None
    policy = constraints.open_string_policy
    is_open = position.playing.is_open
    if policy is OpenStringPolicy.PREFER and not is_open:
        return weight, "fretted, where the policy prefers open strings"
    if policy is OpenStringPolicy.AVOID and is_open:
        return weight, "open, where the policy avoids open strings"
    return 0.0, None


def _lower_position_bias_cost(
    position: SpatialPosition, bias: float
) -> tuple[float, str | None]:
    """The one signed term.

    MSME-001 calls this "an intentionally signed bias" and its validator requires
    only that it be finite, so a negative value is legal and makes higher
    positions CHEAPER. Honoured as specified rather than clamped: silently
    forcing it non-negative would delete a documented capability, and a caller
    who sets a negative bias has asked for exactly this.
    """
    if bias == 0.0:
        return 0.0, None
    cost = bias * position.physical.normalized_position
    if cost == 0.0:
        return 0.0, None
    direction = "penalises" if bias > 0 else "rewards"
    return cost, f"bias {direction} distance from the nut ({cost:+.4f})"


def score_candidate(
    *,
    candidate: PositionCandidate,
    profile: InstrumentProfile,
    constraints: MappingConstraints | None = None,
    preferences: MappingPreferences | None = None,
    previous_position: SpatialPosition | None = None,
) -> PositionCandidate:
    """Return a copy of ``candidate`` carrying its ``CandidateScore``.

    The input candidate is never mutated — every model here is a frozen
    dataclass and this returns a new one, so a caller keeping the unscored set
    still has it.
    """
    constraints = constraints or MappingConstraints()
    preferences = preferences or MappingPreferences()
    position = candidate.position

    raw: dict[str, tuple[float, str | None]] = {
        MOVEMENT: _movement_cost(position, previous_position, preferences.movement_weight),
        STRING_CHANGE: _string_change_cost(
            position, previous_position, profile, preferences.string_change_weight
        ),
        POSITION: _position_cost(position, preferences.position_weight),
        PREFERRED_REGION: _preferred_region_cost(
            position, constraints, preferences.preferred_region_weight
        ),
        OPEN_STRING: _open_string_cost(position, constraints, preferences.open_string_weight),
        LOWER_POSITION_BIAS: _lower_position_bias_cost(
            position, preferences.lower_position_bias
        ),
    }

    # Every component is present even at zero, so consumers can rely on the shape
    # and a missing key always means a bug rather than an absent penalty.
    components = {name: raw[name][0] for name in COMPONENT_ORDER}
    explanation = tuple(
        f"{name}: {raw[name][1]}" for name in COMPONENT_ORDER if raw[name][1] is not None
    )
    return PositionCandidate(
        position=position,
        score=CandidateScore(
            # math.fsum, not sum(): CPython 3.12 switched sum() to Neumaier
            # compensated summation for floats, so the same components produce a
            # different last bit on 3.11 than on 3.12+. That is invisible until a
            # score is compared against a stored one, at which point a golden
            # vector recorded on one interpreter fails on another. fsum is
            # exactly rounded, so every version and platform agrees.
            total=math.fsum(components.values()),
            components=components,
            explanation=explanation,
        ),
    )


def score_candidates(
    *,
    candidates: tuple[PositionCandidate, ...],
    profile: InstrumentProfile,
    constraints: MappingConstraints | None = None,
    preferences: MappingPreferences | None = None,
    previous_position: SpatialPosition | None = None,
) -> tuple[PositionCandidate, ...]:
    """Score every candidate, preserving count and order exactly.

    Ranking is Phase D. Returning the set in its generated order keeps this stage
    honest: if scoring also sorted, a caller could not tell whether a change in
    output came from the scores or from the candidate set itself.
    """
    return tuple(
        score_candidate(
            candidate=candidate,
            profile=profile,
            constraints=constraints,
            preferences=preferences,
            previous_position=previous_position,
        )
        for candidate in candidates
    )
