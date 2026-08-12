"""Deterministic selection among scored candidates.

Dev Order: MSME-002 Phase D

Selection answers "which of these equally-known locations do we hand back?" and
nothing else. It does not annotate, does not build a ``MappingResult``, and does
not decide that a pitch is unplayable — an empty candidate set means orchestration
skipped the branch that produces ``SelectionStatus.UNPLAYABLE``, so selection
refuses rather than inventing an incomplete pseudo-result.

**Ambiguity is decided before tie-breaking, and tie-breaking never undoes it.**
The equal-best set is every candidate sharing the exact minimum total. If more
than one candidate is in it the outcome is ambiguous, and it stays ambiguous even
though a winner is still chosen: the tie-break makes the answer REPEATABLE, not
unique. Collapsing those two ideas would let the engine claim confidence it does
not have.

Exact equality is used deliberately rather than a tolerance. Ties in this model
arise from components that are genuinely identical — a binary string-change
charge, a zeroed weight, two terms that cancel — not from accumulated drift.
Probing every shipped profile across default, position-only, string-change-only
and deliberately cancelling weight sets produced many exact ties and not one pair
that differed by less than 1e-9 without being equal. A tolerance would add a
tuning constant to the behavioural contract and buy nothing.

The tie-break is SEMANTIC. It deliberately does not use ``display_order``, which
is presentation metadata carrying an unenforced convention: the shipped profiles
number the highest-pitched unit first, other profiles need not, and a profile
numbering the other way would silently invert every tie.
"""

from __future__ import annotations

from dataclasses import dataclass

from .candidates import playable_units, unit_index_of
from .errors import SelectionInputError
from .models import InstrumentProfile, PositionCandidate, SpatialPosition

# Ordered, documented, and total. Each key states its own direction; the final
# identifier is unique per playable unit, so the ordering never falls through to
# insertion order, object identity, or position in the source list.
TIE_BREAK_KEYS: tuple[str, ...] = (
    "total score, ascending",
    "open pitch of the playable unit, descending",
    "normalized physical position, ascending",
    "stable playable-unit identifier, ascending",
)


@dataclass(frozen=True)
class SelectionOutcome:
    """The result of choosing among scored candidates.

    Deliberately NOT a ``MappingResult`` and deliberately carrying no status
    enum of its own. Phase F maps ``is_ambiguous`` onto the existing
    ``SelectionStatus.SELECTED`` / ``AMBIGUOUS``; duplicating the public domain
    result here would create a second contract to keep in step with the first.

    ``equal_best`` is the complete set sharing the minimum total, winner
    included. Reporting ambiguity without saying WHICH candidates tied would
    leave a caller unable to act on it.
    """

    winner: PositionCandidate
    equal_best: tuple[PositionCandidate, ...]
    is_ambiguous: bool


def unit_identity(position: SpatialPosition) -> str:
    """Stable identifier for the playable unit a position sits on.

    ``course_id`` when the profile declares one, so the paired wires of a course
    never compete against each other as if they were separate choices.
    """
    return position.course_id if position.course_id is not None else position.string_id


def _open_pitch(profile: InstrumentProfile, position: SpatialPosition) -> int:
    """Open pitch of the position's playable unit, from the profile.

    Read from the declared unit rather than recomputed from the sounding pitch
    minus the offset: the profile is authoritative about what a course is tuned
    to, and course membership comes from ``course_id``, never from strings
    happening to share a pitch.
    """
    units = playable_units(profile)
    index = unit_index_of(units, position)
    if index is None:
        # A position whose unit is not in this profile cannot be ordered against
        # ones that are. Sorting it last keeps the comparison total instead of
        # raising in the middle of a sort.
        return -1
    return units[index].open_midi_note


def _tie_break_key(
    profile: InstrumentProfile, candidate: PositionCandidate
) -> tuple[float, int, float, str]:
    position = candidate.position
    assert candidate.score is not None  # guaranteed by _require_scored
    return (
        candidate.score.total,
        -_open_pitch(profile, position),
        position.physical.normalized_position,
        unit_identity(position),
    )


def _require_scored(candidates: tuple[PositionCandidate, ...]) -> None:
    if not candidates:
        raise SelectionInputError(
            "selection requires a non-empty candidate set; an empty one means the "
            "caller skipped the branch that reports SelectionStatus.UNPLAYABLE, and "
            "selection must not manufacture that outcome itself"
        )
    for index, candidate in enumerate(candidates):
        if candidate.score is None:
            raise SelectionInputError(
                f"candidate {index} on {unit_identity(candidate.position)!r} arrived "
                f"unscored; Phase D consumes scored candidates and an unscored one is "
                f"a pipeline error, not a musical outcome"
            )


def select_candidate(
    *,
    candidates: tuple[PositionCandidate, ...],
    profile: InstrumentProfile,
) -> SelectionOutcome:
    """Choose deterministically among scored candidates.

    The equal-best set is formed on total score alone and on exact equality. The
    tie-break then orders that set by open pitch descending, normalized position
    ascending, and stable unit identifier ascending — a total order over already
    governed data, so the same input always yields the same winner regardless of
    the order the candidates arrive in.
    """
    _require_scored(candidates)

    best_total = min(c.score.total for c in candidates if c.score is not None)
    equal_best = tuple(
        c for c in candidates if c.score is not None and c.score.total == best_total
    )

    # Ambiguity is a property of the SCORES, decided here and never revisited.
    # The tie-break below picks a repeatable winner; it does not resolve the tie.
    is_ambiguous = len(equal_best) > 1

    # Sorted once and reused: the winner is simply the first of the tie-broken
    # order, so the reported set and the chosen candidate cannot disagree.
    ordered = tuple(sorted(equal_best, key=lambda c: _tie_break_key(profile, c)))
    return SelectionOutcome(
        winner=ordered[0], equal_best=ordered, is_ambiguous=is_ambiguous
    )
