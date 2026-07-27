# Smart Guitar — CAD Dimension Sheet

Generated from the governed geometry record, not transcribed by hand.

- Derived geometry: `fixtures/geometry/smart_guitar_cavity_geometry_v1.json`
- Component register: `fixtures/geometry/smart_guitar_component_register_v1.json`
- Positions: luthiers-toolbox `smart_guitar_v1.json` v1.1 (vendored 2026-07-26)

All dimensions **mm**. Origin for positions: **body top (neck end)** for `y`,
**centreline** for `x`, `x+` toward treble.

> The electronics pod now has a **governed position** (section 3.1).
> Two edge features still carry positions that fall outside the outline.

---

## 1. Body

| Dimension | Value | Basis |
|---|---:|---|
| Length | **468.5** | Official CAD, ruled 2026-07-26 |
| Width (max) | **402.85** | Derived at k = 1.611128 from traced aspect; independently corroborated |
| Thickness | **47.0** | ENLARGED from 44.45 to clear four spec-native web failures |
| Half-width | 201.43 | |

Growth of +24.0 from the previous 444.5 sits **at the tail, below the bridge**,
so every `y_from_top` below is unchanged from the spec.

## 2. Structural constraints

| Constraint | Value | Source |
|---|---:|---|
| Rim minimum (cavity to outline) | 12.7 | sg-spec `rim_min_in` 0.5 |
| Spine width minimum (centreline) | 38.1 | sg-spec `spine_width_min_in` 1.5 |
| Top skin minimum | 7.62 | sg-spec `top_skin_min_in` 0.3 |
| Max hollow depth | 30.48 | sg-spec `max_hollow_depth_in` 1.2 |
| Floor minimum (cavity to opposite face) | 8.0 | ruled 2026-07-26 |
| Web minimum (between opposing cavities) | 8.0 | ruled 2026-07-26 |

## 3. Electronics cavities — DERIVED

These are computed from the parts they hold. They supersede any cavity size
in either source spec.

| Cavity | Length | Width | Depth | Floor left | Fits blank |
|---|---:|---:|---:|---:|:--:|
| `ELECTRONICS_POD` | **162.0** | **64.0** | **33.0** | 14.0 | yes |
| `TEENSY_IO_POCKET` | **70.0** | **25.0** | **11.5** | 35.5 | yes |
| `BATTERY_CHAMBER` | **90.0** | **55.0** | **21.0** | 26.0 | yes |

Required blank thickness **41.0** (governed by `ELECTRONICS_POD`), against 47.0 — margin **6.0**.

### Contents and internal clearances

| Cavity | Part | Part L×W×H | Mount | Standoff | Edge margins L/W | Lid clr |
|---|---|---|---|---:|---:|---:|
| `ELECTRONICS_POD` | Raspberry Pi 5 (8 GB) | 85.0 × 56.0 × 18.0 | floor | 6.0 | 4.0 / 4.0 | 3.0 |
| `ELECTRONICS_POD` | HiFiBerry DAC+ADC | 65.0 × 56.0 × 24.0 | floor | 6.0 | 4.0 / 4.0 | 3.0 |
| `ELECTRONICS_POD` | 40 mm cooling fan | 40.0 × 40.0 × 10.0 | lid | 0.0 | 2.0 / 2.0 | 0.0 |
| `TEENSY_IO_POCKET` | Teensy 4.1 | 61.0 × 18.0 × 3.0 | floor | 4.0 | 4.5 / 3.5 | 4.5 |
| `BATTERY_CHAMBER` | Battery pack + BMS (4x 18650) | 80.0 × 45.0 × 18.0 | floor | 0.0 | 5.0 / 5.0 | 3.0 |

Pod layout is **side-by-side**, Pi 5 and HiFiBerry both on the cavity floor,
**4.0 mm between them**. They do *not* stack — that needs a ribbon or riser to
the GPIO header. The 40 mm fan mounts on the lid and **vents outward**, so it
adds no cavity depth; the lid requires vents.

### 3.1 Electronics pod — governed position

Relocated to the tail below the bridge, 2026-07-27.

| | Value |
|---|---:|
| Centre x | **74.0** |
| Centre y from top | **387.0** |
| Extent x | −7.0 .. 155.0 |
| Extent y | 355.0 .. 419.0 |
| Orientation | 162 across X, 64 along Y |
| Floor remaining | 14.0 |

Clearances: **8.0** wall to `control_cavity` (ends y 347.0), **14.0** to
`bridge_route`, **40.4** to `bridge_pickup_route`, **36.8** spare to the tail
rim limit at y 455.8.

The pod clears every top-face route, so no opposed-face web check applies to
it — separation removes the constraint rather than satisfying it.

**Latitude is narrow.** Feasible centre x is only **61.9 .. 86.2**, a 24.3 mm
window, because the body narrows toward the tail: at y 419 the outline spans
x −31.8 .. 186.5, leaving 192.9 of usable width for a 162 pod. More than about
12 mm of X movement either way pushes it through the rim.

The 8.0 cavity-to-cavity wall is borrowed from the ruled floor and web
minimums by analogy; it has not itself been ruled.

## 4. Spec cavities — positions and sizes

Positions carried from the spec. Sizes here are the spec's own, *not* derived.

| Feature | x | y from top | L × W × D | Corner r |
|---|---:|---:|---|---:|
| `neck_pocket` | 0.0 | 53.3 | 76.2 × 55.9 × 15.9 | 6.35 |
| `neck_pickup_route` | 0.0 | 167.6 | 92.0 × 40.0 × 19.0 | 3.0 |
| `bridge_pickup_route` | 0.0 | 294.6 | 92.0 × 40.0 × 19.0 | 3.0 |
| `bridge_route` | 0.0 | 320.0 | 95.0 × 42.0 × 12.0 | 3.175 |
| `control_cavity` | 25.0 | 317.0 | 100.0 × 60.0 × 20.0 | 6.35 |
| `control_plate_surface` | 25.0 | 317.0 | 100.0 × 50.0 | 6.35 |
| `teensy_io_pocket` | 36.8 | 133.5 | 70.0 × 25.0 × 20.0 | 3.0 |
| `rear_electronics_cavity` | 36.8 | 275.7 | 95.0 × 65.0 × 22.0 | 6.0 |
| `antenna_recess` | 22.2 | 202.6 | 50.0 × 30.0 | 3.0 |
| `output_jack` | 110.4 | 391.2 | 12.7 × 25.0 | 0 |
| `usb_c_port` | 216.0 | 239.4 | 12.0 × 6.5 × 7.0 | 1.5 |

**Neck pocket** also carries a 4-bolt pattern at ±22.0, ±28.0 from pocket centre,
#8-32 screws, 4.0 pilot, 9.5 counterbore 5.0 deep, neck angle 3.5°.

## 5. Still to fix before the drawing closes

### 5.1 Two edge features are positioned off the body

`usb_c_port` at x **216.0** against a half-width of **201.43** — **14.57 outside**.
`output_jack` at x **110.4**, where the outline edge at y 391.2 is x **182.2** —
71.8 short of the edge, which also drops it inside the relocated pod footprint.

Both are **edge features**, so neither x should be a fixed number: each must be
derived from the outline at its own y station. Placed at the edge, the jack
clears the pod by 20.9.

### 5.2 The pod exceeds the maximum hollow depth

Derived depth **33.0** against sg-spec's `max_hollow_depth` of **30.48** —
over by 2.52. Relocation does not help.

The constraint was set against a 44.45 blank; scaled to 47.0 it becomes
**32.23**, which 33.0 still exceeds by 0.77.
Restate the limit against the new thickness rather than assuming it still binds.

### 5.3 Which side is treble

The traced outline says **+X is treble**; the spec annotates a positive
`x_center` of 36.8 as *"bass side"*. They cannot both hold. The pod position
below is stated in the **trace** convention, so it sits treble. If the spec is
right instead, the pod centre is **x −74.0** and every asymmetric feature
mirrors with it. Settle this before cutting anything off-centre.

## 6. Open items that affect the drawing

| Item | Effect on CAD |
|---|---|
| `CONF-PICKUP-ROUTE-DIMS` | Route is 92 × 40 × 19.0 (r3.0) or 82 × 38 × 19.05 (r4.0). Pick one before cutting pickup pockets. |
| `CONF-PICKUP-TYPE` | Humbucker vs P90 — same file contradicts itself. Changes route size again. |
| `CONF-HIZ-SPLITTER-DIMS` | A required in-body part with no dimensions anywhere. **The 162 × 64 pod is a lower bound.** |
| `CONF-BATTERY-PLACEMENT` | Chamber size is derived; its position is not decided. |
| `CONF-USB-INTERFACE-LOCATION` | If the Hi-Z interface must be onboard, the named parts do not fit and the pod grows again. |
| `CONF-TRACE-REGISTRATION` | Cavity positions cannot be verified against the outline — the trace's own landmarks disagree with the spec. Treat positions as spec-authoritative, not outline-verified. |

## 7. Confidence

Everything here is **draft**. Length 468.5, thickness 44.45, and the derived
cavity sizes are the firmest. Width 402.85 is derived and corroborated but
never measured. Positions are the spec's and unverified against the outline.
