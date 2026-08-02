"""Models for governed Smart Guitar cavity geometry.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Cavity dimensions are DERIVED from a component register, never asserted twice.
This exists because the Smart Guitar specs carried a cavity that could not hold
its own contents: sg-spec declared a 76 mm stacked assembly inside a 30.48 mm
pod, and luthiers-toolbox gave a 22 mm rear cavity with no room for the
HiFiBerry HAT at all. Neither is catchable by eye across three repositories.

The contract is therefore:

    component dimensions + clearances  ->  cavity dimensions  ->  fit verdict

A stale note like "total_height_mm: 76.0" cannot survive here, because nothing
downstream reads it: depth is recomputed from the parts and checked against the
blank. Conflicts that cannot be resolved arithmetically are recorded as
explicit conflict records rather than silently averaged.

These records describe physical geometry only. They carry no cost, price, or
manufacturing-time fields by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# How components occupy a cavity.
#   side_by_side  components sit beside each other on the cavity floor
#   stacked       components sit on top of one another
#   single        one component
CAVITY_LAYOUTS: frozenset[str] = frozenset({"side_by_side", "stacked", "single"})

# Where a component mounts. Lid-mounted parts may protrude outward through the
# cover instead of consuming cavity depth; that is what consumes_cavity_depth
# records, and it is the single variable that decides whether the Smart Guitar
# body needs to get thicker.
MOUNTING_SURFACES: frozenset[str] = frozenset({"floor", "lid"})

CAVITY_SURFACES: frozenset[str] = frozenset({"back", "top", "edge"})

CONFLICT_STATUSES: frozenset[str] = frozenset({"ruled", "unresolved"})


@dataclass(frozen=True)
class GeometryProvenanceV1:
    """Where a dimension came from, and how far it can be trusted."""

    source: str
    source_ref: str
    snapshot_date: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class ComponentV1:
    """One physical part with the clearances it needs around it.

    Dimensions are the bare part. Every allowance the part needs is explicit
    and separate, so a cavity can be recomputed when a clearance rule changes
    without re-measuring the part.
    """

    component_id: str
    display_name: str
    role: str
    length_mm: float
    width_mm: float
    height_mm: float
    mounting: str
    standoff_mm: float
    margin_length_mm: float
    margin_width_mm: float
    lid_clearance_mm: float
    consumes_cavity_depth: bool
    required: bool
    provenance: GeometryProvenanceV1

    def __post_init__(self) -> None:
        for name in (
            "length_mm",
            "width_mm",
            "height_mm",
            "standoff_mm",
            "margin_length_mm",
            "margin_width_mm",
            "lid_clearance_mm",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"component {self.component_id}: {name} must be a "
                    f"non-negative number"
                )
        if self.mounting not in MOUNTING_SURFACES:
            raise ValueError(
                f"component {self.component_id}: unsupported mounting "
                f"{self.mounting!r}"
            )

    @property
    def footprint_length_mm(self) -> float:
        """Part length plus its own edge margins."""
        return self.length_mm + 2 * self.margin_length_mm

    @property
    def footprint_width_mm(self) -> float:
        """Part width plus its own edge margins."""
        return self.width_mm + 2 * self.margin_width_mm

    @property
    def depth_demand_mm(self) -> float:
        """Cavity depth this part demands, zero if it protrudes outward."""
        if not self.consumes_cavity_depth:
            return 0.0
        return float(self.standoff_mm + self.height_mm + self.lid_clearance_mm)


@dataclass(frozen=True)
class CavityPlanV1:
    """What a cavity must contain and how, before any dimension is computed.

    stated_* fields carry whatever the source specs assert, purely so the
    derivation can be compared against them. They are never used as inputs.
    """

    cavity_id: str
    description: str
    surface: str
    layout: str
    component_ids: tuple[str, ...]
    inter_component_margin_mm: float
    min_floor_mm: float
    provenance: GeometryProvenanceV1
    stated_length_mm: float | None = None
    stated_width_mm: float | None = None
    stated_depth_mm: float | None = None

    def __post_init__(self) -> None:
        if self.layout not in CAVITY_LAYOUTS:
            raise ValueError(f"cavity {self.cavity_id}: unsupported layout {self.layout!r}")
        if self.surface not in CAVITY_SURFACES:
            raise ValueError(f"cavity {self.cavity_id}: unsupported surface {self.surface!r}")
        if not self.component_ids:
            raise ValueError(f"cavity {self.cavity_id}: must contain at least one component")
        if self.layout == "single" and len(self.component_ids) != 1:
            raise ValueError(
                f"cavity {self.cavity_id}: layout 'single' requires exactly one component"
            )
        if self.min_floor_mm < 0 or self.inter_component_margin_mm < 0:
            raise ValueError(f"cavity {self.cavity_id}: margins must be non-negative")


@dataclass(frozen=True)
class BodyBlankV1:
    """The blank the cavities are cut from."""

    body_id: str
    description: str
    stated_thickness_mm: float
    provenance: GeometryProvenanceV1

    def __post_init__(self) -> None:
        if self.stated_thickness_mm <= 0:
            raise ValueError("stated_thickness_mm must be greater than 0")


@dataclass(frozen=True)
class SpecConflictV1:
    """A disagreement between source specs, with its ruling if one exists.

    Recorded rather than resolved silently. An unresolved conflict is a
    first-class output of this Dev Order, not a failure of it.
    """

    conflict_id: str
    field: str
    sources: tuple[str, ...]
    status: str
    ruling: str
    ruled_by: str

    def __post_init__(self) -> None:
        if self.status not in CONFLICT_STATUSES:
            raise ValueError(f"conflict {self.conflict_id}: bad status {self.status!r}")
        if len(self.sources) < 2:
            raise ValueError(f"conflict {self.conflict_id}: needs at least two sources")


@dataclass(frozen=True)
class ComponentRegisterV1:
    """Governed snapshot of every part, plus the cavities and the blank."""

    register_id: str
    product_ref: str
    status: str
    units: str
    body: BodyBlankV1
    components: tuple[ComponentV1, ...]
    cavity_plans: tuple[CavityPlanV1, ...]
    conflicts: tuple[SpecConflictV1, ...]
    provenance: GeometryProvenanceV1
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CavityDerivationV1:
    """Computed geometry for one cavity, with its fit verdict."""

    cavity_id: str
    surface: str
    layout: str
    component_ids: tuple[str, ...]
    derived_length_mm: float
    derived_width_mm: float
    derived_depth_mm: float
    floor_remaining_mm: float
    min_floor_mm: float
    fit_ok: bool
    stated_length_mm: float | None
    stated_width_mm: float | None
    stated_depth_mm: float | None
    length_delta_mm: float | None
    width_delta_mm: float | None
    depth_delta_mm: float | None
    findings: tuple[str, ...]


@dataclass(frozen=True)
class BodyThicknessDerivationV1:
    """Whether the stated blank is thick enough for the derived cavities."""

    stated_thickness_mm: float
    required_thickness_mm: float
    governing_cavity_id: str
    margin_mm: float
    verdict: str


@dataclass(frozen=True)
class GeometryCalculationMetaV1:
    """Calculator identity and rounding policy."""

    calculator_id: str
    rounding_policy: str
    effective_date: str


@dataclass(frozen=True)
class SmartGuitarCavityGeometryV1:
    """Derived cavity geometry for the Smart Guitar body."""

    geometry_id: str
    register_id: str
    register_ref: str
    product_ref: str
    status: str
    units: str
    body: BodyThicknessDerivationV1
    cavities: tuple[CavityDerivationV1, ...]
    conflicts: tuple[SpecConflictV1, ...]
    calculation: GeometryCalculationMetaV1
    provenance: GeometryProvenanceV1
    notes: tuple[str, ...] = field(default_factory=tuple)
