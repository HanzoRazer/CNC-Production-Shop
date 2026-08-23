"""Musical Spatial Mapping Engine (MSME).

Dev Order: MSME-001

A reusable, application-agnostic Core Engine that converts canonical musical pitch
events into playable spatial locations on a configured stringed instrument --
fretted or fretless. It is executable mathematics: dependency-free, deterministic,
and embeddable. Applications consume it; applications do not define it. See the
package README ("Architectural Position").

The public entry point is :class:`MusicalSpatialMapper`, which runs
``validate -> generate -> score -> select -> annotate`` and returns a
``MappingResult``. The individual stages live in ``candidates``, ``scoring``,
``selection`` and ``annotation`` and are deliberately NOT re-exported here: they
are how the engine works rather than what it promises, and a caller reaching past
the facade should have to say so by importing the module.

What IS exported alongside the facade is everything needed to use it across a
process boundary: the domain models and enums, the fail-closed validators, and
the (de)serializers for profiles, results and spatial positions. The position
pair is public because a caller resuming from stored state needs it to rebuild a
``previous_position`` for the next call, and that is the ordinary workflow rather
than an internal detail.

Example profiles live in ``musical_spatial_mapping.fixtures`` and are importable,
but are deliberately not part of this root contract: they are sample data, not a
durable API.

``musical_spatial_mapping.cli`` is a diagnostic consumer of the engine and is
likewise not exported; it has no semantics of its own.
"""

from ._distribution_version import distribution_version as _distribution_version
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
    SelectionInputError,
    SpatialMappingError,
    UnsupportedPitchError,
)
from .mapper import MusicalSpatialMapper, equal_best_of
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
    mapping_result_from_dict,
    mapping_result_from_json,
    mapping_result_to_dict,
    mapping_result_to_json,
    spatial_position_from_dict,
    spatial_position_to_dict,
)
from .validation import (
    validate_instrument_profile,
    validate_mapping_constraints,
    validate_mapping_preferences,
    validate_musical_event,
    validate_string_profile,
)

# Version of the installed cnc-production-shop distribution.
# This is not MSME API maturity; see MSME_API_VERSION.
__version__ = _distribution_version()

# Version of the public MSME API/behavioral contract.
# Not a separately installable distribution version.
MSME_API_VERSION = "0.2.0"

__all__ = [
    "MSME_API_VERSION",
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
    "SelectionInputError",
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
    "mapping_result_to_dict",
    "mapping_result_to_json",
    "mapping_result_from_dict",
    "mapping_result_from_json",
    "spatial_position_to_dict",
    "spatial_position_from_dict",
    # mapping facade
    "MusicalSpatialMapper",
    "equal_best_of",
]
