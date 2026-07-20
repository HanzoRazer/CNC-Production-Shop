"""Musical Spatial Mapping Engine (MSME).

Dev Order: MSME-001

A reusable, application-agnostic Core Engine that converts canonical musical pitch
events into playable spatial locations on a configured stringed instrument --
fretted or fretless. It is executable mathematics: dependency-free, deterministic,
and embeddable. Applications consume it; applications do not define it. See the
package README ("Architectural Position").

Public surface as of MSME-001 Phase 1-2 (contracts + geometry primitives). Mapping
behaviour -- candidate generation, scoring, selection, annotation, and the
``MusicalSpatialMapper`` facade -- lands in later phases and is intentionally not
exported yet.
"""

__version__ = "0.1.0"

from .enums import (
    FingerboardMode,
    OpenStringPolicy,
    PositionUnit,
    RejectionCode,
    SelectionStatus,
)
from .errors import (
    EventValidationError,
    MappingConstraintError,
    ProfileValidationError,
    SpatialMappingError,
    UnsupportedPitchError,
)
from .models import (
    CandidateScore,
    InstrumentProfile,
    MappingAnnotation,
    MappingConstraints,
    MappingPreferences,
    MappingResult,
    MusicalEvent,
    PhysicalPosition,
    PlayingPosition,
    PositionCandidate,
    ReferenceMarker,
    SoundingPitch,
    SpatialPosition,
    StringProfile,
)
from .serialization import (
    instrument_profile_from_dict,
    instrument_profile_from_json,
    instrument_profile_to_dict,
)
from .validation import (
    validate_instrument_profile,
    validate_mapping_constraints,
    validate_mapping_preferences,
    validate_musical_event,
    validate_string_profile,
)

__all__ = [
    # enums
    "FingerboardMode",
    "OpenStringPolicy",
    "PositionUnit",
    "RejectionCode",
    "SelectionStatus",
    # errors
    "SpatialMappingError",
    "ProfileValidationError",
    "EventValidationError",
    "MappingConstraintError",
    "UnsupportedPitchError",
    # models
    "MusicalEvent",
    "StringProfile",
    "ReferenceMarker",
    "InstrumentProfile",
    "MappingConstraints",
    "MappingPreferences",
    "SoundingPitch",
    "PhysicalPosition",
    "PlayingPosition",
    "SpatialPosition",
    "CandidateScore",
    "PositionCandidate",
    "MappingAnnotation",
    "MappingResult",
    # validation
    "validate_musical_event",
    "validate_string_profile",
    "validate_instrument_profile",
    "validate_mapping_constraints",
    "validate_mapping_preferences",
    # serialization
    "instrument_profile_to_dict",
    "instrument_profile_from_dict",
    "instrument_profile_from_json",
]
