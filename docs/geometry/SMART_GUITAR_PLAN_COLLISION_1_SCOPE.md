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

## Gate: the outline is not calibrated, and cannot be used until it is

The traced outline carries its own warning:

```text
"Traced at reduced zoom. Shape topology is correct.
 Scale factor TBD against physical blank."
```

Its extents do not scale uniformly to the stated body dimensions:

```text
traced extent    250.04 x 290.79 mm
stated body      368.30 x 444.50 mm

width  scale     368.30 / 250.04 = 1.4730
length scale     444.50 / 290.79 = 1.5286     -> 3.78% apart
```

No single scale factor satisfies both axes. Either the trace is
aspect-distorted (it was hand-traced from an AI render), or the stated width
and length are not both true extents of this outline.

**The consequence is decisive.** A 3.78% ambiguity on the 368 mm axis is
±13.9 mm. The rim minimum this Dev Order is supposed to enforce is 12.7 mm.
The measurement error would exceed the clearance being measured, so every
containment and edge-clearance result would be noise wearing the costume of a
number. Calibration is therefore **phase 1 and a hard gate**: no collision
check runs, and no result is published, until the outline is calibrated or
explicitly declared topology-only.

This is also why the Dev Order cannot be quietly folded into the budget model.
An uncalibrated outline produces confident, wrong clearances.

## Phases

### Phase 1 — Outline calibration (gate)

Establish a trustworthy outline in real millimetres, or establish that one does
not yet exist.

- Vendor a dated snapshot of `smart_guitar_back_v1.json` (78 points, 7 voids)
  the way the component register vendors spec values
- Recompute extents from the points rather than trusting the stated `extent_mm`
- Derive per-axis scale factors against the stated body dimensions
- Report anisotropy; fail the gate if it exceeds a governed tolerance
- Record the calibration basis and its confidence

Phase 1 has three possible honest outcomes, and the Dev Order must be willing
to stop at any of them:

1. **Calibrated** — a measurement of the physical blank resolves the scale;
   proceed to phase 2 with real clearances
2. **Uniform-scale approximation** — anisotropy accepted as trace error, scale
   taken from one governed axis, and every downstream clearance carries the
   residual as an explicit uncertainty band
3. **Topology only** — the outline is trusted for *ordering and adjacency* but
   not for distance; phase 2 runs containment and overlap checks but reports no
   millimetre clearances at all

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
| Body outline, 78 pts + 7 voids | luthiers-toolbox `traced_outlines/smart_guitar_back_v1.json` | exists, **uncalibrated** |
| Cavity sizes | `fixtures/geometry/smart_guitar_cavity_geometry_v1.json` | exists, derived |
| Cavity positions | luthiers-toolbox `body_position_mm` per cavity | exists, frame unreconciled |
| Body constraints | sg-spec `body_constraints` | exists |
| `min_web` | — | **does not exist**, needs a ruling |
| Physical blank measurement | — | **does not exist**, gates phase 1 |
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
| 1 | Calibration basis: measure a physical blank, accept uniform-scale approximation, or run topology-only | Determines whether phase 3 reports millimetres or only adjacency, and whether the Dev Order can finish at all |
| 2 | `min_web` value between opposing cavities | Directly decides whether C4 passes; needs structural judgement, not a default |
| 3 | Add `shapely>=2.0` to `pyproject.toml`, or hand-roll polygon predicates | shapely 2.1.2 is present in the environment but undeclared. Hand-rolling avoids a runtime dependency in a repo that currently has five, at the cost of writing and testing point-in-polygon, inset, and intersection ourselves |
| 4 | Canonical coordinate frame | Everything downstream reads it; changing it later invalidates every stored result |
| 5 | Does a C9 failure (pod 33.0 mm vs 30.48 mm max hollow) block, or become a ruled conflict | The pod already appears to violate sg-spec's own maximum hollow depth |
| 6 | Whether pickup checks run bounded (worst case of both routes) or wait for `CONF-PICKUP-TYPE` | Bounded gives an answer now; waiting gives a precise one later |

## Risks

**The outline may not be salvageable.** It was hand-traced from an AI render at
reduced zoom with a 3.78% aspect inconsistency. If phase 1 concludes it cannot
be calibrated, the honest deliverable is a record saying so — which is worth
having, because it would mean no plan-level claim about this instrument is
currently supportable.

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
