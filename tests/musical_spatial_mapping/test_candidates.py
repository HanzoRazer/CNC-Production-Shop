"""Candidate generation tests.

Dev Order: MSME-002 Phase B

Generation is characterized on its own here, before any scoring exists. That is
deliberate: if these tests passed only once ranking was in place, a change to
scoring policy could silently change which locations the engine believes exist.
"""

from __future__ import annotations

import pytest

from musical_spatial_mapping.candidates import (
    generate_candidates,
    playable_units,
)
from musical_spatial_mapping.enums import FingerboardMode, OpenStringPolicy, RejectionCode
from musical_spatial_mapping.models import (
    InstrumentProfile,
    MappingConstraints,
    MusicalEvent,
    StringProfile,
)

# Standard tuning, low to high: E2 A2 D3 G3 B3 E4.
GUITAR_OPEN = (40, 45, 50, 55, 59, 64)


def _string(order: int, midi: int, *, course: str | None = None, **kw) -> StringProfile:
    return StringProfile(
        string_id=kw.pop("string_id", f"string-{order}"),
        display_label=str(order),
        display_order=order,
        open_midi_note=midi,
        course_id=course,
        **kw,
    )


def guitar(**kw) -> InstrumentProfile:
    return InstrumentProfile(
        schema_version="1.0",
        instrument_id="guitar.standard.6",
        display_name="Guitar",
        family="guitar",
        fingerboard_mode=FingerboardMode.FRETTED,
        strings=tuple(_string(i + 1, m) for i, m in enumerate(GUITAR_OPEN)),
        scale_length_mm=kw.pop("scale_length_mm", 648.0),
        fret_count=kw.pop("fret_count", 22),
        **kw,
    )


def mandolin() -> InstrumentProfile:
    """Eight strings, four unison courses — four independent choices."""
    pairs = (("course-g", 55), ("course-d", 62), ("course-a", 69), ("course-e", 76))
    strings = []
    order = 1
    for course_id, midi in pairs:
        for _ in range(2):
            strings.append(_string(order, midi, course=course_id))
            order += 1
    return InstrumentProfile(
        schema_version="1.0",
        instrument_id="mandolin.standard.8",
        display_name="Mandolin",
        family="mandolin",
        fingerboard_mode=FingerboardMode.FRETTED,
        strings=tuple(strings),
        scale_length_mm=350.0,
        fret_count=20,
    )


def fretless_bass(*, scale_length_mm: float | None = 864.0) -> InstrumentProfile:
    return InstrumentProfile(
        schema_version="1.0",
        instrument_id="bass.fretless.4",
        display_name="Fretless bass",
        family="bass",
        fingerboard_mode=FingerboardMode.FRETLESS,
        strings=tuple(_string(i + 1, m) for i, m in enumerate((28, 33, 38, 43))),
        scale_length_mm=scale_length_mm,
        fret_count=None,
    )


def event(midi: int, *, cents: float = 0.0) -> MusicalEvent:
    return MusicalEvent(
        event_id="e1", midi_note=midi, start_tick=0, duration_ticks=480, cents_offset=cents
    )


def gen(profile, midi, **kw):
    return generate_candidates(event=event(midi), profile=profile, **kw)


# ------------------------------------------------------------------ playable units


def test_a_guitar_string_is_its_own_playable_unit():
    units = playable_units(guitar())
    assert len(units) == 6
    assert all(u.course_id is None for u in units)


def test_a_mandolin_course_is_one_unit_not_two():
    """Eight wires, four choices. This is instrument topology, not selection policy."""
    units = playable_units(mandolin())
    assert len(units) == 4
    assert [u.course_id for u in units] == ["course-g", "course-d", "course-a", "course-e"]
    assert all(len(u.member_strings) == 2 for u in units)


def test_units_are_ordered_deterministically_regardless_of_profile_order():
    forward = guitar()
    reversed_profile = InstrumentProfile(
        **{**forward.__dict__, "strings": tuple(reversed(forward.strings))}
    )
    assert [u.unit_id for u in playable_units(forward)] == [
        u.unit_id for u in playable_units(reversed_profile)
    ]


def test_a_course_adopts_its_most_restrictive_member_limit():
    """The finger stops where the shortest playable wire stops."""
    strings = (
        _string(1, 55, course="course-g", max_position=12.0),
        _string(2, 55, course="course-g", max_position=7.0),
    )
    profile = InstrumentProfile(
        schema_version="1.0", instrument_id="x", display_name="x", family="x",
        fingerboard_mode=FingerboardMode.FRETTED, strings=strings,
        scale_length_mm=350.0, fret_count=20,
    )
    assert playable_units(profile)[0].max_position == 7.0


def test_unison_strings_without_a_course_id_stay_separate():
    """Equal open pitch is NOT evidence of a mechanical course."""
    strings = (_string(1, 55), _string(2, 55))
    profile = InstrumentProfile(
        schema_version="1.0", instrument_id="x", display_name="x", family="x",
        fingerboard_mode=FingerboardMode.FRETTED, strings=strings,
        scale_length_mm=350.0, fret_count=20,
    )
    assert len(playable_units(profile)) == 2


# --------------------------------------------------------------------- generation


def test_a_pitch_playable_on_several_strings_yields_several_candidates():
    # E4 (64) is the open 1st string and also fret 5 of the B string, etc.
    out = gen(guitar(), 64)
    assert len(out.candidates) > 1
    assert all(c.score is None for c in out.candidates), "generation must not score"


def test_an_open_string_candidate_is_marked_open():
    out = gen(guitar(), 40)  # low E, open on string 6
    opens = [c for c in out.candidates if c.position.playing.is_open]
    assert len(opens) == 1
    assert opens[0].position.physical.fret_number == 0


def test_open_string_policy_exclude_removes_it():
    out = gen(guitar(), 40, constraints=MappingConstraints(
        open_string_policy=OpenStringPolicy.EXCLUDE))
    assert not [c for c in out.candidates if c.position.playing.is_open]
    assert RejectionCode.OPEN_STRING_EXCLUDED in {r.code for r in out.rejections}


@pytest.mark.parametrize("policy", [OpenStringPolicy.PREFER, OpenStringPolicy.AVOID])
def test_prefer_and_avoid_are_scoring_not_rejection(policy):
    out = gen(guitar(), 40, constraints=MappingConstraints(open_string_policy=policy))
    assert [c for c in out.candidates if c.position.playing.is_open]


def test_pitch_below_every_string_produces_no_candidates_and_says_why():
    out = gen(guitar(), 30)  # below low E
    assert out.candidates == ()
    assert {r.code for r in out.rejections} == {RejectionCode.BELOW_OPEN_PITCH}
    assert len(out.rejections) == 6


def test_pitch_above_the_neck_produces_no_candidates_and_says_why():
    out = gen(guitar(fret_count=22), 100)
    assert out.candidates == ()
    assert {r.code for r in out.rejections} == {RejectionCode.ABOVE_POSITION_RANGE}


def test_a_constraint_can_eliminate_some_candidates():
    # string-1 is the LOW E: E4 sits at fret 24 there and is already out of range,
    # so exclude string-3 (D3), which genuinely contributes a candidate at fret 14.
    unconstrained = gen(guitar(), 64)
    constrained = gen(guitar(), 64, constraints=MappingConstraints(
        excluded_string_ids=frozenset({"string-3"})))
    assert len(constrained.candidates) == len(unconstrained.candidates) - 1
    assert RejectionCode.STRING_EXCLUDED in {r.code for r in constrained.rejections}


def test_a_constraint_can_eliminate_every_candidate():
    # Only the high E permitted, but it sounds E4 open — below a minimum of 5.
    out = gen(guitar(), 64, constraints=MappingConstraints(
        allowed_string_ids=frozenset({"string-6"}), minimum_position=5.0))
    assert out.candidates == ()
    assert out.rejections


def test_instrument_limits_and_caller_limits_use_different_codes():
    """UNPLAYABLE must be able to say WHICH kind of limit killed every location.

    An instrument that runs out of neck and a caller who narrowed the window are
    different answers to "why can't I play this", and one shared code destroys
    the distinction. The low bound previously borrowed BELOW_OPEN_PITCH and the
    high bound borrowed ABOVE_POSITION_RANGE, so a caller's own window was
    indistinguishable from the instrument's physical range.
    """
    # Instrument ran out of neck: every unit reports the feasibility code.
    instrument = gen(guitar(fret_count=22), 100)
    assert {r.code for r in instrument.rejections} == {RejectionCode.ABOVE_POSITION_RANGE}

    # Caller narrowed the window. Restricted to the B string alone, where E4 sits
    # at a perfectly playable fret 5, so nothing but the caller's bound can fire.
    only_b = frozenset({"string-5"})
    caller_high = gen(guitar(), 64, constraints=MappingConstraints(
        allowed_string_ids=only_b, maximum_position=2.0))
    caller_low = gen(guitar(), 64, constraints=MappingConstraints(
        allowed_string_ids=only_b, minimum_position=9.0))
    for outcome in (caller_high, caller_low):
        codes = {r.code for r in outcome.rejections if r.string_ids == ("string-5",)}
        assert codes == {RejectionCode.POSITION_CONSTRAINT}


def test_a_caller_window_never_reports_an_instrument_feasibility_code():
    """The specific regression: minimum_position must not read as BELOW_OPEN_PITCH."""
    out = gen(guitar(), 59, constraints=MappingConstraints(
        allowed_string_ids=frozenset({"string-5"}), minimum_position=4.0))
    assert out.candidates == ()
    codes = {r.code for r in out.rejections if r.string_ids == ("string-5",)}
    assert codes == {RejectionCode.POSITION_CONSTRAINT}


def test_disabled_strings_are_not_candidates():
    profile = guitar()
    strings = tuple(
        StringProfile(**{**s.__dict__, "enabled": s.string_id != "string-1"})
        for s in profile.strings
    )
    out = gen(InstrumentProfile(**{**profile.__dict__, "strings": strings}), 64)
    assert "string-1" not in {c.position.string_id for c in out.candidates}


# --------------------------------------------------------------------------- capo


def test_capo_separates_physical_and_playing_position():
    """The regression the coordinate model exists for.

    Capo 2, playing G4 (67) on the high E string: physically fret 3 from the nut,
    but only 1 above the capo. Any implementation collapsing these into one
    integer fails here.
    """
    out = gen(guitar(), 67, constraints=MappingConstraints(capo_fret=2))
    high_e = next(c for c in out.candidates if c.position.string_id == "string-6")
    assert high_e.position.physical.fret_number == 3
    assert high_e.position.playing.fret_relative_to_capo == 1
    assert high_e.position.physical.fret_number != high_e.position.playing.fret_relative_to_capo


def test_capo_makes_the_capoed_pitch_the_new_open():
    out = gen(guitar(), 66, constraints=MappingConstraints(capo_fret=2))
    high_e = next(c for c in out.candidates if c.position.string_id == "string-6")
    assert high_e.position.playing.is_open is True
    assert high_e.position.physical.fret_number == 2, "still fret 2 from the nut"


def test_a_pitch_under_the_capo_is_a_capo_conflict():
    out = gen(guitar(), 64, constraints=MappingConstraints(capo_fret=5))
    assert RejectionCode.CAPO_CONFLICT in {r.code for r in out.rejections}


def test_capo_does_not_mutate_the_profile():
    profile = guitar()
    before = tuple(s.open_midi_note for s in profile.strings)
    gen(profile, 67, constraints=MappingConstraints(capo_fret=4))
    assert tuple(s.open_midi_note for s in profile.strings) == before


# ----------------------------------------------------------------------- fretless


def test_fretless_positions_carry_no_fret_but_keep_a_position():
    out = gen(fretless_bass(), 40)
    assert out.candidates
    for c in out.candidates:
        assert c.position.physical.fret_number is None
        assert c.position.playing.fret_relative_to_capo is None
        assert 0.0 <= c.position.physical.normalized_position < 1.0


def test_fretless_reports_physical_mm_when_scale_length_is_known():
    c = gen(fretless_bass(scale_length_mm=864.0), 40).candidates[0]
    assert c.position.physical.distance_from_nut_mm is not None
    assert c.position.physical.distance_from_nut_mm > 0


def test_absent_scale_length_keeps_normalized_position():
    c = gen(fretless_bass(scale_length_mm=None), 40).candidates[0]
    assert c.position.physical.distance_from_nut_mm is None
    assert c.position.physical.normalized_position > 0


def test_a_fretless_instrument_accepts_a_microtone():
    out = gen(fretless_bass(), 40, )
    assert out.candidates
    micro = generate_candidates(event=event(40, cents=50.0), profile=fretless_bass())
    assert micro.candidates
    assert micro.candidates[0].position.physical.semitone_offset_from_nut % 1 != 0


def test_a_fretted_instrument_cannot_realize_a_microtone():
    """Ordinary unplayability, not an exception — MSME-002 ruling 1."""
    out = generate_candidates(event=event(64, cents=50.0), profile=guitar())
    assert out.candidates == ()
    assert {r.code for r in out.rejections} == {RejectionCode.PITCH_NOT_REALIZABLE}


# -------------------------------------------------------------------- string jump


def test_maximum_string_jump_is_inert_without_a_previous_position():
    out = gen(guitar(), 64, constraints=MappingConstraints(maximum_string_jump=0))
    assert len(out.candidates) > 1


def test_maximum_string_jump_limits_movement_from_a_previous_position():
    first = gen(guitar(), 64)
    anchor = next(c for c in first.candidates if c.position.string_id == "string-6").position
    limited = gen(
        guitar(), 64,
        constraints=MappingConstraints(maximum_string_jump=1),
        previous_position=anchor,
    )
    assert len(limited.candidates) < len(first.candidates)
    assert all(
        abs(int(c.position.string_id.split("-")[1]) - 6) <= 1 for c in limited.candidates
    )


# ---------------------------------------------------------------------- integrity


def test_a_course_with_mismatched_open_pitches_is_reported_invalid():
    strings = (_string(1, 55, course="c"), _string(2, 57, course="c"))
    profile = InstrumentProfile(
        schema_version="1.0", instrument_id="x", display_name="x", family="x",
        fingerboard_mode=FingerboardMode.FRETTED, strings=strings,
        scale_length_mm=350.0, fret_count=20,
    )
    out = generate_candidates(event=event(60), profile=profile)
    assert out.candidates == ()
    assert {r.code for r in out.rejections} == {RejectionCode.PROFILE_INVALID}


def test_generation_is_deterministic():
    runs = [gen(guitar(), 64).candidates for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_mandolin_gives_four_choices_not_eight():
    """The golden guarantee: eight wires must never become eight choices."""
    out = gen(mandolin(), 74)  # D5, playable on more than one course
    assert len(playable_units(mandolin())) == 4
    assert len(out.candidates) <= 4
    assert len({c.position.course_id for c in out.candidates}) == len(out.candidates)


def test_every_rejection_names_its_strings_and_reason():
    out = gen(guitar(), 30)
    for r in out.rejections:
        assert r.string_ids
        assert r.detail
        assert isinstance(r.code, RejectionCode)
