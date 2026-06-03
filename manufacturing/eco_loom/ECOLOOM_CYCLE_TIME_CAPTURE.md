# Eco-Loom — Cycle Time Capture

**Sprint:** ECOLOOM-MFG-READINESS-1
**Status:** draft capture

> **This is the most important document in the sprint.**

Machine runtime (cycle time) is the primary unknown. It drives machine cost,
labor, electricity, and tool wear — which ultimately drive quote price. All
values are `draft` placeholders until supplied by the AutoCAD designer /
machinist. Capture in **minutes**.

---

## Runtime Breakdown

| Component | Estimated Minutes | Source | Confidence |
| --- | --- | --- | --- |
| Cut Time | | | draft |
| Rapid Time | | | draft |
| Tool Change Time | | | draft |
| Load/Unload Time | | | draft |
| Setup Time | | | draft |
| **Total Runtime** | | | draft |

---

## Per-Operation Capture

Repeat this block for each operation in `ECOLOOM_PROCESS_PLAN.md`.

### Operation 10

| Field | Value |
| --- | --- |
| Operation | |
| Estimated Minutes | |
| Source | |
| Confidence | draft |

### Operation 20

| Field | Value |
| --- | --- |
| Operation | |
| Estimated Minutes | |
| Source | |
| Confidence | draft |

### Operation 30

| Field | Value |
| --- | --- |
| Operation | |
| Estimated Minutes | |
| Source | |
| Confidence | draft |

---

> **Cost-engine note:** total runtime is captured here in **minutes**. The cost
> fixture (`eco_loom_cost_inputs_v1.json`) records `machine_runtime_minutes`,
> which the cost engine converts to `machine_runtime_hours` (÷ 60). See the
> README's *Relationship to Cost Engine* section.
