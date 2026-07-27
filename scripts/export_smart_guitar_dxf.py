#!/usr/bin/env python3
"""Export the Smart Guitar body outline and cavity layout as DXF.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Scales the traced silhouette by the governed factor and places every cavity at
its governed position, so a CAD drawing can start from a curve rather than from
a table of numbers to retype.

    python scripts/export_smart_guitar_dxf.py

Output is written under exports/, which is gitignored: the DXF is regenerable
from this script plus the governed fixtures, so it is a build product rather
than a source artifact.

WHAT THIS IS NOT: a verified outline. The silhouette is corroborated for
proportion but has never been measured against a physical blank, and
CONF-X-SIGN-CONVENTION is unresolved, so the treble side is assumed. Cavity
rectangles are footprints at governed sizes, without corner radii. Edge
features are omitted because their stated x values fall off the outline.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE = Path(
    "C:/Users/thepr/Downloads/luthiers-toolbox/services/api/app"
    "/instrument_geometry/body/traced_outlines/smart_guitar_back_v1.json"
)
OUT = ROOT / "exports" / "geometry" / "smart_guitar_body_v1.dxf"

# Governed scale: official CAD length 468.5 over the traced height 290.79.
SCALE = 1.611128

# Through-body ergonomic voids. V4, V6 and V7 are hardware references in the
# trace rather than geometry, and are deliberately excluded.
THROUGH_BODY_VOIDS = (0, 1, 2, 4)

# (layer, centre x, y_from_top, width across X, height along Y)
CAVITIES = (
    ("CAV_BACK_POD", 74.0, 387.0, 162.0, 64.0),
    ("CAV_BACK_TEENSY", 36.8, 133.5, 70.0, 25.0),
    ("CAV_BACK_BATTERY", 36.8, 133.5, 90.0, 55.0),
    ("CAV_BACK_CONTROL", 25.0, 317.0, 100.0, 60.0),
    ("CAV_TOP_NECKPOCKET", 0.0, 53.3, 76.2, 55.9),
    ("CAV_TOP_PU_NECK", 0.0, 167.6, 92.0, 40.0),
    ("CAV_TOP_PU_BRIDGE", 0.0, 294.6, 92.0, 40.0),
    ("CAV_TOP_BRIDGE", 0.0, 320.0, 95.0, 42.0),
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


def build_entities() -> list[tuple[str, list[Point]]]:
    data = json.loads(TRACE.read_text(encoding="utf-8"))
    body = scaled(data["body_pts_mm"])
    top_y = max(y for _, y in body)

    entities: list[tuple[str, list[Point]]] = [("BODY_OUTLINE", body)]
    for index in THROUGH_BODY_VOIDS:
        entities.append(("VOID_THROUGH_BODY", scaled(data["voids_mm"][index])))
    for layer, cx, y_from_top, w, h in CAVITIES:
        entities.append((layer, rect(cx, y_from_top, w, h, top_y)))
    return entities


def to_dxf(entities: list[tuple[str, list[Point]]]) -> str:
    out = ["0", "SECTION", "2", "ENTITIES"]
    for layer, points in entities:
        out += ["0", "LWPOLYLINE", "8", layer, "90", str(len(points)), "70", "1", "43", "0"]
        for x, y in points:
            out += ["10", f"{x:.4f}", "20", f"{y:.4f}"]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


def main() -> int:
    entities = build_entities()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(to_dxf(entities), encoding="utf-8")

    body = entities[0][1]
    xs = [x for x, _ in body]
    ys = [y for _, y in body]
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    print("  frame: origin body centre, X+ treble, Y+ toward neck, mm")
    print(f"  length {max(ys) - min(ys):.2f}  (top y {max(ys):.2f}, tail y {min(ys):.2f})")
    print(f"  width  {max(xs) - min(xs):.2f}  (x {min(xs):.2f} .. {max(xs):.2f})")
    print(f"  {len(entities)} polylines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
