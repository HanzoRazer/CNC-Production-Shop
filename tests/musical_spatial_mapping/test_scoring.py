"""Candidate scoring tests.

Dev Order: MSME-002 Phase C

Scoring is characterized without any selection existing. The point of the split
is that a preference change must be able to move a score without moving the
candidate set, and only separate stages can prove that.
"""

from __future__ import annotations

import copy

import pytest

from musical_spatial_mapping.candidates import generate_candidates
from musical_spatial_mapping.enums import OpenStringPolicy
from musical_spatial_mapping.models import (
    CandidateScore,
    MappingConstraints,
    MappingPreferences,
)
from musical_spatial_mapping.scoring import (
    COMPONENT_ORDER,
    MOVEMENT,
    OPEN_STRING,
    POSITION,
    PREFERRED_REGION,
    STRING_CHANGE,
    score_candidate,
    score_candidates,
)

from .test_candidates import event, fretless_bass, guitar, mandolin

ZERO = MappingPreferences(
    movement_weight=0.0,
    string_change_weight=0.0,
    position_weight=0.0,
    preferred_region_weight=0.0,
    open_string_weight=0.0,
    lower_position_bias=0.0,
)


def generated(profile=None, midi=64, **kw):
    return generate_candidates(event=event(midi), profile=profile or guitar(), **kw).candidates


def scored(profile=None, midi=64, **kw):
    profile = profile or guitar()
    prefs = kw.pop("preferences", None)
    constraints = kw.pop("constraints", None)
    previous = kw.pop("previous_position", None)
    return score_candidates(
        candidates=generate_candidates(
            event=event(midi), profile=profile, constraints=constraints, **kw
        ).candidates,
        profile=profile,
        constraints=constraints,
        preferences=prefs,
        previous_position=previous,
    )


def on(candidates, string_id):
    return next(c for c in candidates if c.position.string_id == string_id)


# ------------------------------------------------------------------- boundaries


def test_every_generated_candidate_arrives_unscored():
    assert all(c.score is None for c in generated())


def test_scoring_populates_every_candidate():
    out = scored()
    assert out
    assert all(isinstance(c.score, CandidateScore) for c in out)


def test_scoring_adds_removes_and_reorders_nothing():
    before = generated()
    after = scored()
    assert len(after) == len(before)
    assert [c.position for c in after] == [c.position for c in before]


def test_scoring_does_not_mutate_the_original_candidates():
    before = generated()
    snapshot = copy.deepcopy(before)
    score_candidates(candidates=before, profile=guitar())
    assert before == snapshot
    assert all(c.score is None for c in before)


def test_scoring_does_not_mutate_its_inputs():
    profile, prefs = guitar(), MappingPreferences()
    constraints = MappingConstraints(capo_fret=2)
    ev = event(67)
    previous = generated()[0].position
    snapshots = tuple(copy.deepcopy(x) for x in (profile, prefs, constraints, ev, previous))
    made = generate_candidates(event=ev, profile=profile, constraints=constraints)
    score_candidates(
        candidates=made.candidates, profile=profile, constraints=constraints,
        preferences=prefs, previous_position=previous,
    )
    assert (profile, prefs, constraints, ev, previous) == snapshots


# ---------------------------------------------------------------------- totals


def test_total_is_the_sum_of_its_components():
    for c in scored():
        assert c.score is not None
        assert c.score.total == pytest.approx(sum(c.score.components.values()))


def test_every_component_is_always_present():
    for c in scored():
        assert c.score is not None
        assert tuple(c.score.components) == COMPONENT_ORDER


def test_zero_weights_produce_a_zero_score():
    for c in scored(preferences=ZERO):
        assert c.score is not None
        assert c.score.total == 0.0
        assert set(c.score.components.values()) == {0.0}


@pytest.mark.parametrize("component", [MOVEMENT, STRING_CHANGE, POSITION, OPEN_STRING])
def test_a_zero_weight_zeroes_only_its_own_component(component):
    weights = dict(
        movement_weight=1.0, string_change_weight=1.0,
        position_weight=1.0, open_string_weight=1.0,
    )
    weights[{MOVEMENT: "movement_weight", STRING_CHANGE: "string_change_weight",
             POSITION: "position_weight", OPEN_STRING: "open_string_weight"}[component]] = 0.0
    previous = on(generated(), "string-2").position
    out = scored(
        preferences=MappingPreferences(**weights),
        constraints=MappingConstraints(open_string_policy=OpenStringPolicy.AVOID),
        previous_position=previous,
    )
    assert all(c.score is not None and c.score.components[component] == 0.0 for c in out)


# ------------------------------------------------------------- previous position


def test_no_previous_position_means_no_movement_or_string_change():
    for c in scored(previous_position=None):
        assert c.score is not None
        assert c.score.components[MOVEMENT] == 0.0
        assert c.score.components[STRING_CHANGE] == 0.0


def test_staying_on_the_same_unit_costs_no_string_change():
    here = on(generated(), "string-5").position
    out = on(scored(previous_position=here), "string-5")
    assert out.score is not None
    assert out.score.components[STRING_CHANGE] == 0.0


def test_changing_unit_costs_the_configured_penalty():
    here = on(generated(), "string-5").position
    prefs = MappingPreferences(string_change_weight=3.0)
    out = on(scored(previous_position=here, preferences=prefs), "string-6")
    assert out.score is not None
    assert out.score.components[STRING_CHANGE] == 3.0


def test_moving_between_wires_of_one_course_is_not_a_string_change():
    """A mandolin player fingering a course has not changed strings."""
    cands = generate_candidates(event=event(74), profile=mandolin()).candidates
    first = cands[0]
    out = score_candidate(
        candidate=first, profile=mandolin(),
        previous_position=first.position,
        preferences=MappingPreferences(string_change_weight=5.0),
    )
    assert out.score is not None
    assert out.score.components[STRING_CHANGE] == 0.0


def test_greater_movement_costs_more():
    previous = on(generated(), "string-6").position  # E4 open, at the nut
    out = scored(previous_position=previous, preferences=MappingPreferences(movement_weight=1.0))
    near = on(out, "string-5")   # fret 5
    far = on(out, "string-2")    # fret 19
    assert near.score is not None and far.score is not None
    assert far.score.components[MOVEMENT] > near.score.components[MOVEMENT] > 0.0


# --------------------------------------------------------------------- fretless


def test_fretless_movement_scores_without_fret_numbers():
    profile = fretless_bass()
    cands = generate_candidates(event=event(50), profile=profile).candidates
    assert all(c.position.physical.fret_number is None for c in cands)
    previous = cands[0].position
    out = score_candidates(
        candidates=cands, profile=profile, previous_position=previous,
        preferences=MappingPreferences(movement_weight=1.0),
    )
    assert any(c.score is not None and c.score.components[MOVEMENT] > 0.0 for c in out)


def test_movement_is_scoreable_without_a_declared_scale_length():
    """Normalized position exists even when millimetres do not."""
    profile = fretless_bass(scale_length_mm=None)
    cands = generate_candidates(event=event(50), profile=profile).candidates
    assert all(c.position.physical.distance_from_nut_mm is None for c in cands)
    out = score_candidates(
        candidates=cands, profile=profile, previous_position=cands[0].position,
        preferences=MappingPreferences(movement_weight=1.0),
    )
    assert any(c.score is not None and c.score.components[MOVEMENT] > 0.0 for c in out)


def test_the_same_movement_costs_the_same_with_or_without_a_scale_length():
    """Declaring dimensions is documentation, and must not change the musical cost."""
    def movement(profile):
        cands = generate_candidates(event=event(50), profile=profile).candidates
        out = score_candidates(
            candidates=cands, profile=profile, previous_position=cands[0].position,
            preferences=MappingPreferences(movement_weight=1.0),
        )
        return [c.score.components[MOVEMENT] for c in out if c.score is not None]

    assert movement(fretless_bass(scale_length_mm=864.0)) == movement(
        fretless_bass(scale_length_mm=None)
    )


# -------------------------------------------------------------- preferred region


def test_a_preferred_region_miss_penalises_but_never_rejects():
    constraints = MappingConstraints(
        preferred_minimum_position=0.0, preferred_maximum_position=3.0
    )
    before = generated()
    after = scored(constraints=constraints,
                   preferences=MappingPreferences(preferred_region_weight=2.0))
    assert len(after) == len(before), "a soft miss must not remove a candidate"
    missed = on(after, "string-2")  # fret 19, far outside
    assert missed.score is not None
    assert missed.score.components[PREFERRED_REGION] > 0.0


def test_inside_the_preferred_region_costs_nothing():
    constraints = MappingConstraints(
        preferred_minimum_position=0.0, preferred_maximum_position=6.0
    )
    inside = on(scored(constraints=constraints), "string-5")  # fret 5
    assert inside.score is not None
    assert inside.score.components[PREFERRED_REGION] == 0.0


def test_a_region_miss_is_measured_by_how_far_outside_it_falls():
    tight = MappingConstraints(preferred_maximum_position=1.0)
    loose = MappingConstraints(preferred_maximum_position=4.0)
    prefs = MappingPreferences(preferred_region_weight=1.0)
    tighter = on(scored(constraints=tight, preferences=prefs), "string-5")
    looser = on(scored(constraints=loose, preferences=prefs), "string-5")
    assert tighter.score is not None and looser.score is not None
    assert tighter.score.components[PREFERRED_REGION] > looser.score.components[PREFERRED_REGION]


# ------------------------------------------------------------------ open string


def test_prefer_charges_fretted_positions():
    # E4: open on the high E string, fretted on four others. E2 would not do —
    # it is only reachable as the open low E, so there is no fretted case.
    out = scored(midi=64, constraints=MappingConstraints(
        open_string_policy=OpenStringPolicy.PREFER))
    open_c = next(c for c in out if c.position.playing.is_open)
    fretted = next(c for c in out if not c.position.playing.is_open)
    assert open_c.score is not None and fretted.score is not None
    assert open_c.score.components[OPEN_STRING] == 0.0
    assert fretted.score.components[OPEN_STRING] > 0.0


def test_avoid_charges_open_positions():
    out = scored(midi=64, constraints=MappingConstraints(
        open_string_policy=OpenStringPolicy.AVOID))
    open_c = next(c for c in out if c.position.playing.is_open)
    assert open_c.score is not None
    assert open_c.score.components[OPEN_STRING] > 0.0


# ------------------------------------------------------------ signed bias & misc


def test_a_negative_lower_position_bias_is_honoured_not_clamped():
    """MSME-001 calls it "an intentionally signed bias" and validates only finiteness.

    Clamping it to zero would silently delete a documented capability, so a
    negative bias is allowed to make a total go below zero.
    """
    prefs = MappingPreferences(
        movement_weight=0.0, string_change_weight=0.0, position_weight=0.0,
        preferred_region_weight=0.0, open_string_weight=0.0, lower_position_bias=-1.0,
    )
    high = on(scored(preferences=prefs), "string-2")  # fret 19, well up the neck
    assert high.score is not None
    assert high.score.total < 0.0


def test_changing_a_preference_changes_score_but_not_the_candidate_set():
    base = scored(preferences=MappingPreferences(position_weight=1.0))
    other = scored(preferences=MappingPreferences(position_weight=9.0))
    assert [c.position for c in base] == [c.position for c in other]
    assert [c.score.total for c in base if c.score] != [
        c.score.total for c in other if c.score
    ]


def test_scoring_is_deterministic():
    runs = [scored(previous_position=on(generated(), "string-5").position) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_explanations_name_only_the_components_that_cost_something():
    out = on(scored(preferences=MappingPreferences(position_weight=1.0)), "string-2")
    assert out.score is not None
    assert out.score.explanation
    assert all(POSITION in e or ":" in e for e in out.score.explanation)
    assert not any(e.startswith(f"{MOVEMENT}:") for e in out.score.explanation)
