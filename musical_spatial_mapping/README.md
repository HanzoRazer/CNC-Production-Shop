# Musical Spatial Mapping Engine (MSME)

**Dev Order:** MSME-001 · **Status:** Phases 1–2 delivered (contracts + geometry primitives); Phases 3–7 pending an architecture review.

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

Equal temperament (12-TET) is the first and only geometry model in MSME-001. For a
scale length `L` and a semitone offset `n` from the open string:

```
distance = L × (1 − 2^(−n / 12))       normalized = 1 − 2^(−n / 12)
```

The same formula gives both a physical fret location and a fretless pitch target;
fractional `n` is supported. `scale_length_mm` may be absent, in which case
normalized positions remain available and millimetre distances are `None`.

---

## What exists as of Phases 1–2

`enums` · `errors` · `models` (all frozen dataclasses, incl. the three-concept
position) · `validation` (fail-closed) · `pitch` · `geometry` · profile
(de)serialization · three example profiles + JSON schema + fixtures. Tests under
`tests/musical_spatial_mapping/` (pytest); the behavioral-spec golden vectors land
in `tests/golden/` at Phase 6.

**Not yet built (Phases 3–7):** candidate generation, scoring, deterministic
selection, annotation, the `MusicalSpatialMapper` facade, result serialization, and
the CLI utilities. These are deliberately deferred pending the Phase 2 architecture
review of the contracts above.
