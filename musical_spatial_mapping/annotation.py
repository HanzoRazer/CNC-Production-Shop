"""Instrument-aware annotation of a selected position.

Dev Order: MSME-002 Phase E

Annotation describes a location that has already been chosen. It never re-scores,
never re-selects, and never touches the position it is describing — every model
here is frozen and this module only reads.

It is SEMANTIC, not graphical: labels a renderer or a screen reader can use, with
no colours, pixels, or coordinates. What terminology to use comes from profile
data — ``fingerboard_mode``, ``display_label``, ``course_id``, ``reference_markers``
— never from branching on an instrument's name, and never from any consuming
application's vocabulary.

Two rules do real work here.

**A fretless instrument is never described with fret language.** Not in the
primary label, not in the position label, not in the accessibility text. A
fretless location has a position, and saying "fret" would assert a landmark the
instrument does not have. ``fret_number`` stays None and the prose agrees with it.

**A course is one playable unit, not two wires.** When the profile declares a
``course_id`` the annotation names the course, and the individual strings appear
only as supporting membership. Exposing a paired wire as though it were the
choice would contradict what generation already decided.
"""

from __future__ import annotations

from dataclasses import dataclass

from .candidates import playable_units, unit_index_of
from .geometry import POSITION_EPSILON
from .models import (
    InstrumentProfile,
    MappingAnnotation,
    ReferenceMarker,
    SpatialPosition,
)
from .pitch import format_pitch_name


@dataclass(frozen=True)
class PlayableUnitLabel:
    """What to call one playable unit, plus the wires it covers.

    Local to annotation on purpose. ``MappingAnnotation`` is the domain contract
    and this is scratch work on the way to filling it in; promoting it to
    ``models`` would create a second annotation type to keep in step.
    """

    label: str
    string_ids: tuple[str, ...]


def _unit_label(profile: InstrumentProfile, position: SpatialPosition) -> PlayableUnitLabel:
    """What to call the thing the player fingers, and which wires it covers."""
    units = playable_units(profile)
    index = unit_index_of(units, position)
    if index is None:
        noun = "Course" if position.course_id is not None else "String"
        return PlayableUnitLabel(f"{noun} {position.string_id}", ())
    unit = units[index]
    label = unit.representative.display_label
    noun = "Course" if unit.course_id is not None else "String"
    return PlayableUnitLabel(f"{noun} {label}", unit.string_ids)


def _pitch_label(position: SpatialPosition) -> str:
    """Spelled pitch, with a cents deviation only when there is one."""
    name = format_pitch_name(position.sounding.midi_note)
    cents = position.sounding.cents_offset
    if cents == 0.0:
        return name
    return f"{name}{cents:+.0f}c"


def _position_label(profile: InstrumentProfile, position: SpatialPosition) -> str:
    """Where on the neck, in the instrument's own terms.

    A fretted instrument has frets and may say so. A fretless one has a position,
    described in semitones from the nut and in millimetres when the profile knows
    its scale length — never as a fret, which it does not have.
    """
    physical = position.physical
    if physical.fret_number is not None:
        return f"fret {physical.fret_number}"
    offset = f"{physical.semitone_offset_from_nut:.2f} semitones from the nut"
    if physical.distance_from_nut_mm is None:
        return offset
    return f"{offset} ({physical.distance_from_nut_mm:.1f} mm)"


def _marker_for(profile: InstrumentProfile, position: SpatialPosition) -> ReferenceMarker | None:
    """The landmark at this exact position, if the profile declares one.

    Markers enrich the description and never move the position: this only reads
    ``reference_markers`` and matches on the physical offset already computed.
    """
    for marker in profile.reference_markers:
        if abs(marker.semitone_offset - position.physical.semitone_offset_from_nut) <= (
            POSITION_EPSILON
        ):
            return marker
    return None


def _capo_semitones(position: SpatialPosition) -> float:
    """How far the effective open sits above the nut, derived from the position.

    The capo is recoverable from the two coordinates themselves, so annotation
    does not need the constraints that produced them and cannot fall out of step
    with the position it is describing.
    """
    return position.physical.semitone_offset_from_nut - position.playing.semitone_offset_from_open


def _supporting_clauses(
    profile: InstrumentProfile, position: SpatialPosition, unit: PlayableUnitLabel
) -> tuple[str, ...]:
    """Facts that support the primary label without competing with it."""
    clauses: list[str] = []
    capo = _capo_semitones(position)
    if abs(capo) > POSITION_EPSILON:
        # The whole reason the coordinate model keeps these apart: with a capo
        # the fret the player counts is not the fret measured from the nut.
        if position.playing.is_open:
            clauses.append(f"open above the capo at {capo:.0f}")
        elif position.playing.fret_relative_to_capo is not None:
            clauses.append(
                f"fret {position.playing.fret_relative_to_capo} above the capo at {capo:.0f}"
            )
        else:
            clauses.append(
                f"{position.playing.semitone_offset_from_open:.2f} semitones above the "
                f"capo at {capo:.0f}"
            )
    elif position.playing.is_open:
        clauses.append("open string")
    if position.course_id is not None and len(unit.string_ids) > 1:
        clauses.append(f"sounded by {' and '.join(unit.string_ids)}")
    return tuple(clauses)


def annotate(
    *, position: SpatialPosition, profile: InstrumentProfile
) -> MappingAnnotation:
    """Describe one already-selected position in the instrument's own terms.

    Reads only. The position, the profile, and everything reachable from them are
    frozen dataclasses and none is rebuilt here, so annotating can never change
    what was selected.
    """
    unit = _unit_label(profile, position)
    pitch = _pitch_label(position)
    where = _position_label(profile, position)
    marker = _marker_for(profile, position)
    clauses = _supporting_clauses(profile, position, unit)

    primary = f"{unit.label}, {where}"
    accessibility = f"{pitch} on {unit.label.lower()}, {where}"
    if clauses:
        accessibility = f"{accessibility}, {', '.join(clauses)}"
    if marker is not None:
        accessibility = f"{accessibility}, at marker {marker.label}"

    return MappingAnnotation(
        primary_label=primary,
        secondary_label="; ".join(clauses) if clauses else None,
        pitch_label=pitch,
        string_label=unit.label,
        position_label=where,
        reference_marker_label=None if marker is None else marker.label,
        accessibility_text=f"{accessibility}.",
    )
