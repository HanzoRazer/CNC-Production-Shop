"""Deterministic selection tests.

Dev Order: MSME-002 Phase D

The two properties worth defending here are that ambiguity survives tie-breaking,
and that the winner never depends on anything outside the governed data — not
insertion order, not presentation metadata, not the order the caller happened to
build its list in.
"""

from __future__ import annotations

import copy
import random

import pytest

from musical_spatial_mapping.candidates import generate_candidates
from musical_spatial_mapping.errors import SelectionInputError
from musical_spatial_mapping.models import (
    InstrumentProfile,
    MappingPreferences,
    StringProfile,
)
from musical_spatial_mapping.scoring import score_candidates
from musical_spatial_mapping.selection import (
    SelectionOutcome,
    select_candidate,
    unit_identity,
)

from .test_candidates import event, fretless_bass, guitar, mandolin

# Zeroing every weight makes every total exactly 0.0, so the whole set ties and
# only the tie-break can decide. Ties here are genuine equality, not drift.
ALL_TIED = MappingPreferences(
    movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
    preferred_region_weight=0.0, open_string_weight=0.0, lower_position_bias=0.0,
)


def scored(profile=None, midi=64, preferences=None):
    profile = profile or guitar()
    cands = generate_candidates(event=event(midi), profile=profile).candidates
    return profile, score_candidates(
        candidates=cands, profile=profile, preferences=preferences
    )


def select(profile=None, midi=64, preferences=None):
    profile, cands = scored(profile, midi, preferences)
    return select_candidate(candidates=cands, profile=profile)


# -------------------------------------------------------------------- refusals


def test_an_empty_candidate_set_is_refused():
    """UNPLAYABLE belongs to orchestration; selection must not manufacture it."""
    with pytest.raises(SelectionInputError, match="non-empty"):
        select_candidate(candidates=(), profile=guitar())


def test_an_unscored_candidate_is_refused():
    """A pipeline error, not a musical outcome."""
    unscored = generate_candidates(event=event(64), profile=guitar()).candidates
    with pytest.raises(SelectionInputError, match="unscored"):
        select_candidate(candidates=unscored, profile=guitar())


def test_a_partially_scored_set_is_refused():
    profile, cands = scored()
    mixed = cands[:-1] + generate_candidates(event=event(64), profile=profile).candidates[-1:]
    with pytest.raises(SelectionInputError, match="unscored"):
        select_candidate(candidates=mixed, profile=profile)


# ------------------------------------------------------------ unique vs ambiguous


def test_a_unique_minimum_is_not_ambiguous():
    out = select(preferences=MappingPreferences(position_weight=1.0))
    assert isinstance(out, SelectionOutcome)
    assert out.is_ambiguous is False
    assert len(out.equal_best) == 1
    assert out.winner is out.equal_best[0]


def test_an_exact_tie_is_ambiguous_and_still_names_a_winner():
    out = select(preferences=ALL_TIED)
    assert out.is_ambiguous is True
    assert len(out.equal_best) > 1
    assert out.winner is not None
    assert out.winner in out.equal_best


def test_more_than_two_equal_best_candidates():
    out = select(preferences=ALL_TIED)
    assert len(out.equal_best) >= 3


def test_tie_breaking_does_not_make_the_result_unambiguous():
    """The tie-break makes the answer repeatable, not unique."""
    out = select(preferences=ALL_TIED)
    assert out.winner is not None and out.is_ambiguous is True


def test_equal_best_contains_only_the_minimum_total():
    out = select(preferences=MappingPreferences(position_weight=1.0))
    best = out.winner.score.total
    assert all(c.score.total == best for c in out.equal_best)


# ------------------------------------------------------------------ determinism


def test_repeated_selection_returns_the_same_winner():
    results = [select(preferences=ALL_TIED).winner.position for _ in range(10)]
    assert all(r == results[0] for r in results)


def test_input_order_does_not_change_the_winner():
    """No reliance on insertion order, object identity, or source-list position."""
    profile, cands = scored(preferences=ALL_TIED)
    baseline = select_candidate(candidates=cands, profile=profile).winner.position
    rng = random.Random(20260810)
    for _ in range(25):
        shuffled = list(cands)
        rng.shuffle(shuffled)
        out = select_candidate(candidates=tuple(shuffled), profile=profile)
        assert out.winner.position == baseline


def test_equal_best_is_reported_in_a_stable_order():
    profile, cands = scored(preferences=ALL_TIED)
    rng = random.Random(7)
    baseline = [c.position for c in select_candidate(
        candidates=cands, profile=profile).equal_best]
    for _ in range(10):
        shuffled = list(cands)
        rng.shuffle(shuffled)
        out = select_candidate(candidates=tuple(shuffled), profile=profile)
        assert [c.position for c in out.equal_best] == baseline


# ------------------------------------------------------------------- tie-break


def test_the_higher_pitched_unit_wins_a_tie():
    """Key 2: open pitch descending — for one sounding pitch that is the lower fret."""
    out = select(preferences=ALL_TIED)
    profile, _ = scored(preferences=ALL_TIED)
    opens = {s.string_id: s.open_midi_note for s in profile.strings}
    winner_open = opens[out.winner.position.string_id]
    assert winner_open == max(opens[c.position.string_id] for c in out.equal_best)


def test_display_order_is_not_used_in_the_tie_break():
    """Presentation metadata carries an unenforced convention and must not decide.

    Same instrument, same pitches, numbering inverted. If display_order leaked
    into the tie-break the winner would flip.
    """
    normal = guitar()
    inverted = InstrumentProfile(**{**normal.__dict__, "strings": tuple(
        StringProfile(**{**s.__dict__, "display_order": 7 - s.display_order})
        for s in normal.strings
    )})
    a = select_candidate(
        candidates=score_candidates(
            candidates=generate_candidates(event=event(64), profile=normal).candidates,
            profile=normal, preferences=ALL_TIED),
        profile=normal,
    )
    b = select_candidate(
        candidates=score_candidates(
            candidates=generate_candidates(event=event(64), profile=inverted).candidates,
            profile=inverted, preferences=ALL_TIED),
        profile=inverted,
    )
    assert a.winner.position.string_id == b.winner.position.string_id


def test_a_worse_score_can_never_win_on_tie_break_fields():
    """Tie-break fields order the equal-best set; they never overrule the score.

    The high E string wins every tie-break dimension, so if the keys could beat
    the total it would win outright. Weighted so it scores worst, it must lose.
    """
    profile = guitar()
    cands = generate_candidates(event=event(64), profile=profile).candidates
    scored_set = score_candidates(
        candidates=cands, profile=profile,
        preferences=MappingPreferences(
            movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
            preferred_region_weight=0.0, open_string_weight=0.0,
            # Negative bias rewards distance from the nut, so the open high E
            # (normalized 0.0) becomes the WORST candidate.
            lower_position_bias=-1.0,
        ),
    )
    out = select_candidate(candidates=scored_set, profile=profile)
    assert out.winner.position.string_id != "string-6"
    assert out.winner.score.total == min(c.score.total for c in scored_set)


def test_negative_totals_compare_correctly():
    """A signed bias can drive totals below zero; minimum still means minimum."""
    profile = guitar()
    scored_set = score_candidates(
        candidates=generate_candidates(event=event(64), profile=profile).candidates,
        profile=profile,
        preferences=MappingPreferences(
            movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
            preferred_region_weight=0.0, open_string_weight=0.0,
            lower_position_bias=-2.0,
        ),
    )
    totals = [c.score.total for c in scored_set]
    assert min(totals) < 0.0
    out = select_candidate(candidates=scored_set, profile=profile)
    assert out.winner.score.total == min(totals)


# ------------------------------------------------------------ courses & fretless


def test_a_course_tie_is_decided_on_course_identity():
    profile, cands = scored(mandolin(), 74, ALL_TIED)
    out = select_candidate(candidates=cands, profile=profile)
    assert out.winner.position.course_id is not None
    assert unit_identity(out.winner.position) == out.winner.position.course_id
    # One candidate per course, so no two entries share an identity.
    identities = [unit_identity(c.position) for c in out.equal_best]
    assert len(identities) == len(set(identities))


def test_paired_wires_never_compete_as_separate_choices():
    profile, cands = scored(mandolin(), 74, ALL_TIED)
    out = select_candidate(candidates=cands, profile=profile)
    assert all(unit_identity(c.position).startswith("course-") for c in out.equal_best)


def test_a_fretless_tie_is_decided_without_fret_numbers():
    profile, cands = scored(fretless_bass(), 50, ALL_TIED)
    out = select_candidate(candidates=cands, profile=profile)
    assert all(c.position.physical.fret_number is None for c in out.equal_best)
    assert out.winner is not None
    assert out.is_ambiguous is (len(out.equal_best) > 1)


def test_fretless_without_a_scale_length_still_selects():
    profile, cands = scored(fretless_bass(scale_length_mm=None), 50, ALL_TIED)
    out = select_candidate(candidates=cands, profile=profile)
    assert out.winner.position.physical.distance_from_nut_mm is None


# -------------------------------------------------------------------- immutability


def test_selection_mutates_nothing():
    profile, cands = scored(preferences=ALL_TIED)
    snapshot = copy.deepcopy((profile, cands))
    select_candidate(candidates=cands, profile=profile)
    assert (profile, cands) == snapshot


def test_selection_returns_the_original_candidate_objects():
    """The winner is one of the inputs, not a rebuilt copy carrying a new score."""
    profile, cands = scored(preferences=MappingPreferences(position_weight=1.0))
    out = select_candidate(candidates=cands, profile=profile)
    assert any(out.winner is c for c in cands)
