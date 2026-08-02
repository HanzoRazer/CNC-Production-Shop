"""Pure calculator for Smart Guitar cavity geometry.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Derives every cavity dimension from the component register and checks it
against the blank. Reads no stated dimension as an input: stated values are
compared against the derivation and reported as deltas, so a spec that drifts
from its own contents produces a finding instead of a silent inconsistency.

Depth rules
-----------
side_by_side  every part sits on the cavity floor, so depth is set by the
              tallest single demand, not the sum
stacked       parts sit on one another, so demands add
single        one part

Lid-mounted parts are added on top of the floor-mounted stack only when they
consume cavity depth. A fan that vents outward through the cover does not.
That one flag decides whether the Smart Guitar body has to get thicker, which
is why it is explicit per component rather than assumed.

Body thickness
--------------
    required_thickness = max over cavities of (derived_depth + min_floor)

Reported against the stated blank rather than replacing it, so the blank stays
a reviewed decision and this stays evidence for it.
"""

from __future__ import annotations

from business.geometry.models import (
    BodyThicknessDerivationV1,
    CavityDerivationV1,
    CavityPlanV1,
    ComponentRegisterV1,
    ComponentV1,
    GeometryCalculationMetaV1,
    GeometryProvenanceV1,
    SmartGuitarCavityGeometryV1,
)

CALCULATOR_ID = "smart_guitar_cavity_geometry_v1"
ROUNDING_POLICY = "millimetre_half_up_2dp"
DEFAULT_GEOMETRY_ID = "SMART-GUITAR-CAVITY-GEOMETRY-V1"

VERDICT_SUFFICIENT = "sufficient"
VERDICT_INSUFFICIENT = "insufficient"


def as_mm(value: float) -> float:
    """Round a millimetre dimension using the geometry convention (2 dp)."""
    return round(float(value), 2)


def mm_equal(left: float | None, right: float | None) -> bool:
    """Compare millimetre dimensions after explicit rounding."""
    if left is None or right is None:
        return left is None and right is None
    return as_mm(left) == as_mm(right)


def _components_by_id(
    components: tuple[ComponentV1, ...] | list[ComponentV1],
) -> dict[str, ComponentV1]:
    mapping: dict[str, ComponentV1] = {}
    for component in components:
        if component.component_id in mapping:
            raise ValueError(f"duplicate component_id: {component.component_id}")
        mapping[component.component_id] = component
    return mapping


def _resolve(
    plan: CavityPlanV1, registry: dict[str, ComponentV1]
) -> tuple[ComponentV1, ...]:
    resolved: list[ComponentV1] = []
    for component_id in plan.component_ids:
        if component_id not in registry:
            raise ValueError(
                f"cavity {plan.cavity_id} references unknown component_id: {component_id}"
            )
        resolved.append(registry[component_id])
    return tuple(resolved)


def derive_cavity_depth(
    components: tuple[ComponentV1, ...] | list[ComponentV1],
    layout: str,
) -> float:
    """Depth demanded by a set of components under a layout.

    Floor-mounted parts either share the floor (side_by_side, single) or stack
    on each other (stacked). Lid-mounted parts that consume depth always add on
    top of whichever the floor arrangement produced.
    """
    floor_parts = [c for c in components if c.mounting == "floor"]
    lid_parts = [c for c in components if c.mounting == "lid"]

    floor_demands = [c.depth_demand_mm for c in floor_parts]
    if layout == "stacked":
        floor_depth = sum(floor_demands)
    else:
        floor_depth = max(floor_demands, default=0.0)

    lid_depth = sum(c.depth_demand_mm for c in lid_parts)
    return as_mm(floor_depth + lid_depth)


def derive_cavity_footprint(
    components: tuple[ComponentV1, ...] | list[ComponentV1],
    layout: str,
    inter_component_margin_mm: float,
) -> tuple[float, float]:
    """Return (length, width) demanded by a set of components under a layout.

    side_by_side lays parts along the length axis, so lengths add and the
    inter-component margin applies between neighbours. Every other layout
    overlaps them in plan, so the largest footprint governs.
    """
    if not components:
        raise ValueError("cavity must contain at least one component")

    # Only floor-mounted parts compete for plan area. A lid-mounted part sits
    # above them, so it widens the cavity only if its own footprint is larger.
    floor_parts = [c for c in components if c.mounting == "floor"]
    lid_parts = [c for c in components if c.mounting == "lid"]

    if layout == "side_by_side" and len(floor_parts) > 1:
        bare_length = sum(c.length_mm for c in floor_parts)
        gaps = (len(floor_parts) - 1) * inter_component_margin_mm
        edge = 2 * max(c.margin_length_mm for c in floor_parts)
        length = bare_length + gaps + edge
    elif floor_parts:
        length = max(c.footprint_length_mm for c in floor_parts)
    else:
        length = 0.0

    length = max(length, max((c.footprint_length_mm for c in lid_parts), default=0.0))
    width = max(c.footprint_width_mm for c in components)
    return as_mm(length), as_mm(width)


def derive_cavity(
    plan: CavityPlanV1,
    registry: dict[str, ComponentV1],
    body_thickness_mm: float,
) -> CavityDerivationV1:
    """Derive one cavity's geometry and compare it against what specs assert."""
    components = _resolve(plan, registry)
    length, width = derive_cavity_footprint(
        components, plan.layout, plan.inter_component_margin_mm
    )
    depth = derive_cavity_depth(components, plan.layout)
    floor_remaining = as_mm(body_thickness_mm - depth)
    fit_ok = floor_remaining >= plan.min_floor_mm

    findings: list[str] = []
    if not fit_ok:
        findings.append(
            f"floor_remaining {floor_remaining} mm is below min_floor "
            f"{plan.min_floor_mm} mm: cavity does not fit the stated blank"
        )

    def _delta(stated: float | None, derived: float) -> float | None:
        return None if stated is None else as_mm(stated - derived)

    length_delta = _delta(plan.stated_length_mm, length)
    width_delta = _delta(plan.stated_width_mm, width)
    depth_delta = _delta(plan.stated_depth_mm, depth)

    for axis, stated, derived, delta in (
        ("length", plan.stated_length_mm, length, length_delta),
        ("width", plan.stated_width_mm, width, width_delta),
        ("depth", plan.stated_depth_mm, depth, depth_delta),
    ):
        if delta is None:
            continue
        if delta < 0:
            findings.append(
                f"stated {axis} {stated} mm is SMALLER than derived {derived} mm "
                f"by {abs(delta)} mm: the spec cannot hold its own contents"
            )
        elif delta > 0:
            findings.append(
                f"stated {axis} {stated} mm exceeds derived {derived} mm by "
                f"{delta} mm of slack"
            )

    return CavityDerivationV1(
        cavity_id=plan.cavity_id,
        surface=plan.surface,
        layout=plan.layout,
        component_ids=tuple(plan.component_ids),
        derived_length_mm=length,
        derived_width_mm=width,
        derived_depth_mm=depth,
        floor_remaining_mm=floor_remaining,
        min_floor_mm=plan.min_floor_mm,
        fit_ok=fit_ok,
        stated_length_mm=plan.stated_length_mm,
        stated_width_mm=plan.stated_width_mm,
        stated_depth_mm=plan.stated_depth_mm,
        length_delta_mm=length_delta,
        width_delta_mm=width_delta,
        depth_delta_mm=depth_delta,
        findings=tuple(findings),
    )


def derive_required_body_thickness(
    derivations: tuple[CavityDerivationV1, ...] | list[CavityDerivationV1],
    stated_thickness_mm: float,
) -> BodyThicknessDerivationV1:
    """Thinnest blank that satisfies every cavity's depth and floor minimum."""
    if not derivations:
        raise ValueError("at least one cavity derivation is required")

    governing = max(derivations, key=lambda d: d.derived_depth_mm + d.min_floor_mm)
    required = as_mm(governing.derived_depth_mm + governing.min_floor_mm)
    margin = as_mm(stated_thickness_mm - required)

    return BodyThicknessDerivationV1(
        stated_thickness_mm=as_mm(stated_thickness_mm),
        required_thickness_mm=required,
        governing_cavity_id=governing.cavity_id,
        margin_mm=margin,
        verdict=VERDICT_SUFFICIENT if margin >= 0 else VERDICT_INSUFFICIENT,
    )


def derive_cavity_geometry(
    register: ComponentRegisterV1,
    *,
    geometry_id: str = DEFAULT_GEOMETRY_ID,
    register_ref: str,
    effective_date: str,
) -> SmartGuitarCavityGeometryV1:
    """Derive the complete cavity geometry record from a component register."""
    if register.status == "approved" and register.provenance.confidence != "approved":
        raise ValueError("approved register requires approved provenance confidence")
    if register.provenance.confidence == "draft" and register.status not in {
        "draft",
        "superseded",
        "retired",
    }:
        raise ValueError("draft provenance cannot produce a reviewed/approved register")

    registry = _components_by_id(register.components)

    cavity_ids = [plan.cavity_id for plan in register.cavity_plans]
    if len(cavity_ids) != len(set(cavity_ids)):
        raise ValueError("duplicate cavity_id values are not allowed")
    if not register.cavity_plans:
        raise ValueError("register must declare at least one cavity plan")

    # Dangling references are checked before placement completeness: an unknown
    # component_id is the more fundamental error and gives the clearer message.
    placed: set[str] = set()
    for plan in register.cavity_plans:
        for component_id in plan.component_ids:
            if component_id not in registry:
                raise ValueError(
                    f"cavity {plan.cavity_id} references unknown component_id: "
                    f"{component_id}"
                )
            if component_id in placed:
                raise ValueError(
                    f"component {component_id} is placed in more than one cavity"
                )
            placed.add(component_id)

    unplaced = {
        c.component_id for c in register.components if c.required
    } - placed
    if unplaced:
        raise ValueError(f"required components are not placed: {sorted(unplaced)}")

    thickness = register.body.stated_thickness_mm
    derivations = tuple(
        derive_cavity(plan, registry, thickness) for plan in register.cavity_plans
    )
    body = derive_required_body_thickness(derivations, thickness)

    return SmartGuitarCavityGeometryV1(
        geometry_id=geometry_id,
        register_id=register.register_id,
        register_ref=register_ref,
        product_ref=register.product_ref,
        status=register.status,
        units=register.units,
        body=body,
        cavities=derivations,
        conflicts=tuple(register.conflicts),
        calculation=GeometryCalculationMetaV1(
            calculator_id=CALCULATOR_ID,
            rounding_policy=ROUNDING_POLICY,
            effective_date=effective_date,
        ),
        provenance=GeometryProvenanceV1(
            source="calculated",
            source_ref=register_ref,
            snapshot_date=register.provenance.snapshot_date,
            confidence=register.provenance.confidence,
            note=(
                "Physical geometry only. Derived from the component register; "
                "stated spec dimensions are compared, never consumed."
            ),
        ),
        notes=tuple(register.notes),
    )


__all__ = [
    "CALCULATOR_ID",
    "DEFAULT_GEOMETRY_ID",
    "ROUNDING_POLICY",
    "VERDICT_INSUFFICIENT",
    "VERDICT_SUFFICIENT",
    "as_mm",
    "derive_cavity",
    "derive_cavity_depth",
    "derive_cavity_footprint",
    "derive_cavity_geometry",
    "derive_required_body_thickness",
    "mm_equal",
]
