"""Stable, JSON-compatible (de)serialization for instrument profiles.

Dev Order: MSME-001

Instrument profiles round-trip (MSME-001) and mapping results round-trip
(MSME-002 Phase G, which is where MSME-001 deliberately deferred them).

Determinism: keys are emitted in a fixed order and enums by value, so golden
comparisons are byte-stable.
"""

import json
from collections.abc import Mapping
from typing import Any

from .enums import FingerboardMode, SelectionStatus
from .errors import ProfileValidationError
from .models import (
    CandidateScore,
    InstrumentProfile,
    MappingAnnotation,
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


# --------------------------------------------------------------------------- #
# MappingResult (MSME-002 Phase G)
#
# MSME-001 deferred this deliberately; it lands here now that there are results
# to serialize. Same rules as the profile serializer above: fixed key order,
# enums by value, no derived or environment-dependent fields, so a golden file
# is byte-stable across machines and Python versions.
#
# The three coordinate concepts are emitted as three nested objects and are
# never flattened into one number. A serializer that collapsed them would undo
# the distinction the whole model exists to preserve, and the capo case would
# stop being visible in the artifact that outlives the process.
# --------------------------------------------------------------------------- #


def _event_to_dict(event: MusicalEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "midi_note": event.midi_note,
        "start_tick": event.start_tick,
        "duration_ticks": event.duration_ticks,
        "velocity": event.velocity,
        "cents_offset": event.cents_offset,
        "voice_id": event.voice_id,
    }


def _position_to_dict(position: SpatialPosition) -> dict[str, Any]:
    return {
        "string_id": position.string_id,
        "course_id": position.course_id,
        "sounding": {
            "midi_note": position.sounding.midi_note,
            "cents_offset": position.sounding.cents_offset,
        },
        "physical": {
            "semitone_offset_from_nut": position.physical.semitone_offset_from_nut,
            "fret_number": position.physical.fret_number,
            "normalized_position": position.physical.normalized_position,
            "distance_from_nut_mm": position.physical.distance_from_nut_mm,
        },
        "playing": {
            "semitone_offset_from_open": position.playing.semitone_offset_from_open,
            "fret_relative_to_capo": position.playing.fret_relative_to_capo,
            "is_open": position.playing.is_open,
        },
    }


def _score_to_dict(score: CandidateScore | None) -> dict[str, Any] | None:
    if score is None:
        return None
    return {
        "total": score.total,
        "components": dict(score.components),
        "explanation": list(score.explanation),
    }


def _candidate_to_dict(candidate: PositionCandidate) -> dict[str, Any]:
    return {
        "position": _position_to_dict(candidate.position),
        "score": _score_to_dict(candidate.score),
    }


def _annotation_to_dict(annotation: MappingAnnotation | None) -> dict[str, Any] | None:
    if annotation is None:
        return None
    return {
        "primary_label": annotation.primary_label,
        "secondary_label": annotation.secondary_label,
        "pitch_label": annotation.pitch_label,
        "string_label": annotation.string_label,
        "position_label": annotation.position_label,
        "reference_marker_label": annotation.reference_marker_label,
        "accessibility_text": annotation.accessibility_text,
    }


def mapping_result_to_dict(result: MappingResult) -> dict[str, Any]:
    """Serialize a mapping result to an ordered, JSON-compatible dict.

    No ``equal_best`` field is stored. Every candidate carries its score, so the
    tied set is exactly those matching the selected candidate's total — storing
    it as well would create a second copy of a derived fact that could drift out
    of step with the scores it summarises. ``equal_best_of()`` reads it back.
    """
    return {
        "event": _event_to_dict(result.event),
        "instrument_id": result.instrument_id,
        "status": result.status.value,
        "selected": None if result.selected is None else _candidate_to_dict(result.selected),
        "candidates": [_candidate_to_dict(c) for c in result.candidates],
        "annotation": _annotation_to_dict(result.annotation),
        "diagnostics": list(result.diagnostics),
    }


def mapping_result_to_json(result: MappingResult, *, indent: int | None = 2) -> str:
    """Deterministic JSON for a mapping result."""
    return json.dumps(mapping_result_to_dict(result), indent=indent, ensure_ascii=False)


def _position_from_dict(data: Mapping[str, Any]) -> SpatialPosition:
    sounding = _require(data, "sounding")
    physical = _require(data, "physical")
    playing = _require(data, "playing")
    return SpatialPosition(
        string_id=_require(data, "string_id"),
        course_id=data.get("course_id"),
        sounding=SoundingPitch(
            midi_note=_require(sounding, "midi_note"),
            cents_offset=sounding.get("cents_offset", 0.0),
        ),
        physical=PhysicalPosition(
            semitone_offset_from_nut=_require(physical, "semitone_offset_from_nut"),
            fret_number=physical.get("fret_number"),
            normalized_position=_require(physical, "normalized_position"),
            distance_from_nut_mm=physical.get("distance_from_nut_mm"),
        ),
        playing=PlayingPosition(
            semitone_offset_from_open=_require(playing, "semitone_offset_from_open"),
            fret_relative_to_capo=playing.get("fret_relative_to_capo"),
            is_open=_require(playing, "is_open"),
        ),
    )


def _candidate_from_dict(data: Mapping[str, Any]) -> PositionCandidate:
    score = data.get("score")
    return PositionCandidate(
        position=_position_from_dict(_require(data, "position")),
        score=None
        if score is None
        else CandidateScore(
            total=_require(score, "total"),
            components=dict(_require(score, "components")),
            explanation=tuple(score.get("explanation", ())),
        ),
    )


def mapping_result_from_dict(data: Mapping[str, Any]) -> MappingResult:
    """Rebuild a mapping result from its serialized form.

    Added because the model is plain data and the round trip is exact, which
    makes the golden vectors a real contract rather than a rendering: a stored
    result can be read back and compared to a freshly computed one as objects.
    """
    event = _require(data, "event")
    annotation = data.get("annotation")
    selected = data.get("selected")
    return MappingResult(
        event=MusicalEvent(
            event_id=_require(event, "event_id"),
            midi_note=_require(event, "midi_note"),
            start_tick=_require(event, "start_tick"),
            duration_ticks=_require(event, "duration_ticks"),
            velocity=event.get("velocity", 64),
            cents_offset=event.get("cents_offset", 0.0),
            voice_id=event.get("voice_id"),
        ),
        instrument_id=_require(data, "instrument_id"),
        status=SelectionStatus(_require(data, "status")),
        candidates=tuple(_candidate_from_dict(c) for c in data.get("candidates", ())),
        selected=None if selected is None else _candidate_from_dict(selected),
        annotation=None
        if annotation is None
        else MappingAnnotation(
            primary_label=_require(annotation, "primary_label"),
            secondary_label=annotation.get("secondary_label"),
            pitch_label=_require(annotation, "pitch_label"),
            string_label=_require(annotation, "string_label"),
            position_label=_require(annotation, "position_label"),
            reference_marker_label=annotation.get("reference_marker_label"),
            accessibility_text=_require(annotation, "accessibility_text"),
        ),
        diagnostics=tuple(data.get("diagnostics", ())),
    )


def mapping_result_from_json(text: str) -> MappingResult:
    """Rebuild a mapping result from deterministic JSON."""
    return mapping_result_from_dict(json.loads(text))
