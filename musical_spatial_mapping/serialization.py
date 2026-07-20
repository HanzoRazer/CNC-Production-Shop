"""Stable, JSON-compatible (de)serialization for instrument profiles.

Dev Order: MSME-001

Phase 1 scope: instrument-profile round-tripping only (needed so external profile
files can be loaded and validated). ``MappingResult`` serialization is Phase 6 and
is intentionally absent here.

Determinism: keys are emitted in a fixed order and enums by value, so golden
comparisons are byte-stable.
"""

import json
from collections.abc import Mapping
from typing import Any

from .enums import FingerboardMode
from .errors import ProfileValidationError
from .models import InstrumentProfile, ReferenceMarker, StringProfile
from .validation import validate_instrument_profile


def _string_to_dict(string: StringProfile) -> dict[str, Any]:
    return {
        "string_id": string.string_id,
        "display_label": string.display_label,
        "display_order": string.display_order,
        "open_midi_note": string.open_midi_note,
        "course_id": string.course_id,
        "enabled": string.enabled,
        "max_position": string.max_position,
    }


def _marker_to_dict(marker: ReferenceMarker) -> dict[str, Any]:
    return {
        "marker_id": marker.marker_id,
        "semitone_offset": marker.semitone_offset,
        "label": marker.label,
    }


def instrument_profile_to_dict(profile: InstrumentProfile) -> dict[str, Any]:
    """Serialize a profile to an ordered, JSON-compatible dict."""
    return {
        "schema_version": profile.schema_version,
        "instrument_id": profile.instrument_id,
        "display_name": profile.display_name,
        "family": profile.family,
        "fingerboard_mode": profile.fingerboard_mode.value,
        "strings": [_string_to_dict(s) for s in profile.strings],
        "scale_length_mm": profile.scale_length_mm,
        "fret_count": profile.fret_count,
        "reference_markers": [_marker_to_dict(m) for m in profile.reference_markers],
        "metadata": dict(profile.metadata),
    }


def _require(data: Mapping[str, Any], key: str) -> Any:
    if key not in data:
        raise ProfileValidationError(f"instrument profile missing required key: {key}")
    return data[key]


def instrument_profile_from_dict(data: Mapping[str, Any]) -> InstrumentProfile:
    """Build and validate a profile from a JSON-compatible dict.

    Missing required keys raise ``ProfileValidationError``; unknown extra keys are
    ignored (forward-compatible). Semantic validation always runs before return.
    """
    if not isinstance(data, Mapping):
        raise ProfileValidationError("instrument profile must be a mapping")

    try:
        mode = FingerboardMode(_require(data, "fingerboard_mode"))
    except ValueError as exc:
        raise ProfileValidationError(str(exc)) from exc

    strings = tuple(
        StringProfile(
            string_id=_require(s, "string_id"),
            display_label=_require(s, "display_label"),
            display_order=_require(s, "display_order"),
            open_midi_note=_require(s, "open_midi_note"),
            course_id=s.get("course_id"),
            enabled=s.get("enabled", True),
            max_position=s.get("max_position"),
        )
        for s in _require(data, "strings")
    )

    markers = tuple(
        ReferenceMarker(
            marker_id=_require(m, "marker_id"),
            semitone_offset=_require(m, "semitone_offset"),
            label=_require(m, "label"),
        )
        for m in data.get("reference_markers", ())
    )

    profile = InstrumentProfile(
        schema_version=_require(data, "schema_version"),
        instrument_id=_require(data, "instrument_id"),
        display_name=_require(data, "display_name"),
        family=_require(data, "family"),
        fingerboard_mode=mode,
        strings=strings,
        scale_length_mm=data.get("scale_length_mm"),
        fret_count=data.get("fret_count"),
        reference_markers=markers,
        metadata=dict(data.get("metadata", {})),
    )
    return validate_instrument_profile(profile)


def instrument_profile_from_json(text: str) -> InstrumentProfile:
    """Parse and validate a profile from a JSON string."""
    return instrument_profile_from_dict(json.loads(text))
