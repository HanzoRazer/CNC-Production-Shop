# SMART-GUITAR-GEOMETRY-AUTHORITY-CLEANUP-1

**Status:** work complete for the authorized scope; **submittal held**. Not a
pull request and deliberately not pushed — see *Why this is held* below. One
item referred back, see *Open: the ruled neck-pickup station*.

**Supersedes in part:** `SMART-GUITAR-NECK-PICKUP-GEOMETRY-1`, **stopped as
written** by owner ruling before any of it was executed.

## Why this exists

`SMART-GUITAR-NECK-PICKUP-GEOMETRY-1` asked for a neck-pocket / neck-pickup
interference to be measured and a pickup translation derived from it, with
`628.65 mm` scale and a `3.5°` neck angle frozen as governed and the bridge
station locked against movement.

Grounding it against the repository found the premises did not hold:

| Order asserted | Repository state |
|---|---|
| Scale `628.65` is governed and drives a frozen bridge station | Product record carries `647.7`, revised by owner 2026-09-05 (`e5112d2`). The difference is 19.05 mm and the bridge station is scale-derived. |
| A neck-pocket / neck-pickup interference exists | No source in reach shows one. The only located pocket sits 38–57 mm clear of the pickup under every reading. `SMART-GUITAR-PLAN-COLLISION-1`'s sweep lists six failing pairs; this is not among them. |
| Two neck-pocket sources disagree | Hardcoded prose in the exporter, citing neither. One source located, and it is withdrawn. |
| `3.5°` neck angle is ruled | Appears nowhere in this repository. |
| The CAD model is here and can be modified | No `.step`, `.f3d`, `.sldprt` or `.3dm` anywhere in the repository. |

## Owner rulings, 2026-09-07

1. **Scale.** Do not freeze `628.65`; it is superseded and historical. `647.7`
   is the latest repository value but is still subject to the active CAD
   sprint. Final is whatever the CAD model returns and is then governed. Do not
   move the bridge from either figure until the sprint returns its current
   nut / scale / bridge geometry.
2. **Interference.** Do not derive it from repository cavity coordinates. It
   was observed in the active CAD design, which is the authority. Absent a
   current model or measured export, record
   `INTERFERENCE_MEASUREMENT = NOT YET WITNESSED` and do not calculate a
   translation.
3. **CAD boundary.** This repository is not the CAD-authoring venue. The sprint
   creates geometry, places features and measures interference; this repository
   receives measured dimensions, proposed governed values, provenance, and the
   validation and cost consequences.
4. **Neck angle.** `3.5°` may be an active CAD assumption. It is not governed
   merely because a sheet printed it.
5. **Cavity positions.** Remain withdrawn — neck pocket, neck pickup, bridge
   pickup, electronics cavity. Old fixtures containing coordinates do not
   un-withdraw them. Only the CAD sprint returns new proposed positions.
6. **`sg-spec` authority.** Not an authority for neck-pocket geometry. Any
   found there is unreliable; identify its origin and remove stray or stale
   data, and remove generated prose implying it is authoritative.

The order's acceptance criterion *"Scale remains exactly 628.65 mm"* is
withdrawn, as is its claim that the bridge station is already frozen from it.

## What the search actually found

**Neck pocket — the claim was not merely unsupported, it was contradicted.**

The pocket appears with dimensions in exactly two documents, both in
`luthiers-toolbox`, and they agree to the decimal:

```text
services/.../specs/smart_guitar_v1.json     76.2 x 55.9 x 15.9  r6.35  x=0  y=53.3
docs/archive/.../SMART_GUITAR_V1_CNC_HANDOFF.md
                                            76.2 x 55.9 x 15.9         x=0  y=53.3
```

The handoff derives from the spec and says so, so that is one source and a
document about it. Both are withdrawn with every other cavity position.
`sg-spec` and `tap_tone_pi` carry no neck-pocket geometry at all; the other
neck-pocket hits in `luthiers-toolbox` are **other instruments** — Explorer
1958, Les Paul 1959, a 24-fret Stratocaster.

**Where the claim came from.** It was born as a hardcoded string literal in
`4cb42a3` (2026-07-28, "rebuild the CAD dimension sheet around confidence"). The
diff adds it with no corresponding removal, and the previous version of the
sheet did not mention the neck pocket at all — so it replaced nothing and decayed
from nothing. That commit's message is otherwise thorough, and says nothing about
the neck pocket. It entered a *Not established* table in which every neighbouring
row was real.

**No document in this repository has ever named `sg-spec` in connection with the
neck pocket.** The claim named neither source. `sg-spec` was searched because
this project's own notes record it as canonical for cavity dimensions — checked,
not accused. That distinction was stated wrongly in the first draft of
`SG_SPEC_NECK_POCKET_QUERY_1.md` and corrected before dispatch.

**`sg-spec`.** Carries no neck-pocket or pickup geometry at all. The only match
across the whole repository is the prose fragment
`"Clear of neck pocket projection"` in `smart_guitar_cavity_map.json`, which is
a constraint note, not geometry. **Nothing to remove under ruling 6**, and
`sg-spec` is outside this session's working directories in any case.

That negative was produced from outside `sg-spec`, which is weaker than one
produced from inside it, so it has been put to that repository's maintainer as
`SG_SPEC_NECK_POCKET_QUERY_1.md` before being treated as settled. The query
also raises the constraint itself: `bass_chamber` requires clearance from a
"neck pocket projection" while its two sibling constraints resolve to numbers
in the same file, which is a plausible origin of the belief that `sg-spec` knew
where the neck pocket was.

**The clearance that is not a collision.** From the one locatable pocket and
the pickup route, at both candidate envelopes:

```text
 92x40 route | y_from_top = CENTRE      pocket ends  91.40  pickup starts 147.60  gap +56.20 mm
 92x40 route | y_from_top = NEAR EDGE   pocket ends 129.50  pickup starts 167.60  gap +38.10 mm
 82x38 route | y_from_top = CENTRE      pocket ends  91.40  pickup starts 148.60  gap +57.20 mm
```

Per ruling 2 this is evidence of **staleness**, not proof that the collision
observed in CAD is imaginary.

## Changes made

`scripts/export_cad_dimensions.py`, and the sheet regenerated from it:

- The neck-pocket rows no longer claim two disagreeing sources. They state that
  no traceable governing source exists, name what was searched, and attribute
  size and position to the CAD sprint.
- Section 1 gains **Who owns which figure** — an explicit split between what
  the active CAD sprint owns and what this repository owns, and a statement
  that the scale figure is the latest repository value rather than a final one,
  from which the bridge must not be placed.
- Section 4 gains a **neck angle** row: an active-CAD assumption, no value
  returned, none asserted here.

No dimension was added, changed, or removed. Nothing deleted was replaced with
an invented figure.

## Open: the ruled neck-pickup station

**This needs an owner decision and was not touched.**

`scripts/export_smart_guitar_dxf.py` (merged 2026-09-06 as PR #17, `f086ff0`)
carries:

```text
("CAV_TOP", "PU_NECK", 0.0, 207.125, 92.0, 40.0),
```

described in the same file as *"the RULED station … fret 24 at 485.775 plus a
ruled 10.0 setback plus half the 40.0 route. It resolves the fret-24 /
neck-pickup collision at the 25.5 in scale."*

Three things follow:

- **There is a documented collision, and it is not the one the stopped order
  described.** It is *fret 24 versus the neck pickup*, not neck pocket versus
  neck pickup. There is in-house precedent:
  `luthiers-toolbox/docs/archive/.../24_FRET_STRATOCASTER_DESIGN_HANDOFF.md`
  reaches the same conclusion independently at the same 25.5 in scale — going to
  24 frets relocates the **neck pickup**, while "the nut, bridge, and neck pocket
  heel position remain identical". The pocket was never party to it. The pickup was moved from `167.6` to `207.125` — a bridgeward
  translation of **39.525 mm** — which is the same shape of work the stopped
  order specified, already done, under a different premise and using a 10.0 mm
  setback rather than the 8.0 mm structural web.
- **Its provenance is not recorded.** The "ruled 10.0 setback" appears in this
  repository only inside that comment. No fixture, record or ruling document
  carries it, which is the same defect this cleanup removed from the neck-pocket
  claim.
- **It sits against ruling 5.** A neck-pickup position was un-withdrawn and
  ruled, one day before ruling 5 restated that neck-pickup position remains
  withdrawn and only the CAD sprint may return it.

Deleting an owner-merged station would be overreach; leaving it unremarked
would let an unsourced figure keep the authority this cleanup exists to take
away. It is therefore recorded here and referred back.

## Why this is held

Held by owner ruling, 2026-09-07. The work sits on local branch
`sg-authority-cleanup`, cut from `9159055`. It is a preserved checkpoint, not
a submission.

The next CAD release is expected to return the resolved neck / fret-24 /
pickup geometry and will very likely redefine the neck-pickup station. Pushing
this now would put two different "current truths" into the repository within
days of each other: a repository-side authority correction that is right in
principle, and a CAD release that supersedes the geometry it comments on.

What survives that release, because it is an authority finding rather than a
geometry one:

- the "two neck-pocket sources disagree" claim was unsupported prose;
- repository geometry does not outrank the active CAD sprint during the
  prototype phase.

What is deliberately left unadjudicated until the release lands, and must not
be resolved by arithmetic here:

```text
PU_NECK = 207.125                provisional, awaiting CAD confirmation
10.0 mm setback                  provisional, awaiting CAD confirmation
fret-24 / pickup clearance       not yet witnessed
final neck-pickup station        CAD sprint returns it
```

Sequence:

```text
next CAD release becomes the geometry witness
  -> ingest the resolved neck / fret-24 / pickup geometry
  -> reconcile 207.125 and the 10.0 setback against it
  -> update this cleanup if the release changes what is true
  -> submit one authority-consistent pull request
```

## Where this leaves the sequence

```text
ACTIVE CAD SPRINT
    ↓  geometry evolves; scale, neck angle, pocket, pickup, bridge measured
    ↓  returned as proposed dimensions with CAD provenance
CNC-Production-Shop
    ↓  reconcile governed records
    ↓  regenerate the CAD dimension sheet
    ↓  costing and manufacturing validation
```

`INTERFERENCE_MEASUREMENT = NOT YET WITNESSED`. No pickup translation is
calculated in this repository until the sprint returns a measurement.
