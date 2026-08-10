"""Typed failures for the Musical Spatial Mapping Engine.

Dev Order: MSME-001

The engine fails closed: malformed input is rejected with an actionable, typed
error rather than silently corrected. Every error carries a human-readable message
and, where useful, a stable ``code`` for programmatic handling.
"""


class SpatialMappingError(Exception):
    """Base class for every error raised by the engine."""

    code: str = "spatial_mapping_error"


class ProfileValidationError(SpatialMappingError):
    """An instrument profile is structurally or semantically invalid."""

    code = "profile_invalid"


class EventValidationError(SpatialMappingError):
    """A musical event is malformed (bad MIDI note, duration, velocity, etc.)."""

    code = "event_invalid"


class MappingConstraintError(SpatialMappingError):
    """Mapping constraints are internally inconsistent or impossible."""

    code = "constraint_invalid"


class SelectionInputError(SpatialMappingError):
    """Selection was handed something that is not a scored candidate set.

    Added by MSME-002. This is a PIPELINE programming error, never a musical
    outcome. An empty candidate set means the caller skipped the check that
    produces ``SelectionStatus.UNPLAYABLE``, and a candidate arriving with
    ``score=None`` means scoring was skipped; in both cases the honest answer is
    to refuse rather than invent a selection. Selection never manufactures
    UNPLAYABLE — that belongs to orchestration, which branches on the generation
    outcome before selection is ever called.
    """

    code = "selection_input_invalid"


class UnsupportedPitchError(SpatialMappingError):
    """A pitch cannot be REPRESENTED at all — malformed or unsupported notation.

    Narrowed by MSME-002. The MSME-001 wording gave "microtones on a fixed
    fretted instrument, or a note below every open string" as examples, which was
    a contract defect: those are ordinary instrument unplayability, not a
    representation failure. A valid event on a valid profile with nowhere to be
    played is a domain OUTCOME and returns
    ``MappingResult(status=SelectionStatus.UNPLAYABLE)`` carrying the reasons.

    Raising there would have forced every caller mapping a melody into exception
    control flow over ordinary notes, and would have left UNPLAYABLE unreachable.
    """

    code = "unsupported_pitch"
