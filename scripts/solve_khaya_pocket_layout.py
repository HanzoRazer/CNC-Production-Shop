#!/usr/bin/env python3
"""Search Khaya back-face pocket placements, maximising pickup separation.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

CONF-SINGLE-PICKUP-SPACE was ruled from a packing search that asked "does the
electronics set fit alongside a single Telecaster route" and answered yes. It
never asked how much room was left over, and the answer turned out to be
11.6 mm between POD_PI and the pickup — close enough that CONF-SINGLE-PICKUP-EMC
now blocks the configuration pending a measurement.

That earlier search was a throwaway. This is the same search kept, with the
objective changed from feasibility to clearance:

    maximise the plan gap between POD_PI and the pickup route,
    subject to the whole electronics set still packing.

    python scripts/solve_khaya_pocket_layout.py [--step 2.5]

Prints a frontier rather than a single answer, because the Pi is the aggressor
and the pickup is not its only victim: POD_HAT carries the analog front end,
and the ribbon ties it to the Pi. Pushing the Pi away can drag the front end
in. Both distances are reported so the trade is visible instead of implied.

The frame here puts x = 0 on the instrument centreline, where every centreline
feature is specified. front_v5's own outline is horizontally displaced, so the
centreline is recovered from the documented bass overhang rather than from the
file's origin. Separations in y are unaffected either way; x extents are not.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent.parent
DXF_EXPORT = ROOT / "scripts" / "export_smart_guitar_dxf.py"

# Back-face pockets to place, from the derived cavity geometry.
POCKETS: dict[str, tuple[float, float]] = {
    "POD_PI": (93.0, 64.0),
    "POD_HAT": (73.0, 64.5),
    "BATTERY_CHAMBER": (90.0, 55.0),
}
POCKET_DEPTH = {"POD_PI": 27.0, "POD_HAT": 33.0, "BATTERY_CHAMBER": 21.0}

# The single Telecaster-style bridge route, cut from the FRONT face.
PICKUP = {"width": 80.0, "height": 22.0, "x_center": 0.0, "y_from_top": 294.6, "depth": 19.0}

BODY_THICKNESS = 47.0
MIN_WEB = 8.0  # inter-pocket wall, and the floor minimum
RIM_MIN = 12.7
RIBBON_LENGTH = 100.0  # WIRE_CHANNEL_PI_HAT derived length

# y_from_top window the pockets may occupy, a coarse bound before the real
# keep-outs below do the work.
Y_MIN, Y_MAX = 100.0, 420.0

# front_v5 plots its cavity layers with BOTH of its scale errors applied: the
# generator multiplied millimetre values by the trace scale, and the drawing is
# then scaled again to body size. Undoing the product recovers positions that
# land on their nominal y_from_top to within about a millimetre, which is what
# makes these layers usable as keep-outs rather than decoration.
#
# Only the features that survive into the current design are taken. The rest
# are superseded and would over-constrain the search:
#   ARDUINO_POCKET     no Arduino in the component register
#   PICKUP_NECK        deleted by the single-pickup layout — this IS the freed space
#   ANTENNA_RECESS     superseded by the Pi's own radio
#   REAR_ELECTRONICS   superseded by POD_PI / POD_HAT
#   PICKUP_BRIDGE      modelled explicitly and to governed dimensions
#   USB_PORT           edge feature, not a pocket
KEEPOUT_LAYERS = ("NECK_POCKET", "BRIDGE_MOUNTING", "CONTROL_PLATE")


def load_export_module() -> Any:
    spec = importlib.util.spec_from_file_location("dxf_export", DXF_EXPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_body(
    source: str = "front_v5",
) -> tuple[Polygon, list[Polygon], list[tuple[str, Polygon]]]:
    """Return (outline, voids, keepouts) in mm, x = 0 on the instrument centreline."""
    m = load_export_module()
    outline_raw, voids_raw, refs_raw = m.load_source(source)
    xs = [p[0] for p in outline_raw]
    ys = [p[1] for p in outline_raw]
    scale = m.BODY_LENGTH_MM / (max(ys) - min(ys))
    top = max(ys)

    # Recover the centreline from the documented bass overhang instead of the
    # file origin: the bass side overhangs the treble by a known amount, which
    # fixes where x = 0 must fall for a body of the governed width.
    half = (m.BODY_WIDTH_MM + m.DOCUMENTED_BASS_OVERHANG_MM) / 2
    shift = -half - min(xs) * scale

    def to_mm(points: list[tuple[float, float]]) -> Polygon:
        return Polygon([(x * scale + shift, (y - top) * scale) for x, y in points])

    # Cavity layers carry both scale errors; the outline carries only one.
    k = m.V5_TRACE_SCALE * scale
    offset, _ = m.v5_datum_offset(outline_raw, refs_raw)

    def ref_to_mm(points: list[tuple[float, float]]) -> Polygon:
        return Polygon([(x * scale / k, (y + offset - top) * scale / k) for x, y in points])

    keepouts = [(layer, ref_to_mm(p)) for layer, p in refs_raw if layer in KEEPOUT_LAYERS]
    missing = set(KEEPOUT_LAYERS) - {layer for layer, _ in keepouts}
    assert not missing, f"keep-out layers absent from {source}: {sorted(missing)}"
    return to_mm(outline_raw), [to_mm(v) for v in voids_raw], keepouts


def rect(x_center: float, y_from_top: float, width: float, height: float) -> Polygon:
    y = -y_from_top
    return Polygon(
        [
            (x_center - width / 2, y - height / 2),
            (x_center + width / 2, y - height / 2),
            (x_center + width / 2, y + height / 2),
            (x_center - width / 2, y + height / 2),
        ]
    )


def opposed_face_web(pocket_id: str) -> float:
    """Stock left between a back pocket and the front-face pickup route."""
    return BODY_THICKNESS - PICKUP["depth"] - POCKET_DEPTH[pocket_id]


def _centres(a: Polygon, b: Polygon) -> float:
    """Distance between two footprint centres."""
    return ((a.centroid.x - b.centroid.x) ** 2 + (a.centroid.y - b.centroid.y) ** 2) ** 0.5


def _header_span(a: Polygon, b: Polygon) -> float:
    """Shortest header-to-header run between two pockets.

    The ribbon does not connect the nearest corners; it connects two 40-pin
    headers. On a Pi 5 that header runs along the long edge of the board, and
    the HAT's mates with it, so each header sits at its pocket's x centre on
    one of the two x-aligned edges. The run is the best of those four pairings.

    Edge-to-edge distance flatters a diagonal layout badly — it measures corner
    to corner while the ribbon has to travel centre to centre in x.
    """
    ax0, ay0, ax1, ay1 = a.bounds
    bx0, by0, bx1, by1 = b.bounds
    ax, bx = (ax0 + ax1) / 2, (bx0 + bx1) / 2
    return min(
        ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 for ay in (ay0, ay1) for by in (by0, by1)
    )


def solve(step: float, ribbon_metric: str = "header") -> dict[str, Any]:
    outline, voids, features = load_body()
    usable = outline.buffer(-RIM_MIN)
    keepout = [v.buffer(MIN_WEB) for v in voids]
    keepout += [p.buffer(MIN_WEB) for _, p in features]
    route = rect(PICKUP["x_center"], PICKUP["y_from_top"], PICKUP["width"], PICKUP["height"])

    # Where a back pocket overlaps the route in plan, the remaining web is
    # thinner than the minimum for every pocket we place, so plan overlap is
    # forbidden outright and the route carries the same MIN_WEB skirt a pocket
    # would. Asserted rather than assumed: if a shallower pocket ever made the
    # web legal, this search would silently over-constrain.
    assert all(opposed_face_web(p) < MIN_WEB for p in POCKETS), "web rule no longer binds"
    route_keepout = route.buffer(MIN_WEB)

    minx, miny, maxx, maxy = usable.bounds

    def sites(pocket_id: str) -> list[tuple[float, float, Polygon]]:
        w, h = POCKETS[pocket_id]
        found = []
        x = minx + w / 2
        while x <= maxx - w / 2:
            y = Y_MIN
            while y <= Y_MAX:
                if miny <= -y - h / 2 and -y + h / 2 <= maxy:
                    box = rect(x, y, w, h)
                    if (
                        usable.contains(box)
                        and not any(box.intersects(k) for k in keepout)
                        and not box.intersects(route_keepout)
                    ):
                        found.append((x, y, box))
                y += step
            x += step
        return found

    pi_sites = sites("POD_PI")
    hat_sites = sites("POD_HAT")
    bat_sites = sites("BATTERY_CHAMBER")

    # Enumerate Pi/HAT pairs first. The battery is the least constrained of the
    # three and only has to fit somewhere, so testing it last keeps the search
    # to pairs rather than triples.
    pairs = []
    for px, py, pbox in pi_sites:
        pi_gap = pbox.distance(route)
        for hx, hy, hbox in hat_sites:
            ribbon = hbox.distance(pbox)
            if ribbon < MIN_WEB:
                continue
            # How far the ribbon actually has to travel. "header" is the real
            # constraint and the default; the other two are kept because the
            # first layout was ruled on "edge" and it is worth being able to
            # reproduce how far wrong that was.
            span = {
                "header": _header_span,
                "centre": _centres,
                "edge": lambda a, b: a.distance(b),
            }[ribbon_metric](pbox, hbox)
            if span > RIBBON_LENGTH:
                continue
            pairs.append(
                {
                    "pi_gap": pi_gap,
                    "hat_gap": hbox.distance(route),
                    # The Pi is the aggressor. Its nearest victim is whichever
                    # of the pickup coil and the analog board it sits closer
                    # to, so this is the number that actually bounds coupling.
                    "nearest_victim": min(pi_gap, ribbon),
                    "ribbon_gap": ribbon,
                    "ribbon_span": span,
                    "POD_PI": (px, py),
                    "POD_HAT": (hx, hy),
                    "_pi": pbox,
                    "_hat": hbox,
                }
            )

    def with_battery(cands: list[dict[str, Any]]) -> dict[str, Any] | None:
        for cand in cands:
            for bx, by, bbox in bat_sites:
                if (
                    bbox.distance(cand["_pi"]) >= MIN_WEB
                    and bbox.distance(cand["_hat"]) >= MIN_WEB
                ):
                    out = {k: v for k, v in cand.items() if not k.startswith("_")}
                    out["BATTERY_CHAMBER"] = (bx, by)
                    return out
        return None

    return {
        "site_counts": {
            "POD_PI": len(pi_sites),
            "POD_HAT": len(hat_sites),
            "BATTERY_CHAMBER": len(bat_sites),
        },
        "pairs": len(pairs),
        # What was asked for: push the Pi off the pickup, whatever it costs.
        "max_pickup_gap": with_battery(sorted(pairs, key=lambda c: -c["pi_gap"])),
        # What the physics asks for: push the Pi off whatever is nearest.
        "max_nearest_victim": with_battery(sorted(pairs, key=lambda c: -c["nearest_victim"])),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", type=float, default=2.5, help="grid step in mm")
    ap.add_argument(
        "--ribbon-metric",
        choices=("header", "centre", "edge"),
        default="header",
        help="how far the ribbon must travel; header is the real constraint",
    )
    args = ap.parse_args()

    result = solve(args.step, args.ribbon_metric)
    print(f"grid step {args.step} mm, y window {Y_MIN}-{Y_MAX} from top, "
          f"ribbon metric {args.ribbon_metric!r} (limit {RIBBON_LENGTH} mm)")
    print("web between a back pocket and the route where they overlap in plan:")
    for pocket in POCKETS:
        print(f"  {pocket:16s} {opposed_face_web(pocket):5.1f} mm  (min {MIN_WEB})")
    print()
    for pocket, count in result["site_counts"].items():
        print(f"  {pocket:16s} {count:5d} valid sites")
    print()

    print(f"  {result['pairs']} feasible POD_PI/POD_HAT pairs within ribbon reach")
    print()

    if result["max_pickup_gap"] is None or result["max_nearest_victim"] is None:
        print("NO PACKING FOUND")
        return 1

    for label, key in (
        ("A  maximise POD_PI clearance from the pickup route", "max_pickup_gap"),
        ("B  maximise POD_PI clearance from its NEAREST victim", "max_nearest_victim"),
    ):
        best = result[key]
        print(label)
        print(f"     POD_PI to route      {best['pi_gap']:6.1f} mm")
        print(f"     POD_PI to POD_HAT    {best['ribbon_gap']:6.1f} mm  (ribbon {RIBBON_LENGTH})")
        print(f"     POD_HAT to route     {best['hat_gap']:6.1f} mm")
        print(f"     ribbon span          {best['ribbon_span']:6.1f} mm")
        print(f"     nearest victim       {best['nearest_victim']:6.1f} mm")
        for pocket in POCKETS:
            x, y = best[pocket]
            print(f"       {pocket:16s} x {x:8.3f}  y_from_top {y:7.3f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
