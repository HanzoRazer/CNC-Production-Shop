# Eco-Loom — Manufacturing Readiness

**Sprint:** ECOLOOM-MFG-READINESS-1
**Status:** draft capture

This directory captures the manufacturing information required to transform
Eco-Loom from an *Executable Product Specification* into a
*Manufacturing-Ready Product Definition*.

It is **knowledge capture**, not CAM. No toolpaths, production quotes, or
machine code are produced here. The documents and fixtures collect the inputs
that the costing engine needs to produce bid-quality estimates.

---

## Purpose

Provide a governed destination for manufacturing information arriving from the
AutoCAD designer and, later, the CNC machinist. Each document is a capture
template; values remain `draft` placeholders until a human supplies them in a
later sprint (`ECOLOOM-CYCLETIME-1`).

The primary unknown this sprint exists to capture is **machine runtime
(cycle time)**, because runtime drives machine cost, labor, electricity, and
tool wear — which ultimately drive quote price.

---

## Inputs

Supplied by upstream design and manufacturing review:

- STEP model (from OpenSCAD specification → STEP → AutoCAD)
- Drawing package
- Material and stock selection
- Machine and workholding selection
- Tooling list
- Process sequence
- Cycle-time estimates

---

## Outputs

Captured in this directory and the related `fixtures/eco_loom/` and
`schemas/eco_loom/` directories:

- `ECOLOOM_MANUFACTURING_ASSUMPTIONS.md` — material, stock, machine, workholding
- `ECOLOOM_PROCESS_PLAN.md` — operation sequence
- `ECOLOOM_TOOLING_PLAN.md` — tooling list
- `ECOLOOM_CYCLE_TIME_CAPTURE.md` — runtime breakdown (primary deliverable)
- `ECOLOOM_MANUFACTURING_READINESS_CHECKLIST.md` — readiness gate
- `fixtures/eco_loom/eco_loom_cost_inputs_v1.json` — cost engine inputs *(Phase 3)*
- `fixtures/eco_loom/eco_loom_manufacturing_fixture_v1.json` — single manufacturing record *(Phase 3)*

---

## Required Deliverables

Before Eco-Loom is manufacturing-ready, the following must be supplied:

- [ ] STEP model complete
- [ ] Drawing package complete
- [ ] Material selected
- [ ] Stock size selected
- [ ] Tooling identified
- [ ] Process plan created
- [ ] Cycle time estimated
- [ ] Cost inputs recorded
- [ ] Manufacturing fixture generated

See `ECOLOOM_MANUFACTURING_READINESS_CHECKLIST.md` for the authoritative gate.

---

## Relationship to Cost Engine

The cost-input fixture (`fixtures/eco_loom/eco_loom_cost_inputs_v1.json`, created
in Phase 3) feeds the existing pure cost kernel in
`business/calculators/` (`SimpleJobCostInput` →
`calculate_simple_job_cost`).

`cost_inputs_v1` **intentionally captures only the manufacturing-derived subset**
required for this sprint. The mapping below is documented honestly: some
calculator inputs are deliberately *not* present yet. The gap is meant to be
visible, not solved in this sprint.

### Direct mappings

| `eco_loom_cost_inputs_v1.json` | `SimpleJobCostInput` |
| --- | --- |
| `material_cost` | `material_cost` |
| `operator_rate` | `operator_wage_per_hour` |
| `payroll_burden_pct` | `payroll_burden_pct` |
| `machine_burden_rate` | `machine_burden_rate_per_hour` |
| `electricity_rate_per_hour` | `electricity_cost_per_hour` |
| `tooling_rate_per_hour` | `tooling_cost_per_hour` |
| `setup_cost` | `setup_programming_cost` |
| `target_margin_pct` | `target_margin_pct` |

### Unit transformation

| `eco_loom_cost_inputs_v1.json` | `SimpleJobCostInput` | Transform |
| --- | --- | --- |
| `machine_runtime_minutes` | `machine_runtime_hours` | ÷ 60 |

### Fields not covered by `cost_inputs_v1`

The following `SimpleJobCostInput` fields have **no source** in
`cost_inputs_v1`:

- `operator_hours`
- `consumables_cost`
- `scrap_pct`
- `contingency_pct`

> These values are expected to be supplied by manufacturing analysis, quote
> preparation, or future fixture revisions. `cost_inputs_v1` intentionally
> captures only the manufacturing-derived subset required for
> ECOLOOM-MFG-READINESS-1.

No defaults are introduced, the schema is not expanded, and no `v2` is created
in this sprint. The gap is documented so it can be captured deliberately in a
future sprint.
