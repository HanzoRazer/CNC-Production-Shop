"""Candidate generation for the Musical Spatial Mapping Engine.

Dev Order: MSME-002 Phase B

This module answers one question and refuses to answer any other: *where could
this pitch be played on this instrument?* It ranks nothing and selects nothing.
Generation and selection are separate operations, so a later change to scoring
policy can never quietly change which locations were considered to exist.

A candidate is a **distinct playable musical choice, not a distinct physical
component.** That distinction is the whole reason this module groups strings into
playable units before doing any arithmetic: a mandolin has eight strings but only
four things a player can independently finger, and emitting eight candidates for
a note would invent four choices the musician does not have.

Course membership is read from ``StringProfile.course_id`` and is never inferred
from strings happening to share an open pitch. Two strings tuned alike are not
evidence of a mechanical course; only the profile can say that.

Rejections are recorded rather than discarded. An unplayable pitch should be able
to tell its caller *why* every location failed, not merely that none survived.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .enums import FingerboardMode, OpenStringPolicy, RejectionCode
from .geometry import POSITION_EPSILON, distance_from_nut_mm, normalized_position_for_semitones
from .models import (
    InstrumentProfile,
    MappingConstraints,
    MusicalEvent,
    PhysicalPosition,
    PlayingPosition,
    PositionCandidate,
    SoundingPitch,
    SpatialPosition,
    StringProfile,
)
from .pitch import pitch_distance_semitones

# Frets are whole numbers; a required offset this far from an integer cannot be
# produced by a fixed fret. Shared with geometry so the whole engine agrees on
# when two positions coincide.
_EPS = POSITION_EPSILON


@dataclass(frozen=True)
class PlayableUnit:
    """One independently fingerable location group on the instrument.

    On a guitar this is a single string. On a mandolin it is a course: two wires
    fretted together by one finger, which the player cannot address separately.
    ``member_strings`` keeps the physical identity so annotation can still say
    which wires sound, without generation pretending they were separate choices.
    """

    unit_id: str
    course_id: str | None
    member_strings: tuple[StringProfile, ...]
    open_midi_note: int
    display_order: int
    max_position: float | None

    @property
    def representative(self) -> StringProfile:
        """The lowest-ordered member, used for the candidate's string identity."""
        return self.member_strings[0]

    @property
    def string_ids(self) -> tuple[str, ...]:
        return tuple(s.string_id for s in self.member_strings)


@dataclass(frozen=True)
class CandidateRejection:
    """Why one playable unit could not host this pitch.

    Deliberately local to generation rather than added to ``models``: this is
    evidence about one attempt, not a domain contract competing with the existing
    ones. The facade folds these into ``MappingResult.diagnostics``.
    """

    unit_id: str
    string_ids: tuple[str, ...]
    code: RejectionCode
    detail: str


@dataclass(frozen=True)
class GenerationOutcome:
    """Everything generation learned: what survived, and why the rest did not."""

    candidates: tuple[PositionCandidate, ...]
    rejections: tuple[CandidateRejection, ...]


def playable_units(profile: InstrumentProfile) -> tuple[PlayableUnit, ...]:
    """Group a profile's strings into independently playable units.

    Strings sharing a ``course_id`` collapse into one unit; a string with no
    ``course_id`` is its own unit. Ordering is by the lowest ``display_order`` in
    the group, so the result is deterministic regardless of how the profile lists
    its strings.

    A course adopts the MOST RESTRICTIVE ``max_position`` of its members: the
    finger stops where the shortest playable wire stops.
    """
    grouped: dict[str, list[StringProfile]] = {}
    order: list[str] = []
    for string in profile.strings:
        # A course is only a course when the profile says so. Equal open pitch is
        # not proof: two strings can be tuned in unison and still be fingered
        # independently, and treating them as one would silently delete a choice.
        key = f"course:{string.course_id}" if string.course_id else f"string:{string.string_id}"
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(string)

    units: list[PlayableUnit] = []
    for key in order:
        members = tuple(sorted(grouped[key], key=lambda s: (s.display_order, s.string_id)))
        caps = [s.max_position for s in members if s.max_position is not None]
        units.append(
            PlayableUnit(
                unit_id=key,
                course_id=members[0].course_id,
                member_strings=members,
                open_midi_note=members[0].open_midi_note,
                display_order=members[0].display_order,
                max_position=min(caps) if caps else None,
            )
        )
    return tuple(sorted(units, key=lambda u: (u.display_order, u.unit_id)))


def _identity_permits(unit: PlayableUnit, constraints: MappingConstraints) -> bool:
    """True when at least one member wire is enabled and permitted.

    Constraints name STRINGS while a course is played as a whole, so a course
    survives if any member is permitted. Excluding one wire of an inseparable
    pair cannot make the pair unplayable — the finger still lands there.
    """
    for string in unit.member_strings:
        if not string.enabled:
            continue
        if string.string_id in constraints.excluded_string_ids:
            continue
        if (
            constraints.allowed_string_ids is not None
            and string.string_id not in constraints.allowed_string_ids
        ):
            continue
        return True
    return False


def _course_index(profile: InstrumentProfile, unit: PlayableUnit) -> int:
    """Position of this unit in playing order, for string-jump measurement."""
    return [u.unit_id for u in playable_units(profile)].index(unit.unit_id)


def generate_candidates(
    *,
    event: MusicalEvent,
    profile: InstrumentProfile,
    constraints: MappingConstraints | None = None,
    previous_position: SpatialPosition | None = None,
) -> GenerationOutcome:
    """Every location at which ``event`` can be played on ``profile``.

    Hard constraints reject; soft preferences do not appear here at all. The
    returned candidates carry ``score=None`` — scoring is Phase C, and a caller
    that receives an unscored candidate set has been told the truth about what
    this stage knows.

    ``previous_position`` participates only through ``maximum_string_jump``, which
    is a hard limit rather than a weight. With no previous position there is no
    jump to measure and the limit is inert.
    """
    constraints = constraints or MappingConstraints()
    capo = float(constraints.capo_fret)
    fretted = profile.fingerboard_mode is FingerboardMode.FRETTED

    candidates: list[PositionCandidate] = []
    rejections: list[CandidateRejection] = []
    units = playable_units(profile)

    previous_index: int | None = None
    if previous_position is not None and constraints.maximum_string_jump is not None:
        for index, unit in enumerate(units):
            same_course = (
                previous_position.course_id is not None
                and unit.course_id == previous_position.course_id
            )
            if same_course or previous_position.string_id in unit.string_ids:
                previous_index = index
                break

    for index, unit in enumerate(units):
        reject = _make_rejector(unit, rejections)

        # A course whose wires disagree about their open pitch is a broken
        # profile. Say so rather than silently adopting one member's tuning.
        if len({s.open_midi_note for s in unit.member_strings}) > 1:
            reject(
                RejectionCode.PROFILE_INVALID,
                f"course {unit.course_id!r} has members tuned to different open "
                f"pitches, so it has no single open pitch to measure from",
            )
            continue

        if not _identity_permits(unit, constraints):
            reject(RejectionCode.STRING_EXCLUDED, "no member string is enabled and permitted")
            continue

        # Physical position is measured FROM THE NUT and knows nothing about a
        # capo; playing position is measured from the effective open string.
        # These are computed separately on purpose and never derived from one
        # another by a single integer.
        offset_from_nut = pitch_distance_semitones(
            unit.open_midi_note, event.midi_note, event.cents_offset
        )
        if offset_from_nut < -_EPS:
            reject(
                RejectionCode.BELOW_OPEN_PITCH,
                f"pitch is {abs(offset_from_nut):.2f} semitones below the open string",
            )
            continue

        offset_from_open = offset_from_nut - capo
        if offset_from_open < -_EPS:
            reject(
                RejectionCode.CAPO_CONFLICT,
                f"pitch lies under the capo at fret {constraints.capo_fret}; the string "
                f"cannot sound it while clamped",
            )
            continue

        if fretted and abs(offset_from_nut - round(offset_from_nut)) > _EPS:
            reject(
                RejectionCode.PITCH_NOT_REALIZABLE,
                f"a fixed-fret instrument cannot produce an offset of "
                f"{offset_from_nut:.4f} semitones",
            )
            continue

        if profile.fret_count is not None and offset_from_nut > profile.fret_count + _EPS:
            reject(
                RejectionCode.ABOVE_POSITION_RANGE,
                f"fret {offset_from_nut:.2f} is beyond the {profile.fret_count}-fret neck",
            )
            continue

        if unit.max_position is not None and offset_from_nut > unit.max_position + _EPS:
            reject(
                RejectionCode.ABOVE_POSITION_RANGE,
                f"offset {offset_from_nut:.2f} exceeds the unit's playable maximum "
                f"{unit.max_position}",
            )
            continue

        # Constraint window is expressed from the EFFECTIVE open string, per
        # MappingConstraints. Compare against the playing offset, not the nut one.
        #
        # Both bounds report POSITION_CONSTRAINT, never the instrument-range
        # codes above. The location IS playable; the caller's own window ruled it
        # out, and an UNPLAYABLE result has to be able to tell those apart.
        if (
            constraints.minimum_position is not None
            and offset_from_open < constraints.minimum_position - _EPS
        ):
            reject(
                RejectionCode.POSITION_CONSTRAINT,
                f"playing offset {offset_from_open:.2f} is below the caller's minimum "
                f"{constraints.minimum_position}",
            )
            continue

        if (
            constraints.maximum_position is not None
            and offset_from_open > constraints.maximum_position + _EPS
        ):
            reject(
                RejectionCode.POSITION_CONSTRAINT,
                f"playing offset {offset_from_open:.2f} is above the caller's maximum "
                f"{constraints.maximum_position}",
            )
            continue

        is_open = abs(offset_from_open) <= _EPS
        if is_open and constraints.open_string_policy is OpenStringPolicy.EXCLUDE:
            # PREFER and AVOID are scoring weights, not rejections; only EXCLUDE
            # removes the location from consideration.
            reject(RejectionCode.OPEN_STRING_EXCLUDED, "open-string policy excludes open positions")
            continue

        if previous_index is not None and constraints.maximum_string_jump is not None:
            jump = abs(index - previous_index)
            if jump > constraints.maximum_string_jump:
                reject(
                    RejectionCode.STRING_EXCLUDED,
                    f"a jump of {jump} playing units exceeds the maximum of "
                    f"{constraints.maximum_string_jump}",
                )
                continue

        candidates.append(
            PositionCandidate(
                position=_build_position(
                    event=event,
                    unit=unit,
                    profile=profile,
                    fretted=fretted,
                    offset_from_nut=offset_from_nut,
                    offset_from_open=offset_from_open,
                    is_open=is_open,
                ),
                score=None,
            )
        )

    return GenerationOutcome(candidates=tuple(candidates), rejections=tuple(rejections))


def _make_rejector(
    unit: PlayableUnit, sink: list[CandidateRejection]
) -> Callable[[RejectionCode, str], None]:
    def reject(code: RejectionCode, detail: str) -> None:
        sink.append(
            CandidateRejection(
                unit_id=unit.unit_id, string_ids=unit.string_ids, code=code, detail=detail
            )
        )

    return reject


def _build_position(
    *,
    event: MusicalEvent,
    unit: PlayableUnit,
    profile: InstrumentProfile,
    fretted: bool,
    offset_from_nut: float,
    offset_from_open: float,
    is_open: bool,
) -> SpatialPosition:
    """Compose the three coordinate concepts for one surviving location.

    A fretless location carries ``fret_number = None`` and still carries a valid
    normalized position, and a physical distance whenever the profile knows its
    scale length. Absence of a fret never implies absence of a position.

    HYBRID profiles are treated as fretless here: MSME-001 accepts the mode but
    defines no fretted/fretless regions, so claiming a fret number would assert
    something the profile has not said.
    """
    scale = profile.scale_length_mm
    physical = PhysicalPosition(
        semitone_offset_from_nut=offset_from_nut,
        fret_number=int(round(offset_from_nut)) if fretted else None,
        normalized_position=normalized_position_for_semitones(offset_from_nut),
        distance_from_nut_mm=(
            distance_from_nut_mm(scale, offset_from_nut) if scale is not None else None
        ),
    )
    playing = PlayingPosition(
        semitone_offset_from_open=offset_from_open,
        fret_relative_to_capo=int(round(offset_from_open)) if fretted else None,
        is_open=is_open,
    )
    return SpatialPosition(
        string_id=unit.representative.string_id,
        course_id=unit.course_id,
        sounding=SoundingPitch(midi_note=event.midi_note, cents_offset=event.cents_offset),
        physical=physical,
        playing=playing,
    )
