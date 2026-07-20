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
    """

    BELOW_OPEN_PITCH = "below_open_pitch"
    ABOVE_POSITION_RANGE = "above_position_range"
    STRING_EXCLUDED = "string_excluded"
    OPEN_STRING_EXCLUDED = "open_string_excluded"
    OUTSIDE_PREFERRED_REGION = "outside_preferred_region"
    CAPO_CONFLICT = "capo_conflict"
    PROFILE_INVALID = "profile_invalid"
