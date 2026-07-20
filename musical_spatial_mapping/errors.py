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


class UnsupportedPitchError(SpatialMappingError):
    """A pitch cannot be represented on this profile (e.g. microtones on a fixed
    fretted instrument, or a note below every open string)."""

    code = "unsupported_pitch"
