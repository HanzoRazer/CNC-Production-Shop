"""Facade tests.

Dev Order: MSME-002 Phase F

End-to-end behaviour of the public API. The most important test here is the one
asserting that an unplayable pitch does NOT raise: that is where the Phase B
contract correction is actually felt by a caller.
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from musical_spatial_mapping.enums import SelectionStatus
from musical_spatial_mapping.errors import (
    EventValidationError,
    MappingConstraintError,
    ProfileValidationError,
    UnsupportedPitchError,
)
from musical_spatial_mapping.mapper import MusicalSpatialMapper, equal_best_of
from musical_spatial_mapping.models import (
    InstrumentProfile,
    MappingConstraints,
    MappingPreferences,
    MusicalEvent,
)

from .test_candidates import event, fretless_bass, guitar, mandolin

ALL_TIED = MappingPreferences(
    movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
    preferred_region_weight=0.0, open_string_weight=0.0, lower_position_bias=0.0,
)


def mapper(profile=None, **kw):
    return MusicalSpatialMapper(profile=profile or guitar(), **kw)


# ------------------------------------------------------------------- happy path


def test_a_normal_guitar_mapping_is_selected():
    r = mapper().map(event(64))
    assert r.status is SelectionStatus.SELECTED
    assert r.selected is not None
    assert r.annotation is not None
    assert r.instrument_id == "guitar.standard.6"
    assert r.event == event(64)


def test_every_returned_candidate_is_scored():
    r = mapper().map(event(64))
    assert r.candidates
    assert all(c.score is not None for c in r.candidates)


def test_the_annotation_describes_the_selected_candidate():
    r = mapper().map(event(64))
    assert r.selected is not None and r.annotation is not None
    assert r.annotation.string_label.endswith(r.selected.position.string_id.split("-")[1])


# --------------------------------------------------------------------- ambiguity


def test_an_exact_tie_is_ambiguous_but_still_selects():
    r = mapper(preferences=ALL_TIED).map(event(64))
    assert r.status is SelectionStatus.AMBIGUOUS
    assert r.selected is not None
    assert r.annotation is not None, "an ambiguous result is still renderable"


def test_the_tied_set_is_recoverable_from_the_result():
    r = mapper(preferences=ALL_TIED).map(event(64))
    tied = equal_best_of(r)
    assert len(tied) > 1
    assert r.selected in tied
    assert any("ambiguous:" in d for d in r.diagnostics)


def test_a_unique_best_leaves_one_candidate_in_the_tied_set():
    r = mapper(preferences=MappingPreferences(position_weight=1.0)).map(event(64))
    assert r.status is SelectionStatus.SELECTED
    assert len(equal_best_of(r)) == 1


# -------------------------------------------------------------------- unplayable


def test_an_unplayable_pitch_does_not_raise():
    """The Phase B contract correction, pinned at the public boundary.

    MSME-001 documented UnsupportedPitchError for "a note below every open
    string". That is ordinary unplayability and must be an outcome, or every
    caller mapping a melody ends up doing exception control flow over notes.
    """
    r = mapper().map(event(30))  # below the low E
    assert r.status is SelectionStatus.UNPLAYABLE
    assert r.selected is None
    assert r.candidates == ()


def test_an_unplayable_pitch_never_raises_unsupported_pitch_error():
    for midi in (0, 30, 39, 100, 127):
        try:
            result = mapper().map(event(midi))
        except UnsupportedPitchError as exc:  # pragma: no cover - failure path
            pytest.fail(f"midi {midi} raised UnsupportedPitchError: {exc}")
        assert result.status in (SelectionStatus.SELECTED, SelectionStatus.AMBIGUOUS,
                                 SelectionStatus.UNPLAYABLE)


def test_unplayable_preserves_the_rejection_evidence():
    r = mapper().map(event(30))
    assert r.diagnostics, "an UNPLAYABLE result that says only 'none' is useless"
    assert all("—" in d for d in r.diagnostics)
    assert any("below_open_pitch" in d for d in r.diagnostics)


def test_constraints_that_eliminate_everything_are_unplayable_not_an_error():
    m = mapper(constraints=MappingConstraints(
        allowed_string_ids=frozenset({"string-6"}), minimum_position=5.0))
    r = m.map(event(64))
    assert r.status is SelectionStatus.UNPLAYABLE
    assert any("position_constraint" in d for d in r.diagnostics)


def test_selection_is_not_invoked_when_nothing_is_playable(monkeypatch):
    """Phase D's stricter contract stays intact: the facade branches first."""
    import musical_spatial_mapping.mapper as mapper_module

    def explode(**_kw):  # pragma: no cover - must never run
        raise AssertionError("selection was called with no candidates")

    monkeypatch.setattr(mapper_module, "select_candidate", explode)
    assert mapper().map(event(30)).status is SelectionStatus.UNPLAYABLE


# -------------------------------------------------------------------------- capo


def test_capo_survives_end_to_end_with_both_coordinates():
    m = mapper(constraints=MappingConstraints(capo_fret=2))
    r = m.map(event(67))
    assert r.selected is not None
    physical = r.selected.position.physical
    playing = r.selected.position.playing
    assert physical.fret_number != playing.fret_relative_to_capo
    assert r.annotation is not None
    assert "capo" in (r.annotation.secondary_label or "")


def test_a_capo_beyond_the_neck_fails_closed():
    m = mapper(constraints=MappingConstraints(capo_fret=99))
    with pytest.raises(MappingConstraintError):
        m.map(event(64))


# -------------------------------------------------------------- previous position


def test_previous_position_can_change_the_selection():
    base = mapper(preferences=MappingPreferences(
        movement_weight=0.0, string_change_weight=0.0, position_weight=1.0))
    without = base.map(event(64))
    anchor = next(
        c for c in without.candidates if c.position.string_id == "string-2"
    ).position
    heavy = mapper(preferences=MappingPreferences(
        movement_weight=50.0, string_change_weight=0.0, position_weight=1.0))
    with_prev = heavy.map(event(64), previous_position=anchor)
    assert without.selected is not None and with_prev.selected is not None
    assert with_prev.selected.position != without.selected.position


def test_no_previous_position_gives_stateless_single_note_behaviour():
    m = mapper()
    a = m.map(event(64))
    b = m.map(event(64), previous_position=None)
    assert a == b


def test_the_mapper_keeps_no_memory_between_calls():
    m = mapper(preferences=MappingPreferences(movement_weight=50.0))
    first = m.map(event(64))
    anchor = first.candidates[-1].position
    m.map(event(64), previous_position=anchor)
    assert m.map(event(64)) == first, "a later call must not inherit the prior position"


def test_the_mapper_is_frozen():
    m = mapper()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.profile = mandolin()  # type: ignore[misc]


# ---------------------------------------------------------- instruments & purity


def test_fretless_mapping_survives_the_facade():
    r = mapper(fretless_bass()).map(event(50))
    assert r.status in (SelectionStatus.SELECTED, SelectionStatus.AMBIGUOUS)
    assert r.selected is not None
    assert r.selected.position.physical.fret_number is None
    assert r.annotation is not None and "fret" not in r.annotation.accessibility_text


def test_mandolin_mapping_stays_at_course_level():
    r = mapper(mandolin()).map(event(74))
    assert r.selected is not None
    assert r.selected.position.course_id is not None
    assert r.annotation is not None and r.annotation.string_label.startswith("Course")
    identities = [c.position.course_id for c in r.candidates]
    assert len(identities) == len(set(identities)), "no course appears twice"


def test_repeated_identical_calls_return_identical_results():
    m = mapper(preferences=ALL_TIED)
    results = [m.map(event(64)) for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_mapping_mutates_none_of_its_inputs():
    profile = mandolin()
    constraints = MappingConstraints(capo_fret=2)
    preferences = MappingPreferences(movement_weight=2.0)
    ev = event(74)
    previous = mapper(profile).map(ev).candidates[0].position
    snapshot = copy.deepcopy((profile, constraints, preferences, ev, previous))
    MusicalSpatialMapper(
        profile=profile, constraints=constraints, preferences=preferences
    ).map(ev, previous_position=previous)
    assert (profile, constraints, preferences, ev, previous) == snapshot


# -------------------------------------------------------------------- fail closed


def test_an_invalid_event_fails_closed():
    with pytest.raises(EventValidationError):
        mapper().map(MusicalEvent("bad", 999, 0, 480))


def test_an_invalid_profile_fails_closed():
    broken = InstrumentProfile(**{**guitar().__dict__, "strings": ()})
    with pytest.raises(ProfileValidationError):
        MusicalSpatialMapper(profile=broken).map(event(64))


def test_invalid_constraints_fail_closed():
    with pytest.raises(MappingConstraintError):
        mapper(constraints=MappingConstraints(capo_fret=-1)).map(event(64))


def test_invalid_preferences_fail_closed():
    with pytest.raises(MappingConstraintError):
        mapper(preferences=MappingPreferences(movement_weight=-1.0)).map(event(64))
