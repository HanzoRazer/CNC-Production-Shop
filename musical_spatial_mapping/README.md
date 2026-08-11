# Musical Spatial Mapping Engine (MSME)

**Dev Orders:** MSME-001 (contracts + geometry) · MSME-002 (mapping pipeline)
**Status:** the mapping pipeline is complete — generation, scoring, deterministic
selection, annotation, the `MusicalSpatialMapper` facade, result serialization, a
diagnostic CLI, and a protected set of behavioral vectors.

---

## Architectural Position

**The Musical Spatial Mapping Engine is not owned by any application.**

It is a reusable computational **Core Engine**. Applications consume it; applications
do not define it. Its single responsibility is a translation:

```
Musical event  +  Instrument spatial profile  +  Mapping preferences
        ↓
Valid playable positions  →  Selected position  +  Instrument-specific annotation
```

A MIDI pitch is not inherently a guitar fret, a violin position, a bass position, a
mandolin course, or a banjo location. It becomes one only after being interpreted
through an instrument profile. The engine is therefore **not** a "fretboard mapper";
its responsibility is broader — *map canonical musical events onto playable physical
spaces.*

### Layering

```
Core Engines        MSME · Sequencer Timeline · MIDI Event Engine · Phrase Optimizer
        ↓ (consumed by)
Adapters            Guitar · Violin · Banjo · Mandolin · Piano · …
        ↓ (consumed by)
Applications        Smart Guitar · Instant Practice · Lesson Author · Luthiers Toolbox
```

Geometry is *one implementation dependency* of MSME, not its owner. If this engine
ever lived inside an instrument-geometry library, the dependency arrow would point
backwards. The canonical direction is: **Musical Event → MSME → Geometry Adapter →
Renderer.**

### Constitutional rules

1. **Core engines may not depend on transport frameworks.** No FastAPI, no pydantic,
   no persistence, no configuration system inside the engine. Those belong at the
   *application boundary* (e.g. `FastAPI → pydantic → MSME dataclasses → results →
   pydantic → JSON`). The engine is executable mathematics and stays embeddable in
   firmware, a CLI, a desktop sequencer, or the cloud.
2. **Music is canonical; instrument representation is an adapter.**
3. **The engine determines where a note *can* be played and how a chosen location is
   described — never whether a note was played correctly, whether a fingering is
   pedagogically ideal, or how pixels are drawn.** Those belong to analysis,
   pedagogy, and presentation layers.

### Planned consumers

String Master Sequencer · Smart Guitar · Luthiers Toolbox · Practice Loader · a
future Lesson System. This list is why the engine must never become
application-specific.

---

## Coordinate model (never overload one integer)

Three distinct concepts, modelled as three value objects (`models.py`):

| Concept | Measured from | Example (capo 2, finger 3 above capo) |
|---|---|---|
| **SoundingPitch** | — | the note that sounds (e.g. G) |
| **PhysicalPosition** | the **nut** | physical fret **5**; distance/normalized from nut |
| **PlayingPosition** | the **effective open** string (post-capo) | fret **3** relative to the capo; `is_open=False` |

With no capo the physical and playing positions coincide. A capo is a *mapping-time
transformation*, never a mutation of the instrument profile. Fretted and fretless
positions share one `SpatialPosition` contract: a fretless location simply carries
`fret_number = None` while still carrying valid normalized and (when scale length is
known) physical positions. **Absence of a fret never implies absence of a position.**

---

## Geometry

Equal temperament (12-TET) is the first and only geometry model. For a
scale length `L` and a semitone offset `n` from the open string:

```
distance = L × (1 − 2^(−n / 12))       normalized = 1 − 2^(−n / 12)
```

The same formula gives both a physical fret location and a fretless pitch target;
fractional `n` is supported. `scale_length_mm` may be absent, in which case
normalized positions remain available and millimetre distances are `None`.

---

## The pipeline

```
MusicalEvent + InstrumentProfile + MappingConstraints + MappingPreferences
                    ( + optional previous_position )
        ↓  validate      fail closed on malformed input
        ↓  generate      every playable location (candidates.py)
        ↓  score         named cost components (scoring.py)
        ↓  select        deterministic winner (selection.py)
        ↓  annotate      instrument-aware labels (annotation.py)
                    MappingResult
```

Each stage is independently testable and none of them reaches past its own job.
Generation decides what *exists*; scoring decides only what each option *costs*;
selection decides which one is *returned*. A location that scores appallingly is
still a location, so no preference change can silently alter what the engine
believes is playable.

```python
from musical_spatial_mapping import MusicalSpatialMapper, MusicalEvent
from musical_spatial_mapping.fixtures import guitar_standard_6

result = MusicalSpatialMapper(profile=guitar_standard_6()).map(
    MusicalEvent(event_id="e1", midi_note=64, start_tick=0, duration_ticks=480)
)
result.status              # SelectionStatus.SELECTED
result.selected.position   # SpatialPosition
result.annotation.primary_label
```

### Result status

| Status | Meaning |
|---|---|
| `SELECTED` | one candidate had the unique lowest total score |
| `AMBIGUOUS` | two or more candidates tied on the exact lowest total |
| `UNPLAYABLE` | a valid event on a valid profile with nowhere to be played |

**Ambiguity is decided before tie-breaking and tie-breaking never undoes it.**
An `AMBIGUOUS` result still carries a `selected` candidate — the tie-break makes
the answer repeatable, not unique — and the tied set is recoverable from
`candidates` via `equal_best_of()`. There is no stored `equal_best` field,
because every candidate carries its score and a second copy of a derived fact
could drift from the scores it summarises.

**`UNPLAYABLE` is an outcome, never an exception.** `UnsupportedPitchError` is
reserved for input that cannot be interpreted at all. A caller mapping a melody
must not be forced into exception control flow over ordinary unreachable notes.

### Scoring

Every component is a **cost**, and the lowest total wins. Components are named
individually in `CandidateScore` and never collapsed into an opaque number, so a
later stage can say *why* one location outranked another.

One deliberate exception: `lower_position_bias` is described by MSME-001 as "an
intentionally signed bias", and `validate_mapping_preferences` requires only that
it be finite while the other five weights must be non-negative. A negative bias
therefore contributes a negative cost and **a total may fall below zero.** That
is the shipped contract, honoured rather than silently clamped.

Movement is measured with the *normalized* coordinate — never fret numbers,
which do not exist on a fretless instrument, and never millimetres, which would
make the same musical movement cost far more on a profile that happens to
declare its scale length than on one that does not.

### Why a candidate was rejected

`RejectionCode` keeps three families apart, because an `UNPLAYABLE` result has to
be able to say *which* kind of limit applied. Instrument feasibility and a
caller's own constraints must never share a reason merely because both eliminate
a candidate.

| Family | Codes |
|---|---|
| **Instrument feasibility** | `BELOW_OPEN_PITCH` · `ABOVE_POSITION_RANGE` · `STRING_DISABLED` · `PROFILE_INVALID` |
| **Caller constraints** | `POSITION_CONSTRAINT` · `STRING_EXCLUDED` · `STRING_JUMP_CONSTRAINT` · `OPEN_STRING_EXCLUDED` · `CAPO_CONFLICT` |
| **Discrete realizability** | `PITCH_NOT_REALIZABLE` |

The three string-related codes answer three different questions: was the string
unavailable *on the instrument*, did *my request* exclude it, or was it playable
but too far from where I was?

`OUTSIDE_PREFERRED_REGION` is declared by MSME-001 but **is never emitted**, and
should not be: the enum's own docstring records that a preferred-region mismatch
is a scoring *penalty* rather than a rejection. It remains in the vocabulary
because removing a published enum value would break consumers, not because
anything raises it.

### Courses

**A candidate is a distinct playable musical choice, not a distinct physical
component.** A mandolin has eight strings but four things a player can
independently finger, so generation groups strings into playable units before any
arithmetic runs. `course_id` is authoritative and course membership is never
inferred from two strings sharing an open pitch — strings can be tuned in unison
and still be fingered separately, and collapsing them would delete a real choice.

### Statelessness

`MusicalSpatialMapper` is a frozen dataclass. It holds configuration and no
evolving state, so it cannot cache a last result or accumulate a prior position
even by accident. `previous_position` is an explicit argument to every `map()`
call and is the only route by which movement and string-change costs, and the
hard `maximum_string_jump` limit, become active. Sequence mapping is a loop over
this method, feeding each selection forward.

### Serialization and the behavioral contract

`mapping_result_to_dict` / `_to_json` and their `_from_` counterparts round-trip
exactly, and the three coordinate concepts are emitted as three nested objects —
never flattened, so the capo distinction survives into the stored artifact.

`tests/golden/msme_v1_vectors.json` is the protected behavioral spec: 30 vectors
across all three shipped profiles and all three statuses. Inputs are declared in
`tests/musical_spatial_mapping/msme_vectors.py` and every expected output is
produced by running the engine, so the file records behaviour rather than
hand-written prose that could quietly disagree with the code. **Changing a vector
changes the spec** — a reviewed decision, never a way to make a failing
implementation pass.

### CLI

A diagnostic consumer of the engine, never part of its semantics. stdout is
machine-readable JSON only; prose goes to stderr; an unplayable pitch exits 0
because it is a valid outcome rather than a process failure.

```bash
python -m musical_spatial_mapping.cli \
    --profile profile.json --event '{"midi_note": 67}' --constraints '{"capo_fret": 2}'
```

---

## Still deferred

Known limitations, stated so the engine is not read as claiming more than it does:

- **`HYBRID` fingerboard mode has no region model.** `models.py` accepts the
  enum, but nothing describes where a hybrid neck stops being fretted, so hybrid
  profiles are treated as fretless — claiming a fret number would assert
  something the profile never said.
- **Sequence mapping.** The engine maps one event; callers thread
  `previous_position` themselves. Lookahead and backtracking across a phrase are
  not modelled.
- **12-TET only.** Alternate temperaments are a later geometry model.
- **Microtones on fretted instruments are rejected, not approximated.** A pitch
  falling between frets returns `PITCH_NOT_REALIZABLE`; the engine will not
  quietly round it to the nearest fret. Fretless profiles accept fractional
  offsets normally.
