# SMART-GUITAR-PLAN-COLLISION-1 — Dev Order Scope

**Status:** proposed, not started
**Prerequisite:** `SMART-GUITAR-CAVITY-GEOMETRY-1` (complete, commit `4ef8cc3`)
**Blocks:** `SMART-GUITAR-BUDGET-MODEL-1` only if a collision proves the body
unbuildable as specified

## The question it answers

> Do the Smart Guitar cavities fit **inside the body outline**, clear of the
> ergonomic voids and of each other, without breaching the material between
> opposing faces?

`SMART-GUITAR-CAVITY-GEOMETRY-1` derives cavity **size** and checks depth
against the blank. It explicitly excludes **position**, so it cannot see two
cavities colliding in plan, a cavity crossing the structural spine, or a route
breaking through a void wall. `CONF-OPPOSED-FACE-WEB` is the concrete instance
that motivated this Dev Order: on the stated positions, the bridge pickup route
and the rear electronics cavity overlap in plan, and 19.0 mm of top-face route
plus the 33.0 mm derived pod is 52.0 mm through a 44.45 mm blank.

## Gate 1: outline scale — resolved in principle by the official CAD length

**Revised 2026-07-26.** The official CAD gives a body length of **468.5 mm**,
superseding the 444.5 mm in the spec. That converts an unsolvable
two-constraint problem into a single scale factor and one falsifiable
prediction.

Forcing both stated dimensions never worked, and the official length makes it
strictly worse:

```text
traced extent  250.04 x 290.79 mm   aspect 0.859865

                       width scale   length scale   anisotropy
spec length 444.5        1.4730         1.5286         3.78%
CAD  length 468.5        1.4730         1.6111         9.38%
```

Trusting the CAD length **and the traced topology** — which the trace's own
note says is correct, while disclaiming only its scale — removes the conflict
by construction:

```text
k = 468.5 / 290.79 = 1.611128          anisotropy 0.00%
derived width = 250.04 x k = 402.85 mm   (15.86 in)
stated  width =              368.30 mm   (14.50 in)
disagreement  =               34.55 mm   (9.38% of stated)
```

**The cross-check settles which figure is wrong.** Trusting the stated width
instead derives a body length of 428.32 mm — 40.18 mm short of the official
CAD. The width is the outlier, not the length.

Three things corroborate that:

- The spec's own `design_heritage.explorer.reference_body_mm` is **420 x 460 mm**.
  Derived 402.85 x 468.5 belongs to that family; stated 368.3 x 444.5 does not.
- Every disputed figure is an exact round inch — 368.3 = 14.50 in,
  444.5 = 17.50 in, 438.15 = 17.25 in — which reads as assumption. The CAD's
  468.5 mm = 18.44 in is not round, which reads as measured.
- 368.3 mm is a common generic body width and looks carried in rather than
  derived from this outline.

Recorded as `CONF-BODY-WIDTH`, ruled.

**Phase 1 therefore shrinks to a single measurement.** The derived 402.85 mm is
a *prediction*, not a fact. One caliper across the widest point of a physical
blank confirms or refutes the whole calibration. If it measures 402.85 ± a few
mm, the outline is calibrated at k = 1.611128 and phase 3 can report real
millimetres. If it measures 368.3, the traced topology is distorted after all
and the Dev Order reverts to topology-only.

## Gate 2: the length datum — new, and now the binding constraint

The body is **24.0 mm longer** than the datum every cavity position was
measured against, and a third length (438.15 mm, "corrected from 444.5") sits
in the same file.

```text
official CAD   468.5 mm
spec body      444.5 mm     every cavity y_from_top measured from this
spec neck block 438.15 mm   "corrected from 444.5"
```

Whether the stated positions survive depends entirely on **where the extra
24.0 mm sits**. The bridge at `y_from_top` 320.0 is fixed by scale length
(628.65 mm nut to saddle), not by body length:

| Cavity | `y_from_top` | % of 444.5 | % of 468.5 |
|---|---:|---:|---:|
| Neck pocket | 53.3 | 12.0% | 11.4% |
| Neck pickup | 167.6 | 37.7% | 35.8% |
| Rear cavity | 275.7 | 62.0% | 58.8% |
| Bridge pickup | 294.6 | 66.3% | 62.9% |
| Bridge | 320.0 | 72.0% | 68.3% |

Growth at the tail leaves every position valid. Growth at the neck end shifts
all of them by 24.0 mm. No source states which, and a 24 mm error is roughly
twice the 12.7 mm rim minimum, so it dominates every clearance result.

Recorded as `CONF-LENGTH-DATUM`, unresolved. **This is now the gating unknown
rather than outline scale.** It needs the official CAD's own datum, which is a
lookup rather than a research problem.

## Phases

### Phase 1 — Calibration and datum (gate)

Establish a trustworthy outline in real millimetres **and** a trustworthy
length datum, or establish that neither exists yet.

- Vendor a dated snapshot of `smart_guitar_back_v1.json` (78 points, 7 voids)
  the way the component register vendors spec values
- Recompute extents from the points rather than trusting the stated `extent_mm`
- Apply the governed uniform scale k = 468.5 / recomputed height
- **Verify the derived width against a physical blank** — one caliper
  measurement confirms or refutes the entire calibration
- **Resolve the length datum**: locate the extra 24.0 mm relative to the
  neck-end reference, from the official CAD
- Record both bases and their confidence

Phase 1 has three honest outcomes, and the Dev Order must be willing to stop at
any of them:

1. **Calibrated** — the blank measures ~402.85 mm and the CAD datum is known;
   proceed to phase 2 with real clearances
2. **Scale calibrated, datum unknown** — clearances valid in X, all Y-dependent
   results carrying a ±24.0 mm band, which exceeds the rim minimum and
   therefore blocks C1, C2, C5, and C6 in practice
3. **Topology only** — the blank does not measure 402.85 mm, so the traced
   topology is distorted; containment and overlap run on adjacency alone and no
   millimetre clearance is reported

### Phase 2 — Coordinate reconciliation

Three coordinate frames currently describe the same body:

| Frame | Origin | Axes | Used by |
|---|---|---|---|
| Traced outline | body centre | X+ treble, Y+ toward neck | outline and voids |
| Cavity positions | body top edge | `x_center` signed, `y_from_top` | luthiers-toolbox cavities |
| STEM grid | top-left | normalised 0–1, 24 × 32, Y down | sg-spec `grid_position` |

Pick one canonical frame, implement transforms from the other two, and prove
the round trip on known landmarks. Getting this wrong silently mirrors the
instrument, which would make every asymmetric result wrong in a way that still
looks plausible — the bass side extends 7.62 mm further than the treble, so a
mirrored body is not obviously mirrored.

### Phase 3 — Collision checks

| ID | Check | Source of the rule |
|---|---|---|
| C1 | Cavity ⊆ body outline, inset by `rim_min` | sg-spec `rim_min_in` 0.5 → 12.7 mm |
| C2 | Cavity ∩ through-body void = ∅, with clearance | voids V1, V2, V3, V5 |
| C3 | Same-face cavities do not overlap unless declared merged | derived |
| C4 | Opposed-face web: `thickness − top_depth − back_depth ≥ min_web` wherever plan footprints overlap | `CONF-OPPOSED-FACE-WEB` |
| C5 | No cavity crosses the centreline spine band | sg-spec `spine_width_min_in` 1.5 → 38.1 mm |
| C6 | Edge clearance from cavity to outline ≥ `rim_min` | sg-spec `body_constraints` |
| C7 | Fastener positions land in material, not in a void or cavity | cover-plate screws, 4-bolt neck plate |
| C8 | Wire channels connect their endpoints and stay in material | `rear_wiring_channel` paths |
| C9 | Back-face cavity depth ≤ `max_hollow_depth` | sg-spec 1.2 in → 30.48 mm |

C4 is the reason the Dev Order exists. C9 is worth noting now: the derived pod
is **33.0 mm**, against a stated maximum hollow depth of **30.48 mm** — so the
pod likely violates a constraint sg-spec sets for itself, independently of any
collision. That check may fail on day one.

### Phase 4 — Reporting

A governed collision report per cavity and per cavity pair, with the same
posture the geometry record established: **a proven violation is a hard
validator failure; an unresolvable input is an open conflict that reports
loudly and does not fail.**

## Inputs required

| Input | Source | Status |
|---|---|---|
| Body outline, 78 pts + 7 voids | luthiers-toolbox `traced_outlines/smart_guitar_back_v1.json` | exists, scale now derivable at k = 1.611128 |
| Official CAD body length 468.5 mm | owner, 2026-07-26 | **supersedes** the spec's 444.5 mm |
| Physical blank width, predicted 402.85 mm | — | **does not exist**, one measurement gates phase 1 |
| Official CAD length datum | — | **does not exist**, gates all Y positions |
| Cavity sizes | `fixtures/geometry/smart_guitar_cavity_geometry_v1.json` | exists, derived |
| Cavity positions | luthiers-toolbox `body_position_mm` per cavity | exists, frame unreconciled |
| Body constraints | sg-spec `body_constraints` | exists |
| `min_web` | — | **does not exist**, needs a ruling |
| Pickup route size | — | **blocked** on `CONF-PICKUP-TYPE` and `CONF-PICKUP-ROUTE-DIMS` |

The pickup dependency matters: C4 cannot produce a final answer for the bridge
route while the route is either 82 × 38 or 92 × 40 and possibly a P90 instead.
It can still produce a **bounded** answer by checking the worst case of both.

## Deliverables

```text
business/geometry/outline.py        polygon loading, extent recomputation, calibration
business/geometry/frames.py         coordinate transforms with round-trip proofs
business/geometry/collision.py      C1-C9 as pure functions
business/geometry/models.py         extended: outline, placement, collision records
schemas/geometry/smart_guitar_outline_snapshot_v1.schema.json
schemas/geometry/smart_guitar_placement_v1.schema.json
schemas/geometry/smart_guitar_collision_report_v1.schema.json
fixtures/geometry/smart_guitar_outline_snapshot_v1.json    dated vendored snapshot
fixtures/geometry/smart_guitar_placement_v1.json           positions + frame declaration
fixtures/geometry/smart_guitar_collision_report_v1.json    derived
scripts/validate_smart_guitar_collision.py
tests/geometry/test_smart_guitar_collision.py
docs/geometry/SMART_GUITAR_PLAN_COLLISION_V1.md
```

Roughly the size of `SMART-GUITAR-CAVITY-GEOMETRY-1` plus a dependency, with
phase 1 potentially ending the Dev Order early and legitimately.

## Out of scope

- Editing luthiers-toolbox or sg-spec — this rules, it does not rewrite
- Re-tracing or redesigning the outline
- Toolpath, machining time, tool reach, or fixture access
- 3D solid modelling; all checks are 2D plan plus a depth scalar per face
- Neck geometry, fret positions, bridge intonation
- Cost of any kind
- Deciding pickup type — consumed as a bounded input, not settled here

## Open decisions

| # | Decision | Why it changes the work |
|---|---|---|
| 1 | Where the extra 24.0 mm of body length sits, from the official CAD datum | Gates every Y-dependent check. A 24 mm ambiguity is ~2x the rim minimum, so C1/C2/C5/C6 cannot report until it is known |
| 2 | `min_web` value between opposing cavities | Directly decides whether C4 passes; needs structural judgement, not a default |
| 3 | Add `shapely>=2.0` to `pyproject.toml`, or hand-roll polygon predicates | shapely 2.1.2 is present in the environment but undeclared. Hand-rolling avoids a runtime dependency in a repo that currently has five, at the cost of writing and testing point-in-polygon, inset, and intersection ourselves |
| 4 | Canonical coordinate frame | Everything downstream reads it; changing it later invalidates every stored result |
| 5 | Does a C9 failure (pod 33.0 mm vs 30.48 mm max hollow) block, or become a ruled conflict | The pod already appears to violate sg-spec's own maximum hollow depth |
| 6 | Whether pickup checks run bounded (worst case of both routes) or wait for `CONF-PICKUP-TYPE` | Bounded gives an answer now; waiting gives a precise one later |

## Risks

**The derived width is a prediction, not a measurement.** 402.85 mm follows
from trusting the traced topology and the CAD length together. If a physical
blank measures 368.3 mm instead, the topology is distorted and the outline
reverts to topology-only, meaning no plan-level claim about this instrument is
currently supportable. One caliper reading decides it.

**A confident wrong answer is the main hazard.** Every check in phase 3 emits
millimetres, and millimetres read as fact. The uncertainty band from phase 1
must be carried into every reported clearance rather than dropped at the
boundary.

**Success may be bad news.** C4 and C9 both look likely to fail on current
inputs. This Dev Order may conclude that the Smart Guitar is not buildable as
specified without moving the pod, thinning it, or thickening the blank. That is
the point of running it before the budget model prices the current geometry.

## Definition of done

- Outline calibrated, or formally recorded as uncalibratable with the
  consequences stated
- Coordinate transforms proven by round-trip tests on known landmarks
- C1–C9 implemented as pure functions with a validator that recomputes them
- Every violation either resolved, or recorded as a governed conflict with a
  named ruling and its owner
- Reported clearances carry the calibration uncertainty band
- Existing gates stay green: ruff, `mypy business`, pytest, coverage ≥ 90%,
  and all four validators
