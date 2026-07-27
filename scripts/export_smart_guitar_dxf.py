#!/usr/bin/env python3
"""Export the Smart Guitar body outline and cavity layout as a conformant DXF.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Produces a properly structured DXF via ezdxf — real HEADER, TABLES, layer
definitions, declared units and computed extents — rather than a bare ENTITIES
stub. The output is intended to be opened in CAD and drawn over.

    python scripts/export_smart_guitar_dxf.py [--version R2010] [--out PATH]

Drawing conventions
-------------------
    units        millimetres, declared via $INSUNITS and $MEASUREMENT
    origin       body centre
    +X           TREBLE  (ruled 2026-07-27, CONF-X-SIGN-CONVENTION)
    +Y           toward the neck
    body top     y = +202.60      tail  y = -265.90

Faces are separated onto their own layers because this is a two-sided part:
CAV_TOP_* are cut from the front, CAV_BACK_* from the rear. Cutting a back
cavity from the front face mirrors it about the centreline.

WHAT THIS IS NOT
----------------
A verified outline. The silhouette is corroborated for proportion but has
never been measured against a physical blank. Cavity rectangles are footprints
at governed sizes, without corner radii — take radii from the CAD dimension
sheet. Edge features are omitted because their stated x values fall off the
outline, so they must be positioned from the drawn curve at their own y
station. CAV_BACK_BATTERY carries the Teensy position because
CONF-BATTERY-PLACEMENT has never been decided.

Output lands under exports/, which is gitignored: the DXF is regenerable from
this script plus the governed fixtures, so it is a build product rather than a
source artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units as ezunits

ROOT = Path(__file__).resolve().parent.parent
TRACE = Path(
    "C:/Users/thepr/Downloads/luthiers-toolbox/services/api/app"
    "/instrument_geometry/body/traced_outlines/smart_guitar_back_v1.json"
)
DEFAULT_OUT = ROOT / "exports" / "geometry" / "smart_guitar_body_v1.dxf"
DEFAULT_VERSION = "R2010"

# Governed scale: official CAD length 468.5 over the traced height 290.79.
SCALE = 1.611128

# Governed body dimensions, for the title block and a sanity assertion.
BODY_LENGTH_MM = 468.5
BODY_WIDTH_MM = 402.85
BODY_THICKNESS_MM = 47.0
RIM_MIN_MM = 12.7

# Through-body ergonomic voids. V4, V6 and V7 are hardware references in the
# trace rather than geometry, and are deliberately excluded.
THROUGH_BODY_VOIDS = (0, 1, 2, 4)

# name -> (aci colour, lineweight in 1/100 mm, description)
LAYERS: dict[str, tuple[int, int, str]] = {
    "BODY_OUTLINE": (7, 50, "Body perimeter, finished size"),
    "VOID_THROUGH_BODY": (1, 35, "Ergonomic voids, cut through the full thickness"),
    "CAV_TOP": (5, 25, "Cavities cut from the FRONT face"),
    "CAV_BACK": (3, 25, "Cavities cut from the REAR face"),
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


def scaled(points: list[list[float]]) -> list[Point]:
    return [(x * SCALE, y * SCALE) for x, y in points]


def rect(cx: float, y_from_top: float, w: float, h: float, top_y: float) -> list[Point]:
    """A footprint centred on (cx, top_y - y_from_top)."""
    y = top_y - y_from_top
    return [
        (cx - w / 2, y - h / 2),
        (cx + w / 2, y - h / 2),
        (cx + w / 2, y + h / 2),
        (cx - w / 2, y + h / 2),
    ]


def load_outline() -> tuple[list[Point], list[list[Point]]]:
    data = json.loads(TRACE.read_text(encoding="utf-8"))
    body = scaled(data["body_pts_mm"])
    voids = [scaled(data["voids_mm"][i]) for i in THROUGH_BODY_VOIDS]
    return body, voids


def build_document(version: str) -> Any:
    doc = ezdxf.new(version, setup=True)
    doc.units = ezunits.MM
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LUNITS"] = 2  # decimal

    for name, (color, lineweight, description) in LAYERS.items():
        layer = doc.layers.add(name, color=color, linetype="CONTINUOUS")
        layer.dxf.lineweight = lineweight
        layer.description = description

    msp = doc.modelspace()
    body, voids = load_outline()
    top_y = max(y for _, y in body)
    bottom_y = min(y for _, y in body)

    msp.add_lwpolyline(body, close=True, dxfattribs={"layer": "BODY_OUTLINE"})
    for void in voids:
        msp.add_lwpolyline(void, close=True, dxfattribs={"layer": "VOID_THROUGH_BODY"})

    for layer, label, cx, y_from_top, w, h in CAVITIES:
        msp.add_lwpolyline(
            rect(cx, y_from_top, w, h, top_y),
            close=True,
            dxfattribs={"layer": layer},
        )
        msp.add_text(
            label,
            height=6.0,
            dxfattribs={"layer": "NOTES", "color": LAYERS[layer][0]},
        ).set_placement((cx, top_y - y_from_top))

    msp.add_line(
        (0, top_y + 20), (0, bottom_y - 20), dxfattribs={"layer": "REF_CENTERLINE"}
    )

    notes = [
        "SMART GUITAR BODY V1 - DRAFT, NOT A VERIFIED OUTLINE",
        f"blank {BODY_LENGTH_MM} x {BODY_WIDTH_MM} x {BODY_THICKNESS_MM} mm",
        "origin body centre  +X TREBLE  +Y toward neck  units mm",
        f"rim minimum {RIM_MIN_MM} mm - cavity placement must respect it",
        "CAV_TOP cut from FRONT face, CAV_BACK cut from REAR face",
        "footprints only - no corner radii, see the CAD dimension sheet",
        "edge features omitted - position them from the drawn curve",
        "BATTERY shown at the Teensy position - placement undecided",
    ]
    for index, line in enumerate(notes):
        msp.add_text(line, height=5.0, dxfattribs={"layer": "NOTES"}).set_placement(
            (min(x for x, _ in body), bottom_y - 40 - index * 9.0)
        )

    doc.set_modelspace_vport(height=BODY_LENGTH_MM * 1.2, center=(0, 0))
    return doc, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION, help="DXF version")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output path")
    args = parser.parse_args()

    doc, body = build_document(args.version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(args.out)

    xs = [x for x, _ in body]
    ys = [y for _, y in body]
    width = max(xs) - min(xs)
    length = max(ys) - min(ys)

    print(f"wrote {args.out.relative_to(ROOT).as_posix()}  ({args.version}, mm)")
    print(f"  length {length:.2f}  (top y {max(ys):.2f}, tail y {min(ys):.2f})")
    print(f"  width  {width:.2f}  (x {min(xs):.2f} .. {max(xs):.2f})")
    print(f"  layers: {', '.join(LAYERS)}")

    if abs(length - BODY_LENGTH_MM) > 0.01 or abs(width - BODY_WIDTH_MM) > 0.01:
        print(
            f"  FAIL extents drifted from the governed "
            f"{BODY_LENGTH_MM} x {BODY_WIDTH_MM}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
