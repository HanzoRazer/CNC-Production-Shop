"""Load Smart Guitar component-register fixtures into domain models.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from business.geometry.models import (
    BodyBlankV1,
    CavityPlanV1,
    ComponentRegisterV1,
    ComponentV1,
    GeometryProvenanceV1,
    SpecConflictV1,
)


def _prov(data: dict[str, Any]) -> GeometryProvenanceV1:
    return GeometryProvenanceV1(
        source=str(data["source"]),
        source_ref=str(data["source_ref"]),
        snapshot_date=str(data["snapshot_date"]),
        confidence=str(data["confidence"]),
        note=str(data.get("note", "") or ""),
    )


def _optional_mm(value: Any) -> float | None:
    return None if value is None else float(value)


def load_component_register(path: Path) -> ComponentRegisterV1:
    """Load ComponentRegisterV1 from a JSON fixture path."""
    with open(path, encoding="utf-8") as f:
        raw = cast(dict[str, Any], json.load(f))

    return ComponentRegisterV1(
        register_id=raw["register_id"],
        product_ref=raw["product_ref"],
        status=raw["status"],
        units=raw["units"],
        body=BodyBlankV1(
            body_id=raw["body"]["body_id"],
            description=raw["body"]["description"],
            stated_thickness_mm=float(raw["body"]["stated_thickness_mm"]),
            provenance=_prov(raw["body"]["provenance"]),
        ),
        components=tuple(
            ComponentV1(
                component_id=c["component_id"],
                display_name=c["display_name"],
                role=c["role"],
                length_mm=float(c["length_mm"]),
                width_mm=float(c["width_mm"]),
                height_mm=float(c["height_mm"]),
                mounting=c["mounting"],
                standoff_mm=float(c["standoff_mm"]),
                margin_length_mm=float(c["margin_length_mm"]),
                margin_width_mm=float(c["margin_width_mm"]),
                lid_clearance_mm=float(c["lid_clearance_mm"]),
                consumes_cavity_depth=bool(c["consumes_cavity_depth"]),
                required=bool(c["required"]),
                provenance=_prov(c["provenance"]),
            )
            for c in raw["components"]
        ),
        cavity_plans=tuple(
            CavityPlanV1(
                cavity_id=p["cavity_id"],
                description=p["description"],
                surface=p["surface"],
                layout=p["layout"],
                component_ids=tuple(p["component_ids"]),
                inter_component_margin_mm=float(p["inter_component_margin_mm"]),
                min_floor_mm=float(p["min_floor_mm"]),
                provenance=_prov(p["provenance"]),
                stated_length_mm=_optional_mm(p.get("stated_length_mm")),
                stated_width_mm=_optional_mm(p.get("stated_width_mm")),
                stated_depth_mm=_optional_mm(p.get("stated_depth_mm")),
            )
            for p in raw["cavity_plans"]
        ),
        conflicts=tuple(
            SpecConflictV1(
                conflict_id=c["conflict_id"],
                field=c["field"],
                sources=tuple(c["sources"]),
                status=c["status"],
                ruling=c["ruling"],
                ruled_by=c["ruled_by"],
            )
            for c in raw["conflicts"]
        ),
        provenance=_prov(raw["provenance"]),
        notes=tuple(raw.get("notes", [])),
    )
