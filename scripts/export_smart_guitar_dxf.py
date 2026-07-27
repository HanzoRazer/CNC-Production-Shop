#!/usr/bin/env python3
"""Export the Smart Guitar body outline and cavity layout as a conformant DXF.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Takes the body silhouette from a governed source outline, scales it to the
official CAD length, and places every cavity at its governed position. Produces
a properly structured DXF via ezdxf — real HEADER, TABLES, layer definitions,
declared units and computed extents.

    python scripts/export_smart_guitar_dxf.py [--source front_v5] [--version R2010]

Source outlines
---------------
All three carry the same curve at aspect 0.8599; they differ in fidelity.

    front_v5   60 pts, 3 voids   default, and the artifact the CAD derives from
    back_v5    79 pts, 4 voids   richer geometry, adds the treble-mid void
    trace      78 pts, 4 voids   the original hand trace

Whichever is chosen, it is normalised to BODY_LENGTH_MM and translated so the
body top edge sits at y = 0, so the emitted drawing is always 468.50 x 402.85 mm
spanning y 0 to -468.5, and cavity y is simply -y_from_top.

The sources do NOT agree on where x = 0 falls relative to the outline: front_v5
and back_v5 differ by about 8.5 mm. At most one has its centreline at x = 0,
which matters because the neck pocket, both pickups and the bridge are all
specified at x_center 0.

Drawing conventions
-------------------
    units        millimetres, declared via $INSUNITS and $MEASUREMENT
    origin       body TOP edge; x = 0 is the centreline
    +X           TREBLE  (ruled 2026-07-27, CONF-X-SIGN-CONVENTION)
    +Y           toward the neck

Faces are separated because this is a two-sided part: CAV_TOP is cut from the
front, CAV_BACK from the rear. Cutting a back cavity from the front mirrors it.

REF_V5 carries front_v5's own cavity rectangles with their datum bug corrected,
so the governed placement can be diffed against the earlier layout at a glance.
It is reference only — see CONF-TRACE-REGISTRATION.

WHAT THIS IS NOT
----------------
A verified outline. The silhouette is corroborated for proportion across three
artifacts but has never been measured against a physical blank. Cavity
rectangles are footprints without corner radii; take radii from the CAD
dimension sheet. Edge features are omitted because their stated x values fall
off the outline, so they must be positioned from the drawn curve at their own y
station. CAV_BACK_BATTERY carries the Teensy position because
CONF-BATTERY-PLACEMENT has never been decided.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units as ezunits

ROOT = Path(__file__).resolve().parent.parent
LTB = Path("C:/Users/thepr/Downloads/luthiers-toolbox")
REFS = LTB / "docs/archive/instrument_references/smart_guitar"
TRACE = (
    LTB / "services/api/app/instrument_geometry/body/traced_outlines"
    / "smart_guitar_back_v1.json"
)

SOURCES = {
    "front_v5": REFS / "smart_guitar_front_v5.dxf",
    "back_v5": REFS / "smart_guitar_back_v5.dxf",
    "trace": TRACE,
}
DEFAULT_SOURCE = "front_v5"
DEFAULT_OUT = ROOT / "exports" / "geometry" / "smart_guitar_body_v1.dxf"
DEFAULT_VERSION = "R2010"

# Governed body dimensions. Width is derived from the outline aspect and is
# asserted rather than imposed, so a source with a different aspect fails loudly.
BODY_LENGTH_MM = 468.5
BODY_WIDTH_MM = 402.85
BODY_THICKNESS_MM = 47.0
RIM_MIN_MM = 12.7

# The trace metadata records the bass side overhanging the treble by 7.62 trace
# units, which is 12.28 mm at the governed scale. back_v5 and the trace both
# reproduce it exactly; front_v5 does not, so its outline is horizontally
# displaced. Checked rather than assumed, because every centreline feature —
# neck pocket, both pickups, the bridge — is specified at x_center 0.
DOCUMENTED_BASS_OVERHANG_MM = 12.28
BASS_OVERHANG_TOLERANCE_MM = 1.0

# front_v5's outline is the trace scaled by this factor. Its generator applied
# the same factor to cavity positions that were already in millimetres, which
# is the datum bug REF_V5 corrects. See v5_datum_offset.
V5_TRACE_SCALE = 438.15 / 290.79

# Largest tolerable spread, in source units, across the calibration layers
# before the datum correction is refused as not fitting.
V5_DATUM_MAX_SPREAD = 5.0

# Trace void indices that are through-body ergonomic cutouts. V4, V6 and V7 are
# hardware references rather than geometry.
TRACE_THROUGH_BODY_VOIDS = (0, 1, 2, 4)

# front_v5 cavity layers whose implied datum agreed to +/-1.2 mm. NECK_POCKET
# and CONTROL_PLATE are excluded: they remain outliers after the offset is
# removed, so they cannot calibrate it.
V5_DATUM_LAYERS: dict[str, float] = {
    "ARDUINO_POCKET": 133.5,
    "PICKUP_NECK": 167.6,
    "ANTENNA_RECESS": 202.6,
    "REAR_ELECTRONICS": 275.7,
    "PICKUP_BRIDGE": 294.6,
    "BRIDGE_MOUNTING": 320.0,
}
V5_REF_LAYERS = tuple(V5_DATUM_LAYERS) + ("NECK_POCKET", "CONTROL_PLATE", "USB_PORT")

# name -> (aci colour, lineweight in 1/100 mm, description)
LAYERS: dict[str, tuple[int, int, str]] = {
    "BODY_OUTLINE": (7, 50, "Body perimeter, finished size"),
    "VOID_THROUGH_BODY": (1, 35, "Ergonomic voids, cut through the full thickness"),
    "CAV_TOP": (5, 25, "Cavities cut from the FRONT face"),
    "CAV_BACK": (3, 25, "Cavities cut from the REAR face"),
    "REF_V5": (9, 9, "front_v5 cavities, datum-corrected, reference only"),
    "REF_CENTERLINE": (8, 13, "Reference only, not geometry"),
    "NOTES": (8, 13, "Annotation"),
}

# (layer, label, centre x, y_from_top, width across X, height along Y)
CAVITIES = (
    ("CAV_BACK", "POD", 74.0, 387.0, 162.0, 64.0),
    ("CAV_BACK", "TEENSY", 36.8, 133.5, 70.0, 25.0),
    ("CAV_BACK", "BATTERY", 36.8, 133.5, 90.0, 55.0),
    ("CAV_BACK", "CONTROL", 25.0, 317.0, 100.0, 60.0),
    ("CAV_TOP", "NECK_POCKET", 0.0, 53.3, 76.2, 55.9),
    ("CAV_TOP", "PU_NECK", 0.0, 167.6, 92.0, 40.0),
    ("CAV_TOP", "PU_BRIDGE", 0.0, 294.6, 92.0, 40.0),
    ("CAV_TOP", "BRIDGE", 0.0, 320.0, 95.0, 42.0),
)

Point = tuple[float, float]
Profile = list[Point]


def _polylines(doc: Any, layer: str) -> list[Profile]:
    return [
        [(p[0], p[1]) for p in e.get_points()]
        for e in doc.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == layer
    ]


def _bbox(points: Profile) -> tuple[float, float, float, float]:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), max(xs), min(ys), max(ys)


def load_source(name: str) -> tuple[Profile, list[Profile], list[tuple[str, Profile]]]:
    """Return (outline, through-body voids, v5 reference cavities) in source units."""
    path = SOURCES[name]
    if name == "trace":
        data = json.loads(path.read_text(encoding="utf-8"))
        outline = [(x, y) for x, y in data["body_pts_mm"]]
        voids = [
            [(x, y) for x, y in data["voids_mm"][i]] for i in TRACE_THROUGH_BODY_VOIDS
        ]
        return outline, voids, []

    doc = ezdxf.readfile(path)
    outline = _polylines(doc, "BODY_OUTLINE")[0]
    voids = [
        profile
        for layer in sorted({e.dxf.layer for e in doc.modelspace()})
        if "VOID" in layer
        for profile in _polylines(doc, layer)
    ]
    refs = [
        (layer, profile)
        for layer in V5_REF_LAYERS
        for profile in _polylines(doc, layer)
    ]
    return outline, voids, refs


def v5_datum_offset(outline: Profile, refs: list[tuple[str, Profile]]) -> tuple[float, float]:
    """Recover the constant datum offset in front_v5's cavity plotting.

    Returns (offset, spread) in source units.

    front_v5's generator multiplied y_from_top by V5_TRACE_SCALE — the factor
    that maps trace units to v5 units — treating values already in millimetres
    as if they were trace units, and plotted from the drawing origin rather
    than the body top edge.

    That diagnosis is self-checking: under this scale the six calibration
    layers agree to a spread near 1 mm, whereas under the body scale they
    scatter by nearly 40. The spread is returned so the caller can refuse a
    correction that does not actually fit.
    """
    _, _, _, outline_top = _bbox(outline)
    implied = []
    for layer, profile in refs:
        if layer not in V5_DATUM_LAYERS:
            continue
        _, _, y0, y1 = _bbox(profile)
        implied.append((y0 + y1) / 2 + V5_DATUM_LAYERS[layer] * V5_TRACE_SCALE)
    if not implied:
        return 0.0, 0.0
    mean = sum(implied) / len(implied)
    spread = (sum((v - mean) ** 2 for v in implied) / len(implied)) ** 0.5
    return outline_top - mean, spread


def rect(cx: float, y_from_top: float, w: float, h: float, top_y: float) -> Profile:
    """A footprint centred on (cx, top_y - y_from_top)."""
    y = top_y - y_from_top
    return [
        (cx - w / 2, y - h / 2),
        (cx + w / 2, y - h / 2),
        (cx + w / 2, y + h / 2),
        (cx - w / 2, y + h / 2),
    ]


def build_document(version: str, source: str) -> tuple[Any, Profile, float, float]:
    outline_raw, voids_raw, refs_raw = load_source(source)
    _, _, y0, y1 = _bbox(outline_raw)
    scale = BODY_LENGTH_MM / (y1 - y0)

    offset, spread = v5_datum_offset(outline_raw, refs_raw) if refs_raw else (0.0, 0.0)
    if refs_raw and spread > V5_DATUM_MAX_SPREAD:
        offset = 0.0  # correction does not fit; leave the reference where it lies

    # Normalise so the body top edge sits at y = 0. Every cavity is specified as
    # y_from_top, so this makes cavity y simply -y_from_top, and it removes the
    # arbitrary vertical placement that differs between source files.
    def to_mm(points: Profile, dy: float = 0.0) -> Profile:
        return [(x * scale, (y + dy - y1) * scale) for x, y in points]

    outline = to_mm(outline_raw)
    voids = [to_mm(v) for v in voids_raw]
    refs = [(layer, to_mm(p, offset)) for layer, p in refs_raw]

    doc = ezdxf.new(version, setup=True)
    doc.units = ezunits.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2

    for name, (color, lineweight, description) in LAYERS.items():
        layer = doc.layers.add(name, color=color, linetype="CONTINUOUS")
        layer.dxf.lineweight = lineweight
        layer.description = description

    msp = doc.modelspace()
    top_y = _bbox(outline)[3]
    bottom_y = _bbox(outline)[2]

    msp.add_lwpolyline(outline, close=True, dxfattribs={"layer": "BODY_OUTLINE"})
    for void in voids:
        msp.add_lwpolyline(void, close=True, dxfattribs={"layer": "VOID_THROUGH_BODY"})
    for _, profile in refs:
        msp.add_lwpolyline(profile, close=True, dxfattribs={"layer": "REF_V5"})

    for layer, label, cx, y_from_top, w, h in CAVITIES:
        msp.add_lwpolyline(
            rect(cx, y_from_top, w, h, top_y), close=True, dxfattribs={"layer": layer}
        )
        msp.add_text(
            label, height=6.0, dxfattribs={"layer": "NOTES", "color": LAYERS[layer][0]}
        ).set_placement((cx, top_y - y_from_top))

    msp.add_line(
        (0, top_y + 20), (0, bottom_y - 20), dxfattribs={"layer": "REF_CENTERLINE"}
    )

    notes = [
        "SMART GUITAR BODY V1 - DRAFT, NOT A VERIFIED OUTLINE",
        f"outline source: {source}   blank {BODY_LENGTH_MM} x {BODY_WIDTH_MM} "
        f"x {BODY_THICKNESS_MM} mm",
        "origin: body TOP edge, x=0 centreline  +X TREBLE  +Y toward neck  mm",
        f"rim minimum {RIM_MIN_MM} mm - cavity placement must respect it",
        "CAV_TOP cut from FRONT face, CAV_BACK cut from REAR face",
        "footprints only - no corner radii, see the CAD dimension sheet",
        "edge features omitted - position them from the drawn curve",
        "BATTERY shown at the Teensy position - placement undecided",
        "cavity y equals -y_from_top; body spans y 0 to -468.5",
        "REF_V5 is the earlier layout, datum-corrected, for comparison only",
    ]
    for index, line in enumerate(notes):
        msp.add_text(line, height=5.0, dxfattribs={"layer": "NOTES"}).set_placement(
            (_bbox(outline)[0], bottom_y - 40 - index * 9.0)
        )

    doc.set_modelspace_vport(
        height=BODY_LENGTH_MM * 1.2, center=(0, -BODY_LENGTH_MM / 2)
    )
    return doc, outline, offset * scale, spread * scale


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Smart Guitar body DXF.")
    parser.add_argument("--source", default=DEFAULT_SOURCE, choices=sorted(SOURCES))
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    doc, outline, offset_mm, spread_mm = build_document(args.version, args.source)
    out = args.out if args.out.is_absolute() else (Path.cwd() / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)

    x0, x1, y0, y1 = _bbox(outline)
    width, length = x1 - x0, y1 - y0

    try:
        shown = out.relative_to(ROOT).as_posix()
    except ValueError:
        shown = out.as_posix()
    print(f"wrote {shown}  ({args.version}, mm)")
    print(f"  source  {args.source}  ({len(outline)} outline points)")
    print(f"  length  {length:.2f}   (top y {y1:.2f}, tail y {y0:.2f})")
    print(f"  width   {width:.2f}   (x {x0:.2f} .. {x1:.2f})")
    if offset_mm:
        print(f"  REF_V5 datum corrected by {offset_mm:+.1f} mm (fit spread {spread_mm:.2f})")
    elif spread_mm:
        print(f"  REF_V5 datum NOT corrected — spread {spread_mm:.2f} mm exceeds tolerance")

    if abs(length - BODY_LENGTH_MM) > 0.01:
        print(f"  FAIL length drifted from the governed {BODY_LENGTH_MM}")
        return 1
    overhang = abs(x0) - x1
    if abs(overhang - DOCUMENTED_BASS_OVERHANG_MM) > BASS_OVERHANG_TOLERANCE_MM:
        print(
            f"  WARNING bass overhang {overhang:.2f} mm, documented "
            f"{DOCUMENTED_BASS_OVERHANG_MM} — this outline is displaced "
            f"{overhang - DOCUMENTED_BASS_OVERHANG_MM:+.2f} mm in x, so x=0 is "
            f"not its centreline"
        )

    if abs(width - BODY_WIDTH_MM) > 0.05:
        print(
            f"  FAIL width {width:.2f} does not match the governed "
            f"{BODY_WIDTH_MM} — the source aspect differs from 0.8599"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
