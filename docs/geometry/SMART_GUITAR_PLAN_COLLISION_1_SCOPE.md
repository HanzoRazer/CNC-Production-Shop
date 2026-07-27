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

**Gate 1 is cleared.** The official CAD declares no width — the drawing is on
hold and will produce a comparable width according to shape — and an
independent calculation by the owner arrives at the same 402.85 mm. Two
derivations from different starting points agreeing is what promotes the figure
from provisional to governed. The outline is calibrated at k = 1.611128 and
phase 3 can report real millimetres.

Recorded as `CONF-BODY-WIDTH`, ruled and corroborated.

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

**Gate 2 is cleared.** The extra 24.0 mm is at the **tail, below the bridge**.
Every `y_from_top` is therefore preserved unchanged: the datum is the neck end,
the growth is entirely below the bridge line, and the bridge itself is fixed by
scale length regardless. The 438.15 mm figure in the neck block remains stale.

Recorded as `CONF-LENGTH-DATUM`, ruled.

## Residual risk: the outline cannot be registration-checked

Both gates are cleared, but one verification is unavailable. The trace's
labelled cavity landmarks do not sit where the spec's cavities sit:

| Landmark | Trace, frac from neck end | Spec /444.5 | Spec /468.5 |
|---|---:|---:|---:|
| V4 `control_cavity` | 0.5707 | 0.7132 | 0.6766 |
| V6 `neck_bolt_plate` | 0.2703 | 0.1199 | 0.1138 |

V4 sits higher than expected and V6 lower — opposite directions, so no scale or
offset reconciles them, and V4's X sign disagrees too. The trace's provenance
explains it: *"hand-traced from AI render back view"*, and a render's voids are
drawn rather than dimensioned.

**This does not affect the width.** Void placement and silhouette proportion are
separable claims, and the width is corroborated independently.

**What it does affect** is verification. The outline-to-spec transform is
deterministic once body length is known and needs no landmarks — but V4 and V6
were the only landmarks available to *check* it, so the alignment stays
unverified.

Mitigation, and a standing rule for phase 2: use the trace for the body
silhouette and the through-body voids V1, V2, V3, V5 **only**, and take every
cavity position from the spec. Never read a cavity position out of the trace.

Recorded as `CONF-TRACE-REGISTRATION`, unresolved — residual risk, not a
blocker.

## Phases

### Phase 1 — Calibration and datum (gate)

Establish a trustworthy outline in real millimetres **and** a trustworthy
length datum, or establish that neither exists yet.

- Vendor a dated snapshot of `smart_guitar_back_v1.json` (78 points, 7 voids)
  the way the component register vendors spec values
- Recompute extents from the points rather than trusting the stated `extent_mm`
- Apply the governed uniform scale k = 468.5 / recomputed height = 1.611128
- Assert the derived width against the governed 402.85 mm
- Apply the ruled datum: growth at the tail, `y_from_top` preserved
- Record both bases, their confidence, and the unverified-registration caveat

Both calibration gates are ruled, so phase 1 is now a short implementation step
rather than an open question. It should still **fail loudly** if the recomputed
extents drift from 250.04 × 290.79, since that would mean the vendored snapshot
no longer matches the outline these rulings were made against.

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
| C4 | Opposed-face web: `thickness − top_depth − back_depth ≥ min_web`, `min_web` = **8.0 mm** (ruled), wherever plan footprints overlap | `CONF-OPPOSED-FACE-WEB` |
| C5 | No cavity crosses the centreline spine band | sg-spec `spine_width_min_in` 1.5 → 38.1 mm |
| C6 | Edge clearance from cavity to outline ≥ `rim_min` | sg-spec `body_constraints` |
| C7 | Fastener positions land in material, not in a void or cavity | cover-plate screws, 4-bolt neck plate |
| C8 | Wire channels connect their endpoints and stay in material | `rear_wiring_channel` paths |
| C9 | Back-face cavity depth ≤ `max_hollow_depth` | sg-spec 1.2 in → 30.48 mm |

### C4 is already known to fail — the job is to fix it, not to find it

With `min_web` ruled at **8.0 mm** (2026-07-26, matching the floor minimum),
C4 can be evaluated now, and it fails at the bridge pickup:

```text
web = 44.45 − 19.0 (bridge route, top) − 33.0 (pod, back) = −7.55 mm
required ≥ 8.0                              FAIL, short by 15.55 mm
```

The web is **negative**, so the cavities physically intersect by 7.55 mm rather
than merely violating a margin.

**Robust to orientation.** The overlap occurs in all three placements tested at
the stated position, so the result does not depend on which cavity dimension
runs along which axis:

| Placement | Overlap with bridge route |
|---|---|
| Stated 95 × 65 cavity | 41.7 × 40.0 mm |
| Derived pod, 162 along Y | 41.2 × 40.0 mm |
| Derived pod, 162 across X | 90.2 × 33.1 mm |

**Neither dimension can absorb it.** Passing by thickness needs a 60.0 mm
blank; passing by depth needs a 17.5 mm pod when the HiFiBerry alone demands
30 mm. **Plan separation is the only viable fix**, which is precisely this Dev
Order's job.

**And there is room.** The bridge sits at `y_from_top` 320.0 on a body now
468.5 mm long, leaving 148.5 mm of tail. Laid 162 across X, the pod needs 64 mm
in Y — fitting below the bridge with 84.5 mm spare before rim inset. The 24 mm
tail extension ruled under `CONF-LENGTH-DATUM` is what creates that room.

So C4 changes character: it is no longer a check to run but a **constraint to
design against**, and the Dev Order's first deliverable is a pod placement that
satisfies it.

### Full sweep result: the spec was already non-manufacturable

Running C1, C3, C4, C5, and C9 across every cavity pair, with positions trusted
(`CONF-LENGTH-DATUM` ruled), width known, and `min_web` = 8.0:

**C4 — six of nine overlapping opposed-face pairs fail.** Four of them involve
**only spec-native cavities**, with no derived pod anywhere in the pair:

| Pair | Web | Short by | Derived pod involved? |
|---|---:|---:|:--:|
| `bridge_pickup_route` × pod | −7.55 | 15.55 | yes |
| `neck_pickup_route` × pod | −7.55 | 15.55 | yes |
| `neck_pickup_route` × `antenna_recess` | **1.45** | 6.55 | **no** |
| `bridge_pickup_route` × `rear_electronics_cavity` | 3.45 | 4.55 | **no** |
| `bridge_pickup_route` × `control_cavity` | 5.45 | 2.55 | **no** |
| `neck_pickup_route` × `teensy_io_pocket` | 5.45 | 2.55 | **no** |

This reframes the Dev Order. The enlarged pod did not break the design — **the
design was already unbuildable**, and the derivation merely made it visible. Any
fix that only relocates the pod leaves four violations untouched.

The worst spec-native case is the antenna recess: **1.45 mm** of wood between
the neck pickup route floor and the antenna pocket. The spec's own
`structural_analysis` records `floor_verdict: safe` on the strength of 20.45 mm
to the front face — but it only ever measured downward, never against a route
cutting up from the other side. The antenna's entire premise is a 2 mm RF
window; at 1.45 mm the window is the pickup cavity.

**C3 — a same-face overlap that is not intentional.** `control_cavity`
(25.0, 317.0, 100 × 60) and `rear_electronics_cavity` (36.8, 275.7, 95 × 65)
are both back-face and overlap by **50.7 × 56.2 mm**, yet the spec describes
them as separate cavities with separate cover plates. Either they are one
cavity or one is misplaced. The other same-face overlaps are benign: the
control plate is documented as spanning both pickup and controls, and the
antenna recess is a stepped shelf inside the rear cavity by design.

**C5 — every back-face cavity crosses the centreline spine band** of ±19.05 mm.
That constraint came from sg-spec's chambered Les Paul concept, which
`CONF-BASE-MODEL` retired. It probably does not apply to a solid body, but it
should be explicitly retired rather than silently ignored, since "carries string
tension load" is a real concern independent of chambering.

**C1/C6 — containment is inconclusive except for one definite failure.** The
check used a rectangle bound, which over-estimates the body, so a pass proves
nothing while a failure is definite. `usb_c_port` at x 216.0 fails against a
188.73 mm limit. Real containment needs the calibrated outline.

**C9 — only the pod fails**, at 33.0 against 30.48, over by 2.52.

### C9 may also fail on day one

The derived pod is **33.0 mm** against sg-spec's own `max_hollow_depth` of
**30.48 mm**, so the pod likely violates a constraint the spec sets for itself,
independently of any collision. Unlike C4 this one has no plan-level escape:
it needs either a relaxed constraint or a shallower assembly.

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
