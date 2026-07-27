# Smart Guitar — CAD Dimension Sheet

Generated from the governed geometry record, not transcribed by hand.

- Derived geometry: `fixtures/geometry/smart_guitar_cavity_geometry_v1.json`
- Component register: `fixtures/geometry/smart_guitar_component_register_v1.json`
- Positions: luthiers-toolbox `smart_guitar_v1.json` v1.1 (vendored 2026-07-26)

All dimensions **mm**. Origin for positions: **body top (neck end)** for `y`,
**centreline** for `x`, `x+` toward treble.

> **Read the three MUST-FIX items before drawing the electronics pod.**
> Two cavities collide and one port falls outside the body.

---

## 1. Body

| Dimension | Value | Basis |
|---|---:|---|
| Length | **468.5** | Official CAD, ruled 2026-07-26 |
| Width (max) | **402.85** | Derived at k = 1.611128 from traced aspect; independently corroborated |
| Thickness | **51.0** | ENLARGED from 44.45 to clear four spec-native web failures |
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
| `ELECTRONICS_POD` | **162.0** | **64.0** | **33.0** | 18.0 | yes |
| `TEENSY_IO_POCKET` | **70.0** | **25.0** | **11.5** | 39.5 | yes |
| `BATTERY_CHAMBER` | **90.0** | **55.0** | **21.0** | 30.0 | yes |

Required blank thickness **41.0** (governed by `ELECTRONICS_POD`), against 51.0 — margin **10.0**.

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

## 5. MUST-FIX before the drawing closes

### 5.1 The electronics pod collides with the bridge pickup route

```text
web = 51.0 − 19.0 (bridge route, TOP) − 33.0 (pod, BACK) = -1.00 mm
required ≥ 8.0                                FAIL, short by 9.00
```

Negative web means the two cavities **physically intersect by 1.00 mm**.
The overlap occurs in every orientation tested, so it does not depend on how
the pod is turned. Neither thickness nor depth can absorb it: passing would
need a 60.0 blank, or a 24.0 pod when the HiFiBerry alone demands 30.

**The pod must move.** The bridge sits at y 320.0 and the body is now 468.5
long, leaving **148.5 of tail**. Laid 162 across X, the pod needs 64 in Y and
fits below the bridge with 84.5 spare before rim inset.

### 5.2 The pod exceeds the maximum hollow depth

Derived depth **33.0** against sg-spec's `max_hollow_depth` of **30.48** —
over by 2.52. Moving it does not help.

Note the constraint was set against a 44.45 blank. Scaled to 51.0, it becomes
**34.97**, which 33.0 satisfies. Restate the limit against the new
thickness rather than assuming it still binds.

### 5.3 The USB-C port sits outside the body

`usb_c_port` is placed at x **216.0**, but the body half-width is **201.43**
— the port is **14.57 outside the outline**. The spec's own note says
"Body half-width ~219 mm at this Y", implying a 438-wide body that matches
neither the stated 368.3 nor the derived 402.85.

Because it is an **edge feature**, its x should not be a fixed number at all:
it must be derived from the outline at y 239.4, and the body is narrower than
its maximum at that station.

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
