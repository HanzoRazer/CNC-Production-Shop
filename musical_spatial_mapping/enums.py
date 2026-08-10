"""Controlled vocabularies for the Musical Spatial Mapping Engine.

Dev Order: MSME-001

Every serialized string value lives here so the subsystem never scatters string
literals. Tests assert these serialized values, because they are a public contract.
"""

from enum import Enum


class FingerboardMode(str, Enum):
    """How positions resolve along a string."""

    FRETTED = "fretted"
    FRETLESS = "fretless"
    # HYBRID is reserved for profiles with both fretted and fretless regions.
    # The model accepts it; full hybrid-region mapping is NOT required in MSME-001.
    HYBRID = "hybrid"


class PositionUnit(str, Enum):
    """Units a spatial position may be expressed in."""

    SEMITONE = "semitone"
    MILLIMETER = "millimeter"
    NORMALIZED = "normalized"


class OpenStringPolicy(str, Enum):
    """How open strings are treated during candidate generation and scoring."""

    ALLOW = "allow"
    PREFER = "prefer"
    AVOID = "avoid"
    EXCLUDE = "exclude"


class SelectionStatus(str, Enum):
    """Outcome of selecting among scored candidates."""

    SELECTED = "selected"
    AMBIGUOUS = "ambiguous"
    UNPLAYABLE = "unplayable"


class RejectionCode(str, Enum):
    """Why a hard-constraint candidate was rejected.

    A preferred-region mismatch is a scoring PENALTY, not a rejection; these codes
    exist for hard-range and identity constraints only.

    INSTRUMENT FEASIBILITY AND CALLER CONSTRAINTS DO NOT SHARE CODES, even though
    both eliminate a candidate. UNPLAYABLE has to be able to say whether the
    instrument could not play the note or the caller's own limits excluded every
    location that could, and one code covering both destroys that answer::

        instrument feasibility   BELOW_OPEN_PITCH, ABOVE_POSITION_RANGE,
                                 PITCH_NOT_REALIZABLE, PROFILE_INVALID
        caller constraints       POSITION_CONSTRAINT, OPEN_STRING_EXCLUDED,
                                 CAPO_CONFLICT, STRING_EXCLUDED
    """

    # Instrument feasibility: the pitch is below the string's open reference, or
    # beyond the neck the profile actually declares.
    BELOW_OPEN_PITCH = "below_open_pitch"
    ABOVE_POSITION_RANGE = "above_position_range"
    STRING_EXCLUDED = "string_excluded"
    OPEN_STRING_EXCLUDED = "open_string_excluded"
    OUTSIDE_PREFERRED_REGION = "outside_preferred_region"
    CAPO_CONFLICT = "capo_conflict"
    PROFILE_INVALID = "profile_invalid"
    # Added by MSME-002: a fixed-fret instrument asked for a pitch that falls
    # between its frets. No existing code covered it -- the location is not out
    # of range, not excluded, and the profile is not invalid; the pitch sits
    # inside the conceptual range and the discrete geometry cannot represent it
    # exactly. Per MSME-002 this is an ordinary unplayable outcome, never an
    # UnsupportedPitchError.
    PITCH_NOT_REALIZABLE = "pitch_not_realizable"
    # Added by MSME-002: the location was physically possible and the CALLER's
    # own position window excluded it. Covers both MappingConstraints bounds --
    # minimum_position and maximum_position -- because the rejection's detail
    # names which bound and by how much, so one code hides nothing. Previously
    # the low bound borrowed BELOW_OPEN_PITCH and the high bound borrowed
    # ABOVE_POSITION_RANGE, which made a caller's own limit indistinguishable
    # from the instrument running out of neck.
    POSITION_CONSTRAINT = "position_constraint"
