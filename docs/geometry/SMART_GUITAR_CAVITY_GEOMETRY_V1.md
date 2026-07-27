# Smart Guitar Cavity Geometry V1

Internal engineering document for **SMART-GUITAR-CAVITY-GEOMETRY-1**.

## Purpose

Make Smart Guitar cavity dimensions **derived and reproducible** rather than
asserted, and record every conflict found across the source specifications
together with its ruling.

This Dev Order exists because the specs carried a cavity that could not hold
its own contents, and no amount of reading was going to catch it reliably:

```text
sg-spec            electronics_pod depth 30.48 mm, containing a
                   "stacked_vertical" assembly declared at 76.0 mm
luthiers-toolbox   rear_electronics_cavity 95 x 65 x 22 mm, with the
                   HiFiBerry DAC+ADC absent from its contents entirely
```

A number that is asserted in two repositories will drift. A number that is
recomputed from the parts it has to hold cannot.

## The contract

```text
component dimensions + clearances  ->  cavity dimensions  ->  fit verdict
```

Nothing downstream reads a stated cavity dimension. `stated_*` fields exist
only so the derivation can be compared against the sources, and the comparison
is reported as a delta. A stale note like `total_height_mm: 76.0` has no path
into any consumer.

It is a **prerequisite** to `SMART-GUITAR-BUDGET-MODEL-1`. Costing a cavity
that cannot close would launder a geometry error into a dollar figure.

## The ruling that made it fit

Stacking is geometrically impossible, and no blank thickness rescues it:

```text
6 mm standoff + Pi 5 at 18 mm + 10 mm standoff + HiFiBerry at 24 mm
= 58 mm of stack, before lid clearance
against a 44.45 mm body — and a 2 in blank at 50.8 mm still fails
```

Side by side, every board sits on the cavity floor, so depth is set by the
tallest single demand rather than the sum:

```text
Pi 5        6 + 18 + 3 = 27 mm
HiFiBerry   6 + 24 + 3 = 33 mm   <- governs
```

**Ruled side-by-side by the owner on 2026-07-26.** It requires a ribbon or
riser between the Pi 5 GPIO header and the HAT instead of direct stacking.

## Derived geometry

Body blank 44.45 mm. All dimensions in mm.

| Cavity | Layout | Derived L × W × D | Stated D | Floor left | Fits |
|---|---|---|---:|---:|:--:|
| `ELECTRONICS_POD` | side_by_side | 162.0 × 64.0 × 33.0 | 30.48 | 11.45 | yes |
| `TEENSY_IO_POCKET` | single | 70.0 × 25.0 × 11.5 | 20.0 | 32.95 | yes |
| `BATTERY_CHAMBER` | single | 90.0 × 55.0 × 21.0 | 30.48 | 23.45 | yes |

```text
required blank thickness   41.0 mm   (governed by ELECTRONICS_POD: 33.0 + 8.0)
stated blank thickness     44.45 mm
margin                      3.45 mm  -> SUFFICIENT
```

The specified body works, side by side, with 3.45 mm to spare.

## Findings

**1. sg-spec's pod is 2.52 mm too shallow for its own contents.** Stated depth
is 30.48 mm; the parts demand 33.0 mm even side by side. The stated figure was
never wrong by much — it was wrong in a way that only appears when you compute
it, which is the entire argument for this record.

**2. The pod must grow 67 mm longer than any spec allows for.** Side-by-side
placement needs 162 mm of length against luthiers-toolbox's 95 mm rear cavity.
sg-spec gives the pod no length or width at all. Depth was never the binding
constraint — plan area is, and that is where the machining time will go.

**3. The Teensy pocket reproduces exactly, which validates the method.** The
sources state a 70 × 25 mm pocket for a 61 × 18 mm board and a single 4.5 mm
margin — which does not reproduce the width. Back-derived anisotropic margins
of 4.5 mm on length and 3.5 mm on width give 70.0 × 25.0 exactly. A test locks
this, because an exact reproduction is the evidence that the derivation rules
match how the original dimensions were actually arrived at.

**4. The fan mounting decided whether the body worked at all, and it went the
right way.** Ruled 2026-07-26: the 40 mm fan vents outward through the cover
and consumes no cavity depth. Had it been mounted internally, required
thickness would be 51.0 mm and the specified 44.45 mm body would **fail by
6.55 mm**. The counterfactual is retained under test — the ruling confirmed the
model, so without it the cost of the alternative would be invisible and a later
edit flipping the mounting would pass silently.

**5. The derived pod footprint is a lower bound.** The canonical signal chain
requires an "active buffered Hi-Z 1 MOhm" splitter that has no dimensions
anywhere in any repository. It could not be included, so the real pod is
larger than 162 × 64 mm by however much that part needs.

## Reconciliation record

Fifteen conflicts found: seven ruled, eight open. Recorded in the register and
propagated verbatim into the derived record, with a test enforcing that they
match, so a reviewer reading only the derived file cannot see fewer conflicts
than exist.

### Ruled

| ID | Field | Ruling |
|---|---|---|
| `CONF-POD-LAYOUT` | pod layout | Side-by-side. Stacking is impossible at any guitar-plausible thickness; the `stacked_vertical` note and its 76.0 mm figure are stale and should be retired at source. |
| `CONF-PI5-HEIGHT` | Pi 5 height | 18.0 mm per sg-spec, which was ruled canonical. luthiers-toolbox says 17.0 mm. The 1 mm changes no verdict. |
| `CONF-BASE-MODEL` | body outline lineage | The 2026-01-29 Les Paul reference is stale. Outline from luthiers-toolbox, cavity dimensions from sg-spec. Cavity *positions* inherited from a Les Paul outline are therefore untrustworthy and excluded. |
| `CONF-BODY-WIDTH` | body width | Official CAD length is **468.5 mm**, superseding 444.5. With the traced topology that gives k = 1.611128 and a derived width of **402.85 mm**; the stated 368.3 mm is 34.55 mm short and treated as stale. The CAD declares no width (drawing on hold). **Independently corroborated**: the owner's separate calculation reaches the same 402.85 mm, so the figure does not rest on the traced aspect alone. |
| `CONF-LENGTH-DATUM` | cavity `y_from_top` | The extra **24.0 mm sits at the tail, below the bridge**, so every `y_from_top` is preserved: the datum is the neck end and the growth is entirely below the bridge line. The bridge is fixed by scale length regardless. The 438.15 mm in the neck block remains stale. This was the binding constraint on plan-level work and is now cleared. |
| `CONF-FAN-INTRUSION` | fan mounting | The fan **vents outward through the lid** and consumes no cavity depth, confirming the modelled configuration. No derived dimension changes, but the thickness verdict stops being provisional: the 3.45 mm margin is real. An internally mounted fan would have demanded 51.0 mm and failed the blank by 6.55 mm; that counterfactual is retained under test. Lid requires vents. |
| `CONF-FRET-COUNT` | fret count | 24. The 2026-07-21 sg-spec quarantine note asserting "canon: 22" is itself wrong. No effect on cavity geometry; recorded because it sits in a file presenting itself as a cleanup. |

### Open

| ID | Field | Why it is still open |
|---|---|---|
| `CONF-USB-INTERFACE-LOCATION` | Hi-Z USB interface | The signal chain names a Scarlett Solo 4th Gen in the audio path. At roughly 143 × 97 × 47 mm it cannot be onboard. Treated as external; if it must be internal, the named parts are impossible. |
| `CONF-HIZ-SPLITTER-DIMS` | buffered splitter | Required by both audio paths, dimensioned nowhere. Omitted rather than invented. |
| `CONF-BATTERY-PLACEMENT` | battery location | sg-spec sites it in a bass chamber; the body was ruled a solid blank with through-body ergonomic voids, which has no such chamber. Depth and footprint hold; position does not. |
| `CONF-NVME-PLACEMENT` | NVMe SSD | Sited "under Pi 5", where it would fit inside the 6 mm standoff gap and add nothing. Plausible, unestablished, so registered but not placed. |
| `CONF-PICKUP-TYPE` | pickup type | **Intra-file**, not cross-repo: luthiers-toolbox says dual humbucker in `hardware.pickups` and P90 in its own `signal_chain` marked `canonical: true` (lines 449–450). sg-spec contains no P90 reference at all. No effect on electronics cavities; decides route size and pickup cost. |
| `CONF-PICKUP-ROUTE-DIMS` | pickup route size | Both sources say humbucker and disagree on the route: sg-spec 82 × 38 × 19.05 (r4.0), luthiers-toolbox 92 × 40 × 19.0 (r3.0). Blocked on `CONF-PICKUP-TYPE`, since a P90 route is different again. |
| `CONF-TRACE-REGISTRATION` | trace void positions | The trace's V4 (0.5707 from the neck end) and V6 (0.2703) do not match the spec's control cavity (0.6766) or neck pocket (0.1138) — opposite directions, so no similarity transform fits. Its provenance is a hand-trace from an AI render, whose voids are drawn not dimensioned. **Scoped to void positions; does not impugn the silhouette aspect**, which is corroborated independently. The frame transform is deterministic but now unverifiable. Use the trace for the silhouette and through-body voids only. |
| `CONF-OPPOSED-FACE-WEB` | top routes vs back pod | On stated positions the bridge route (19 mm, top) overlaps the rear cavity in plan. 19 + 33 = 52 mm through a 44.45 mm blank is a 7.55 mm breach. The source's own `structural_analysis` only measured floor-to-front-face. Unresolvable here — needs plan-level checking. |

## Scope and limits

**The source scan was bounded and is not exhaustive.** It covered sg-spec,
luthiers-toolbox `instrument_geometry`, and tap_tone_pi hardware docs.
`string_master_v.4.0` was not fully searched. The absence of a conflict record
is not evidence that no conflict exists — which is the reason the geometry is
derived rather than transcribed.

**This record derives cavity size only.** It does not validate cavity
*position* against the body outline, so it cannot detect two cavities colliding
in plan or a cavity breaching the perimeter. Given `CONF-BASE-MODEL` retires
the Les Paul outline that sg-spec's positions were mapped against, plan-level
validation is genuinely needed and is out of scope here.
`CONF-OPPOSED-FACE-WEB` is a concrete instance of what that omission hides.

**Only the embedded-electronics cavities are modelled** — the pod, the Teensy
pocket, and the battery chamber. Pickups, pickup routes, the neck pocket, the
bridge, the control cavity, and the output jack are **not** here. Both pickup
disagreements are recorded as conflicts, but no pickup dimension is derived or
fit-checked, and a test asserts no pickup appears as a component or cavity so
silence cannot be mistaken for agreement.

**The required blank thickness is a lower bound in two directions.** It omits
the Hi-Z splitter, which has no dimensions anywhere; and it counts only
back-face depth plus floor, never a top-face route cutting toward the same
plane from the other side.

**`min_floor_mm` is 8.0 everywhere and is an engineering estimate**, not a
structural calculation. The pod sits in the lower bout near the control cavity
and battery routing. A real minimum should come from structural review under
string tension, and it directly moves the required blank thickness.

Nothing here is a vendor datasheet or a measured part. Everything is `draft`.

## What this record excludes

- Cost, price, margin (enforced by validator and test key scans)
- Machining time, toolpaths, operation sequencing
- Cavity positions and plan-level collision checking
- Neck, fretboard, pickup route, and bridge geometry
- Any edit to the source repositories — this record rules, it does not rewrite

## Reproducing

```bash
python scripts/validate_smart_guitar_geometry.py
pytest tests/geometry/test_smart_guitar_cavity_geometry.py
```

The validator recomputes every cavity from the register, checks that
`floor_remaining` equals thickness minus depth, that each delta equals stated
minus derived, that `required_thickness` is the governing cavity's depth plus
its floor minimum, and that the conflict list propagates verbatim. A cavity
that does not fit is a hard failure. An unresolved conflict is printed loudly
and does **not** fail, because unresolved conflicts are an output of this
record rather than a defect in it.

## Sequence

```text
SMART-GUITAR-CAVITY-GEOMETRY-1     <- this Dev Order, complete at draft
        v
SMART-GUITAR-BUDGET-MODEL-1        scenario cost model, two product tiers
        v
SMART-GUITAR-PROTOTYPE-COST-CAPTURE-1
        v
SMART-GUITAR-BATCH-ECONOMICS-1
        v
SMART-GUITAR-OVERHEAD-ALLOCATION-1
        v
SMART-GUITAR-CHANNEL-PRICING-1
        v
SMART-GUITAR-COMMERCIAL-BASELINE-1
```

`CONF-FAN-INTRUSION` is closed, so **this geometry is ready for the budget
model to consume**. Every remaining open conflict can be carried: none of them
changes whether the instrument is buildable from the specified blank.

The open items now split cleanly by who they block. `CONF-HIZ-SPLITTER-DIMS`
and `CONF-USB-INTERFACE-LOCATION` bound the pod footprint and the bill of
materials, so they matter to costing. `CONF-OPPOSED-FACE-WEB`,
`CONF-TRACE-REGISTRATION`, and `CONF-BATTERY-PLACEMENT` are plan-level and
belong to `SMART-GUITAR-PLAN-COLLISION-1`. `CONF-PICKUP-TYPE` and
`CONF-PICKUP-ROUTE-DIMS` block both.
