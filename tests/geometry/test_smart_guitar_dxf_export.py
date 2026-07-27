"""Tests for the Smart Guitar DXF export.

The export is handed to CAD, so the things worth guarding are the ones a
reader would silently get wrong: declared units, the sign convention, closed
profiles, face separation, and extents matching the governed blank.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import ezdxf
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from export_smart_guitar_dxf import (  # noqa: E402
    BODY_LENGTH_MM,
    BODY_WIDTH_MM,
    CAVITIES,
    DOCUMENTED_BASS_OVERHANG_MM,
    LAYERS,
    SOURCES,
    build_document,
    rect,
)


def _written(tmp_path_factory, source: str):
    document, _, _, _ = build_document("R2010", source)
    path = tmp_path_factory.mktemp("dxf") / f"{source}.dxf"
    document.saveas(path)
    return ezdxf.readfile(path)


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    """Round-trip through a real file rather than testing the in-memory doc."""
    return _written(tmp_path_factory, "back_v5")


def test_units_are_declared_as_millimetres(doc):
    """A DXF without declared units imports at whatever the host assumes."""
    assert doc.units == 4
    assert doc.header["$INSUNITS"] == 4
    assert doc.header["$MEASUREMENT"] == 1


def test_every_declared_layer_exists(doc):
    present = {layer.dxf.name for layer in doc.layers}
    assert set(LAYERS) <= present


def test_faces_are_on_separate_layers(doc):
    """Two-sided part: cutting a back cavity from the front mirrors it."""
    layers = {e.dxf.layer for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE"}
    assert "CAV_TOP" in layers
    assert "CAV_BACK" in layers


def test_all_profiles_are_closed(doc):
    """An open profile silently becomes an open path in CAM."""
    polylines = [e for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE"]
    assert polylines
    assert all(e.closed for e in polylines)


def test_body_extents_match_the_governed_blank(doc):
    body = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "BODY_OUTLINE"
    ]
    assert len(body) == 1
    pts = [(p[0], p[1]) for p in body[0].get_points()]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    assert len(pts) == 79  # back_v5 carries the richest outline
    assert max(xs) - min(xs) == pytest.approx(BODY_WIDTH_MM, abs=0.01)
    assert max(ys) - min(ys) == pytest.approx(BODY_LENGTH_MM, abs=0.01)
    # Body top normalised to y = 0: it is the datum every y_from_top is
    # measured from, so cavity y reads directly as -y_from_top.
    assert max(ys) == pytest.approx(0.0, abs=0.01)
    assert min(ys) == pytest.approx(-BODY_LENGTH_MM, abs=0.01)


def test_entity_counts_are_as_intended(doc):
    counts = Counter(e.dxftype() for e in doc.modelspace())
    # 1 outline + 4 through-body voids + 8 cavities
    assert counts["LWPOLYLINE"] == 13
    assert counts["LINE"] == 1  # centreline reference


def test_pod_sits_on_the_treble_side(doc):
    """+X is treble, ruled 2026-07-27. The pod is the asymmetric feature.

    If the sign convention were ever flipped back, this is where it shows:
    the pod would land on the bass half with nothing else complaining.
    """
    pod = next(c for c in CAVITIES if c[1] == "POD")
    _, _, cx, _, _, _ = pod
    assert cx > 0, "pod centre must be positive, i.e. treble"

    profiles = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CAV_BACK"
    ]
    centres = [
        sum(p[0] for p in e.get_points()) / len(e.get_points()) for e in profiles
    ]
    assert any(c == pytest.approx(74.0, abs=0.01) for c in centres)


def test_rect_is_centred_on_its_station():
    """y_from_top is measured down from the body top, not up from the tail."""
    corners = rect(cx=10.0, y_from_top=100.0, w=20.0, h=10.0, top_y=202.6)
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    assert min(xs) == 0.0 and max(xs) == 20.0
    assert sum(ys) / 4 == pytest.approx(102.6)


@pytest.mark.parametrize("source", sorted(SOURCES))
def test_every_source_normalises_to_the_same_blank(tmp_path_factory, source):
    """Three outlines of differing fidelity must emit one blank size.

    They disagree on point count and on x placement, but all carry aspect
    0.8599, so any of them scaled to 468.5 must give 402.85.
    """
    written = _written(tmp_path_factory, source)
    body = next(
        e
        for e in written.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "BODY_OUTLINE"
    )
    pts = [(p[0], p[1]) for p in body.get_points()]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert max(xs) - min(xs) == pytest.approx(BODY_WIDTH_MM, abs=0.05)
    assert max(ys) - min(ys) == pytest.approx(BODY_LENGTH_MM, abs=0.01)
    # Body top normalised to y = 0 so cavity y is simply -y_from_top.
    assert max(ys) == pytest.approx(0.0, abs=0.01)


def test_back_v5_and_trace_agree_on_the_centreline(tmp_path_factory):
    """The documented bass overhang is the check on horizontal placement.

    back_v5 and the trace reproduce 12.28 mm exactly. front_v5 does not, and
    is deliberately not asserted here — see the centreline warning the export
    emits for it.
    """
    for source in ("back_v5", "trace"):
        written = _written(tmp_path_factory, source)
        body = next(
            e
            for e in written.modelspace()
            if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "BODY_OUTLINE"
        )
        xs = [p[0] for p in body.get_points()]
        overhang = abs(min(xs)) - max(xs)
        assert overhang == pytest.approx(
            DOCUMENTED_BASS_OVERHANG_MM, abs=0.05
        ), source


def test_export_script_runs_and_self_checks():
    import subprocess

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_smart_guitar_dxf.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "468.50" in result.stdout
    assert "402.85" in result.stdout
