"""Immutable domain contracts for the Musical Spatial Mapping Engine.

Dev Order: MSME-001

Every model is a frozen dataclass. Models carry data only -- no mapping
mathematics runs in a constructor. The engine is deliberately dependency-free
(no pydantic, no transport frameworks): it is executable mathematics meant to be
embeddable in firmware, a desktop sequencer, a CLI, or a cloud service without
dragging a web stack along. Validation lives in ``validation.py``; boundary
frameworks (pydantic/FastAPI) belong to the applications that consume the engine,
never to the engine itself.

Coordinate vocabulary (MSME-001 amendment -- never overload one integer):
    SoundingPitch     the note that sounds.
    PhysicalPosition  where the finger sits on the neck, measured FROM THE NUT.
    PlayingPosition   what the performer does, measured FROM THE EFFECTIVE OPEN
                      string (i.e. relative to a capo).

With no capo, PhysicalPosition and PlayingPosition coincide; with a capo they
differ, and the two must never be collapsed into a single number. See the package
README ("Coordinate model").
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from .enums import (
    FingerboardMode,
    OpenStringPolicy,
    SelectionStatus,
)

JSONScalar = str | int | float | bool | None


# --------------------------------------------------------------------------- input


@dataclass(frozen=True)
class MusicalEvent:
    """A canonical musical event. The engine's input is musical, never graphical.

    ``midi_note`` is the first canonical pitch key (0-127). ``cents_offset`` allows
    a later microtonal extension; it defaults to 0.0 (12-TET).
    """

    event_id: str
    midi_note: int
    start_tick: int
    duration_ticks: int
    velocity: int = 64
    cents_offset: float = 0.0
    voice_id: str | None = None


# ------------------------------------------------------------------ instrument model


@dataclass(frozen=True)
class StringProfile:
    """One physical string. Identity is a stable ``string_id`` independent of any
    display label such as "high E" and independent of display order."""

    string_id: str
    display_label: str
    display_order: int
    open_midi_note: int
    course_id: str | None = None
    enabled: bool = True
    # Maximum playable position as a semitone offset from the open string.
    max_position: float | None = None


@dataclass(frozen=True)
class ReferenceMarker:
    """A landmark for annotation (fretless position dots, fretted inlays)."""

    marker_id: str
    semitone_offset: float
    label: str


@dataclass(frozen=True)
class InstrumentProfile:
    """A stringed instrument described entirely by data -- never by name branches.

    For a FRETTED instrument ``fret_count`` is required. For a FRETLESS instrument
    ``fret_count`` is None; visual divisions belong in ``reference_markers``.
    ``scale_length_mm`` may be None, in which case semitone and normalized positions
    remain calculable but millimetre distances are None.
    """

    schema_version: str
    instrument_id: str
    display_name: str
    family: str
    fingerboard_mode: FingerboardMode
    strings: tuple[StringProfile, ...]
    scale_length_mm: float | None
    fret_count: int | None
    reference_markers: tuple[ReferenceMarker, ...] = ()
    metadata: Mapping[str, JSONScalar] = field(default_factory=dict)


# ------------------------------------------------------------- request configuration


@dataclass(frozen=True)
class MappingConstraints:
    """Hard limits and identity filters. Positions are semitone offsets from the
    effective (post-capo) open string."""

    allowed_string_ids: frozenset[str] | None = None
    excluded_string_ids: frozenset[str] = frozenset()
    minimum_position: float | None = None
    maximum_position: float | None = None
    preferred_minimum_position: float | None = None
    preferred_maximum_position: float | None = None
    open_string_policy: OpenStringPolicy = OpenStringPolicy.ALLOW
    maximum_string_jump: int | None = None
    capo_fret: int = 0


@dataclass(frozen=True)
class MappingPreferences:
    """Soft weights driving deterministic scoring. Every weight must be finite and
    nonnegative; ``lower_position_bias`` is an intentionally signed bias."""

    movement_weight: float = 1.0
    string_change_weight: float = 1.0
    position_weight: float = 1.0
    preferred_region_weight: float = 1.0
    open_string_weight: float = 1.0
    lower_position_bias: float = 0.0


# ---------------------------------------------------------- coordinate value objects

# Three distinct concepts, per the MSME-001 amendment. Kept as separate frozen
# value objects so no single integer is ever asked to mean physical fret, playing
# position, and sounding pitch at once.


@dataclass(frozen=True)
class SoundingPitch:
    """The note that actually sounds."""

    midi_note: int
    cents_offset: float = 0.0


@dataclass(frozen=True)
class PhysicalPosition:
    """Where the finger sits on the neck, measured FROM THE NUT.

    ``fret_number`` is the physical fret counted from the nut (None on a fretless
    instrument or between frets). ``normalized_position`` is distance/scale_length
    so a renderer needs no physical scale length; ``distance_from_nut_mm`` is None
    when the profile declares no scale length.
    """

    semitone_offset_from_nut: float
    fret_number: int | None
    normalized_position: float
    distance_from_nut_mm: float | None


@dataclass(frozen=True)
class PlayingPosition:
    """What the performer does, measured FROM THE EFFECTIVE OPEN string (relative
    to a capo). ``is_open`` means the finger is not fretting relative to the capo."""

    semitone_offset_from_open: float
    fret_relative_to_capo: int | None
    is_open: bool


@dataclass(frozen=True)
class SpatialPosition:
    """A fully described playable location on one string.

    Composes the three coordinate concepts. Fretted and fretless positions share
    this one contract: a fretless position simply carries ``fret_number = None``
    while still carrying valid normalized and (when scale length is known) physical
    positions. The absence of a fret must never imply the absence of a position.
    """

    string_id: str
    course_id: str | None
    sounding: SoundingPitch
    physical: PhysicalPosition
    playing: PlayingPosition


# --------------------------------------------------------------- scoring & candidates


@dataclass(frozen=True)
class CandidateScore:
    """A structured score. The engine never reports an opaque single number: every
    component is named and an ordered human explanation is retained."""

    total: float
    components: Mapping[str, float]
    explanation: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionCandidate:
    """A playable location, optionally scored."""

    position: SpatialPosition
    score: CandidateScore | None = None


# ------------------------------------------------------------------------ annotation


@dataclass(frozen=True)
class MappingAnnotation:
    """Instrument-aware, presentation-neutral labels for a selected position.

    This is semantic annotation, not graphics: no colours, pixels, or coordinates.
    ``accessibility_text`` is mandatory. Fretless annotations must use position
    language and must not claim a physical fret exists.
    """

    primary_label: str
    secondary_label: str | None
    pitch_label: str
    string_label: str
    position_label: str
    reference_marker_label: str | None
    accessibility_text: str


# ---------------------------------------------------------------------------- result


@dataclass(frozen=True)
class MappingResult:
    """The engine's output for one event.

    ``candidates`` preserves ambiguity (all accepted locations). ``selected`` is a
    deterministic choice that may be present even when ``status`` is AMBIGUOUS, so a
    caller can render immediately without erasing the alternatives.
    """

    event: MusicalEvent
    instrument_id: str
    status: SelectionStatus
    candidates: tuple[PositionCandidate, ...]
    selected: PositionCandidate | None
    annotation: MappingAnnotation | None
    diagnostics: tuple[str, ...] = ()
