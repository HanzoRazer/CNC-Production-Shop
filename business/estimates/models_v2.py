"""Models for governed thin-skin guitar manufacturing estimates.

Dev Order: THIN-SKIN-GUITAR-BUILD-ESTIMATE-1

V2 supersedes the V1 records in business/estimates/models.py for the thin-skin
laminated-body architecture. V1 is retained unchanged so the solid-body
baseline stays recomputable as a comparison variant.

Three contract changes versus V1:

1. Six-field time model per operation. V1 collapsed process behavior into
   labor-ish minutes; V2 keeps operator touch, CNC runtime, equipment
   occupancy, and elapsed wait strictly separate, because press occupancy,
   cure time, and unattended CNC runtime are not labor.

2. Eighteen explicit cost categories. Lamination, finishing, and equipment
   occupancy are first-class lines rather than being buried inside generic
   labor, since they are the economic variables this architecture is
   supposed to expose.

3. Two independent risk mechanisms. A narrow material scrap allowance and a
   broader process/yield reserve, each with its own explicit eligibility, so
   a new laminated process is not modeled with a single blended percentage.

These records describe internal manufacturing cost only. They carry no
customer price, markup, margin, or overhead allocation by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from business.bids.models import MachineCostingV1

# Input categories that roll up to the material-side cost lines. An input may
# appear in either material_inputs or purchased_component_inputs; the category
# alone decides which summary line it lands on.
MATERIAL_CATEGORIES: frozenset[str] = frozenset(
    {
        "core_material",
        "skin_material",
        "adhesive_lamination",
        "neck_fretboard",
        "hardware",
        "electronics",
        "finish_material",
        "other_consumables",
    }
)

# Labor categories that roll up to the conversion-side cost lines.
LABOR_CATEGORIES: frozenset[str] = frozenset(
    {
        "lamination_labor",
        "direct_build_labor",
        "finishing_labor",
        "assembly_labor",
        "setup_and_inspection",
    }
)

# Attendance describes how the operator relates to the operation's elapsed
# time. It is documentation for review, not a cost multiplier: labor minutes
# are always stated explicitly rather than inferred from attendance.
ATTENDANCE_MODES: frozenset[str] = frozenset(
    {
        "attended",
        "partially_attended",
        "unattended",
        "queue_or_cure",
    }
)

# Whether an operation's setup recurs for every unit or once for a whole run.
# per_unit is the default and the pre-existing behaviour: before this field
# existed the calculator multiplied setup by quantity, so every record written
# without it must keep resolving that way.
SETUP_SCOPE_PER_UNIT = "per_unit"
SETUP_SCOPE_PER_BATCH = "per_batch"
SETUP_SCOPES: frozenset[str] = frozenset({SETUP_SCOPE_PER_UNIT, SETUP_SCOPE_PER_BATCH})


@dataclass(frozen=True)
class EstimateProvenanceV2:
    """Provenance for an estimate input, equipment record, or estimate."""

    source: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class MaterialInputV2:
    """Stock material consumed by the build, eligible for scrap allowance."""

    input_id: str
    description: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    provenance: EstimateProvenanceV2


@dataclass(frozen=True)
class PurchasedComponentInputV2:
    """Discrete purchased part; not stock, so scrap eligibility is opt-in."""

    input_id: str
    description: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    provenance: EstimateProvenanceV2


@dataclass(frozen=True)
class LaborRateInputV2:
    """Loaded labor rate definition used by operations."""

    labor_rate_id: str
    description: str
    base_wage_per_hour: float
    payroll_burden_pct: float
    loaded_rate_per_hour: float
    provenance: EstimateProvenanceV2


@dataclass(frozen=True)
class OperationTimeModelV2:
    """Six-field time model for one operation.

    The separation is the point of the record:

        setup_minutes               operator present, job-preparation labor
        operator_touch_minutes      operator present, process labor
        machine_runtime_minutes     CNC time attributable to the job
        equipment_occupancy_minutes non-CNC equipment held by the job
        elapsed_wait_minutes        calendar time consuming neither
        rework_minutes              operator present, in-process correction

    Labor is setup + operator_touch + rework. Machine runtime, equipment
    occupancy, and elapsed wait never become labor, and may overlap each
    other or overlap labor freely.

    setup_scope decides whether setup recurs per unit or once per batch. It
    defaults to per_unit, which is what every record written before it existed
    assumed, so an omitted value resolves to the prior behaviour and no
    existing estimate moves. Only an operation that explicitly declares
    per_batch is treated as amortisable, and at quantity one the two are
    arithmetically identical.
    """

    setup_minutes: float = 0.0
    operator_touch_minutes: float = 0.0
    machine_runtime_minutes: float = 0.0
    equipment_occupancy_minutes: float = 0.0
    elapsed_wait_minutes: float = 0.0
    rework_minutes: float = 0.0
    setup_scope: str = SETUP_SCOPE_PER_UNIT

    def __post_init__(self) -> None:
        for name in (
            "setup_minutes",
            "operator_touch_minutes",
            "machine_runtime_minutes",
            "equipment_occupancy_minutes",
            "elapsed_wait_minutes",
            "rework_minutes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative number")
        if self.setup_scope not in SETUP_SCOPES:
            raise ValueError(
                f"setup_scope must be one of {sorted(SETUP_SCOPES)}, "
                f"got {self.setup_scope!r}"
            )

    @property
    def labor_minutes(self) -> float:
        """Operator-present minutes for ONE unit, setup included.

        Unchanged by setup_scope on purpose. This is the per-unit reading and
        every existing caller wants it; batch allocation is the calculator's
        job, not this property's, because only the calculator knows the
        quantity.
        """
        return float(
            self.setup_minutes + self.operator_touch_minutes + self.rework_minutes
        )

    def labor_minutes_for(self, quantity: int) -> float:
        """Operator-present minutes for a run of `quantity` units.

        The one place batch semantics apply. per_unit multiplies everything;
        per_batch charges setup once and multiplies the rest. At quantity one
        they agree exactly, which is what keeps existing records still.
        """
        if quantity < 1:
            raise ValueError("quantity must be >= 1")
        variable = self.operator_touch_minutes + self.rework_minutes
        if self.setup_scope == SETUP_SCOPE_PER_BATCH:
            return float(self.setup_minutes + variable * quantity)
        return float(self.labor_minutes * quantity)


@dataclass(frozen=True)
class ManufacturingOperationV2:
    """One WBS leaf operation.

    Every WBS leaf carries exactly one operation record, including leaves with
    no time, so the work breakdown stays auditable against the published WBS.
    """

    operation_id: str
    wbs_code: str
    description: str
    labor_category: str
    attendance: str
    time_model: OperationTimeModelV2
    labor_rate_id: str
    provenance: EstimateProvenanceV2
    uses_machine: bool = False
    equipment_id: str = ""
    reserve_eligible: bool = False


@dataclass(frozen=True)
class MaterialScrapPolicyV2:
    """Narrow scrap allowance on explicitly listed stock material IDs."""

    scrap_rate: float
    eligible_input_ids: tuple[str, ...]
    provenance: EstimateProvenanceV2


@dataclass(frozen=True)
class ProcessYieldReservePolicyV2:
    """Broader process/rework/yield reserve on eligible conversion cost.

    The reserve base is deliberately assembled from explicit opt-ins rather
    than from a category sweep, so that adding a high-value purchased part
    can never silently inflate the reserve. The material scrap allowance is
    never part of this base: the two mechanisms do not compound.
    """

    reserve_rate: float
    eligible_input_ids: tuple[str, ...]
    include_machine_time: bool
    include_equipment_occupancy: bool
    provenance: EstimateProvenanceV2


@dataclass(frozen=True)
class EquipmentRefV2:
    """Reference to a governed equipment profile and its cost basis."""

    equipment_id: str
    equipment_profile_ref: str
    cost_basis_ref: str
    cost_basis_id: str


@dataclass(frozen=True)
class EquipmentOccupancyCostingV1:
    """Auditable occupancy derivation for one piece of equipment."""

    equipment_id: str
    equipment_profile_ref: str
    cost_basis_id: str
    cost_basis_ref: str
    cost_basis_role: str
    occupancy_minutes: float
    equipment_hour_rate: float
    derived_occupancy_cost: float
    derivation: str
    provenance_status: str


@dataclass(frozen=True)
class ThinSkinEstimateInputV2:
    """Complete governed estimate input for a thin-skin laminated body."""

    estimate_input_id: str
    product_id: str
    product_ref: str
    variant_id: str
    variant_description: str
    status: str
    quantity: int
    currency: str
    material_inputs: tuple[MaterialInputV2, ...]
    purchased_component_inputs: tuple[PurchasedComponentInputV2, ...]
    labor_rate_inputs: tuple[LaborRateInputV2, ...]
    operations: tuple[ManufacturingOperationV2, ...]
    machine_profile_ref: str
    cost_basis_ref: str
    machine_id: str
    cost_basis_id: str
    equipment_refs: tuple[EquipmentRefV2, ...]
    material_scrap_policy: MaterialScrapPolicyV2
    process_yield_reserve_policy: ProcessYieldReservePolicyV2
    provenance: EstimateProvenanceV2
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationCostResultV2:
    """Calculated result for one operation, times preserved alongside cost."""

    operation_id: str
    wbs_code: str
    labor_category: str
    attendance: str
    labor_minutes: float
    machine_runtime_minutes: float
    equipment_occupancy_minutes: float
    elapsed_wait_minutes: float
    rework_minutes: float
    equipment_id: str
    labor_cost: float
    machine_time_cost: float
    equipment_occupancy_cost: float
    operation_cost: float


@dataclass(frozen=True)
class ThinSkinTimeSummaryV2:
    """Aggregate process behavior, reported independently of cost.

    Kept as a first-class summary because the commercial question is about
    touch labor and throughput, not only dollars.
    """

    total_labor_minutes: float
    total_machine_runtime_minutes: float
    total_equipment_occupancy_minutes: float
    total_elapsed_wait_minutes: float
    total_rework_minutes: float
    lamination_labor_minutes: float
    direct_build_labor_minutes: float
    finishing_labor_minutes: float
    assembly_labor_minutes: float
    setup_and_inspection_minutes: float


@dataclass(frozen=True)
class ThinSkinCostSummaryV2:
    """Explicit manufacturing cost categories for the thin-skin architecture."""

    core_material_cost: float
    skin_material_cost: float
    adhesive_and_lamination_consumables: float
    neck_and_fretboard_cost: float
    hardware_cost: float
    electronics_cost: float
    finish_material_cost: float
    other_consumables_cost: float
    machine_time_cost: float
    equipment_occupancy_cost: float
    lamination_labor_cost: float
    direct_build_labor_cost: float
    finishing_labor_cost: float
    assembly_labor_cost: float
    setup_and_inspection_cost: float
    material_scrap_allowance: float
    process_rework_and_yield_reserve: float
    total_direct_manufacturing_cost: float


@dataclass(frozen=True)
class RiskBasisDetailV2:
    """Audit trail for how each risk mechanism's base was assembled."""

    material_scrap_rate: float
    material_scrap_base: float
    process_reserve_rate: float
    process_reserve_material_base: float
    process_reserve_machine_base: float
    process_reserve_equipment_base: float
    process_reserve_labor_base: float
    process_reserve_base: float
    compounding: str


@dataclass(frozen=True)
class EstimateCalculationMetaV2:
    """Calculator identity and rounding policy."""

    calculator_id: str
    rounding_policy: str
    effective_date: str


@dataclass(frozen=True)
class ThinSkinBuildEstimateV2:
    """Calculated internal thin-skin guitar manufacturing estimate."""

    estimate_id: str
    product_id: str
    product_ref: str
    variant_id: str
    variant_description: str
    estimate_input_id: str
    estimate_input_ref: str
    status: str
    quantity: int
    currency: str
    cost_summary: ThinSkinCostSummaryV2
    time_summary: ThinSkinTimeSummaryV2
    risk_basis: RiskBasisDetailV2
    operation_results: tuple[OperationCostResultV2, ...]
    machine_costing: MachineCostingV1
    equipment_costing: tuple[EquipmentOccupancyCostingV1, ...]
    calculation: EstimateCalculationMetaV2
    provenance: EstimateProvenanceV2
    notes: tuple[str, ...] = field(default_factory=tuple)
