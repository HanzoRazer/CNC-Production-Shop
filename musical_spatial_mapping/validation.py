"""Fail-closed validation for the Musical Spatial Mapping Engine.

Dev Order: MSME-001

Invalid input is rejected before any mapping runs. Nothing here silently mutates
or "repairs" input. Each function returns the validated object unchanged or raises
a typed error from ``errors.py``.
"""

import math

from .enums import FingerboardMode
from .errors import (
    EventValidationError,
    MappingConstraintError,
    ProfileValidationError,
)
from .models import (
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    MusicalEvent,
    StringProfile,
)
from .pitch import MIDI_MAX, MIDI_MIN


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


# ------------------------------------------------------------------------- events


def validate_musical_event(event: MusicalEvent) -> MusicalEvent:
    if not event.event_id:
        raise EventValidationError("event_id must be non-empty")
    if not (MIDI_MIN <= event.midi_note <= MIDI_MAX):
        raise EventValidationError(
            f"midi_note {event.midi_note} out of range {MIDI_MIN}-{MIDI_MAX}"
        )
    if event.start_tick < 0:
        raise EventValidationError(f"start_tick must be >= 0, got {event.start_tick}")
    if event.duration_ticks <= 0:
        raise EventValidationError(
            f"duration_ticks must be > 0, got {event.duration_ticks}"
        )
    if not (0 <= event.velocity <= 127):
        raise EventValidationError(f"velocity {event.velocity} out of range 0-127")
    if not _finite(event.cents_offset):
        raise EventValidationError("cents_offset must be finite")
    return event


# ------------------------------------------------------------------------ strings


def validate_string_profile(string: StringProfile) -> StringProfile:
    if not string.string_id:
        raise ProfileValidationError("string_id must be non-empty")
    if not (MIDI_MIN <= string.open_midi_note <= MIDI_MAX):
        raise ProfileValidationError(
            f"string {string.string_id}: open_midi_note {string.open_midi_note} "
            f"out of range {MIDI_MIN}-{MIDI_MAX}"
        )
    if string.max_position is not None:
        if not _finite(string.max_position) or string.max_position < 0:
            raise ProfileValidationError(
                f"string {string.string_id}: max_position must be finite and >= 0"
            )
    return string


# ------------------------------------------------------------------ instrument


def validate_instrument_profile(profile: InstrumentProfile) -> InstrumentProfile:
    if not profile.schema_version:
        raise ProfileValidationError("schema_version must be non-empty")
    if not profile.instrument_id:
        raise ProfileValidationError("instrument_id must be non-empty")
    if not profile.strings:
        raise ProfileValidationError("profile must declare at least one string")

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for string in profile.strings:
        validate_string_profile(string)
        if string.string_id in seen_ids:
            raise ProfileValidationError(f"duplicate string_id: {string.string_id}")
        seen_ids.add(string.string_id)
        if string.display_order in seen_orders:
            raise ProfileValidationError(
                f"duplicate display_order: {string.display_order}"
            )
        seen_orders.add(string.display_order)

    if profile.scale_length_mm is not None:
        if not _finite(profile.scale_length_mm) or profile.scale_length_mm <= 0:
            raise ProfileValidationError("scale_length_mm must be finite and > 0")

    mode = profile.fingerboard_mode
    if mode == FingerboardMode.FRETTED:
        if profile.fret_count is None or profile.fret_count < 1:
            raise ProfileValidationError(
                "a fretted profile requires fret_count >= 1"
            )
    elif mode == FingerboardMode.FRETLESS:
        if profile.fret_count is not None:
            raise ProfileValidationError(
                "a fretless profile must not declare fret_count; use "
                "reference_markers for visual divisions"
            )
    # HYBRID: fret_count optional, accepted as-is in MSME-001.
    if profile.fret_count is not None and profile.fret_count < 0:
        raise ProfileValidationError("fret_count must be >= 0")

    seen_markers: set[str] = set()
    for marker in profile.reference_markers:
        if not marker.marker_id:
            raise ProfileValidationError("reference marker marker_id must be non-empty")
        if marker.marker_id in seen_markers:
            raise ProfileValidationError(f"duplicate marker_id: {marker.marker_id}")
        seen_markers.add(marker.marker_id)
        if not _finite(marker.semitone_offset) or marker.semitone_offset < 0:
            raise ProfileValidationError(
                f"marker {marker.marker_id}: semitone_offset must be finite and >= 0"
            )
    return profile


# ---------------------------------------------------------------------- constraints


def validate_mapping_constraints(
    profile: InstrumentProfile,
    constraints: MappingConstraints,
) -> MappingConstraints:
    if constraints.capo_fret < 0:
        raise MappingConstraintError("capo_fret must be >= 0")
    if profile.fret_count is not None and constraints.capo_fret > profile.fret_count:
        raise MappingConstraintError(
            f"capo_fret {constraints.capo_fret} exceeds fret_count "
            f"{profile.fret_count}"
        )

    for label, lo, hi in (
        ("position", constraints.minimum_position, constraints.maximum_position),
        (
            "preferred position",
            constraints.preferred_minimum_position,
            constraints.preferred_maximum_position,
        ),
    ):
        if lo is not None and not _finite(lo):
            raise MappingConstraintError(f"{label} minimum must be finite")
        if hi is not None and not _finite(hi):
            raise MappingConstraintError(f"{label} maximum must be finite")
        if lo is not None and hi is not None and lo > hi:
            raise MappingConstraintError(
                f"{label} minimum {lo} exceeds maximum {hi}"
            )

    if (
        constraints.maximum_string_jump is not None
        and constraints.maximum_string_jump < 0
    ):
        raise MappingConstraintError("maximum_string_jump must be >= 0")

    known = {s.string_id for s in profile.strings}
    for sid in constraints.excluded_string_ids:
        if sid not in known:
            raise MappingConstraintError(f"excluded_string_ids: unknown string {sid}")
    if constraints.allowed_string_ids is not None:
        for sid in constraints.allowed_string_ids:
            if sid not in known:
                raise MappingConstraintError(
                    f"allowed_string_ids: unknown string {sid}"
                )
        overlap = constraints.allowed_string_ids & constraints.excluded_string_ids
        if overlap:
            raise MappingConstraintError(
                f"strings both allowed and excluded: {sorted(overlap)}"
            )
        if not (constraints.allowed_string_ids - constraints.excluded_string_ids):
            raise MappingConstraintError(
                "allowed_string_ids minus excluded_string_ids is empty"
            )
    return constraints


# ---------------------------------------------------------------------- preferences


def validate_mapping_preferences(preferences: MappingPreferences) -> MappingPreferences:
    nonnegative = {
        "movement_weight": preferences.movement_weight,
        "string_change_weight": preferences.string_change_weight,
        "position_weight": preferences.position_weight,
        "preferred_region_weight": preferences.preferred_region_weight,
        "open_string_weight": preferences.open_string_weight,
    }
    for name, value in nonnegative.items():
        if not _finite(value):
            raise MappingConstraintError(f"{name} must be finite")
        if value < 0:
            raise MappingConstraintError(f"{name} must be >= 0")
    if not _finite(preferences.lower_position_bias):
        raise MappingConstraintError("lower_position_bias must be finite")
    return preferences
