"""Annotation tests.

Dev Order: MSME-002 Phase E

The defended properties: fretless prose never invents a fret, a course is named
as one playable unit rather than two wires, and a capo keeps the two coordinates
visibly distinct in the text a user actually reads.
"""

from __future__ import annotations

import copy

from musical_spatial_mapping.annotation import annotate
from musical_spatial_mapping.candidates import generate_candidates
from musical_spatial_mapping.models import (
    InstrumentProfile,
    MappingAnnotation,
    MappingConstraints,
    ReferenceMarker,
)

from .test_candidates import event, fretless_bass, guitar, mandolin


def position(profile, midi, string_id=None, **kw):
    cands = generate_candidates(event=event(midi), profile=profile, **kw).candidates
    if string_id is None:
        return cands[0].position
    return next(c for c in cands if c.position.string_id == string_id).position


def all_text(a: MappingAnnotation) -> str:
    parts = [
        a.primary_label, a.secondary_label or "", a.pitch_label,
        a.string_label, a.position_label, a.reference_marker_label or "",
        a.accessibility_text,
    ]
    return " ".join(parts).lower()


# ----------------------------------------------------------------------- fretted


def test_a_fretted_guitar_position_names_its_string_and_fret():
    a = annotate(position=position(guitar(), 64, "string-5"), profile=guitar())
    assert a.string_label == "String 5"
    assert a.position_label == "fret 5"
    assert a.primary_label == "String 5, fret 5"
    assert a.pitch_label == "E4"
    assert a.accessibility_text.endswith(".")


def test_an_open_string_says_so():
    a = annotate(position=position(guitar(), 64, "string-6"), profile=guitar())
    assert a.position_label == "fret 0"
    assert a.secondary_label is not None and "open string" in a.secondary_label


# ---------------------------------------------------------------------- fretless


def test_a_fretless_position_never_claims_a_fret():
    """The rule this module exists to enforce."""
    pos = position(fretless_bass(), 50)
    assert pos.physical.fret_number is None
    a = annotate(position=pos, profile=fretless_bass())
    assert "fret" not in all_text(a)


def test_a_fretless_position_uses_position_language():
    a = annotate(position=position(fretless_bass(), 50), profile=fretless_bass())
    assert "semitones from the nut" in a.position_label
    assert "mm" in a.position_label, "scale length is known, so millimetres are available"


def test_a_fretless_position_without_a_scale_length_drops_only_millimetres():
    profile = fretless_bass(scale_length_mm=None)
    a = annotate(position=position(profile, 50), profile=profile)
    assert "semitones from the nut" in a.position_label
    assert "mm" not in a.position_label
    assert "fret" not in all_text(a)


def test_a_microtonal_fretless_pitch_is_labelled_with_its_cents():
    profile = fretless_bass()
    cands = generate_candidates(
        event=event(50, cents=50.0), profile=profile
    ).candidates
    a = annotate(position=cands[0].position, profile=profile)
    assert "+50c" in a.pitch_label


# ------------------------------------------------------------------------ course


def test_a_course_is_named_once_not_as_two_wires():
    pos = position(mandolin(), 74)
    a = annotate(position=pos, profile=mandolin())
    assert a.string_label.startswith("Course ")
    assert a.primary_label.startswith("Course ")


def test_course_membership_appears_only_as_supporting_detail():
    pos = position(mandolin(), 74)
    a = annotate(position=pos, profile=mandolin())
    assert a.secondary_label is not None
    assert "sounded by" in a.secondary_label
    # Both wires are named as membership, never as an alternative choice.
    assert a.secondary_label.count("string-") == 2
    assert "or" not in a.secondary_label


def test_an_ordinary_string_is_not_called_a_course():
    a = annotate(position=position(guitar(), 64, "string-5"), profile=guitar())
    assert "course" not in all_text(a)


# ------------------------------------------------------------- reference markers


def test_a_position_on_a_marker_reports_it():
    profile = fretless_bass()
    marked = InstrumentProfile(**{**profile.__dict__, "reference_markers": (
        ReferenceMarker(marker_id="pos-12", semitone_offset=12.0, label="12"),
    )})
    a = annotate(position=position(marked, 40, "string-1"), profile=marked)
    assert a.reference_marker_label == "12"
    assert "marker 12" in a.accessibility_text


def test_a_position_with_no_marker_reports_none():
    profile = fretless_bass()
    marked = InstrumentProfile(**{**profile.__dict__, "reference_markers": (
        ReferenceMarker(marker_id="pos-12", semitone_offset=12.0, label="12"),
    )})
    a = annotate(position=position(marked, 44, "string-1"), profile=marked)
    assert a.reference_marker_label is None
    assert "marker" not in a.accessibility_text


def test_a_marker_does_not_change_the_position_it_describes():
    profile = fretless_bass()
    marked = InstrumentProfile(**{**profile.__dict__, "reference_markers": (
        ReferenceMarker(marker_id="pos-12", semitone_offset=12.0, label="12"),
    )})
    pos = position(marked, 40, "string-1")
    before = copy.deepcopy(pos)
    annotate(position=pos, profile=marked)
    assert pos == before


# -------------------------------------------------------------------------- capo


def test_a_capo_keeps_both_coordinates_visible():
    """The regression the coordinate model exists for, now in the prose.

    Capo 2, G4 on the high E string: fret 3 from the nut, fret 1 above the capo.
    An annotation reporting only one of those has erased the distinction.
    """
    pos = position(guitar(), 67, "string-6", constraints=MappingConstraints(capo_fret=2))
    assert pos.physical.fret_number == 3
    assert pos.playing.fret_relative_to_capo == 1
    a = annotate(position=pos, profile=guitar())
    assert a.position_label == "fret 3", "position_label reports the PHYSICAL fret"
    assert a.secondary_label is not None
    assert "fret 1 above the capo" in a.secondary_label


def test_without_a_capo_no_capo_language_appears():
    a = annotate(position=position(guitar(), 64, "string-5"), profile=guitar())
    assert "capo" not in all_text(a)


def test_an_open_position_under_a_capo_is_described_as_such():
    pos = position(guitar(), 66, "string-6", constraints=MappingConstraints(capo_fret=2))
    assert pos.playing.is_open is True
    a = annotate(position=pos, profile=guitar())
    assert a.secondary_label is not None and "open above the capo" in a.secondary_label
    assert a.position_label == "fret 2", "still fret 2 from the nut"


# ---------------------------------------------------------- determinism & purity


def test_annotation_is_deterministic():
    pos = position(guitar(), 64, "string-5")
    results = [annotate(position=pos, profile=guitar()) for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_annotation_mutates_neither_profile_nor_position():
    profile = mandolin()
    pos = position(profile, 74)
    snapshot = copy.deepcopy((profile, pos))
    annotate(position=pos, profile=profile)
    assert (profile, pos) == snapshot


def test_accessibility_text_is_always_populated():
    for profile, midi in ((guitar(), 64), (fretless_bass(), 50), (mandolin(), 74)):
        a = annotate(position=position(profile, midi), profile=profile)
        assert a.accessibility_text.strip()
        assert a.pitch_label in a.accessibility_text


def test_annotation_carries_no_presentation_semantics():
    """Semantic labels, not graphics — no colours, pixels, or coordinates."""
    a = annotate(position=position(guitar(), 64, "string-5"), profile=guitar())
    text = all_text(a)
    for banned in ("colour", "color", "pixel", "rgb", "#", "x=", "y="):
        assert banned not in text
