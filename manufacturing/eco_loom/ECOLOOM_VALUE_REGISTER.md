# Eco-Loom — Value Register

**Sprint:** ECOLOOM-CYCLETIME-1
**Status:** draft capture
**Instance:** `draft_001`

Single human-readable sheet of the current Eco-Loom assumptions — for quick
reference on a call with the machinist, customer, or AutoCAD designer. The
machine-readable source of truth is the instance fixtures under
`fixtures/eco_loom/instances/`; provenance is in the `*.provenance.json`
sidecars. This sheet mirrors them and must be kept in sync.

> **Nothing here is verified.** Every value is `draft`. Shop-level rates are
> established shop estimates; everything product-specific is a placeholder
> pending the AutoCAD/CAM deliverable and machinist review. Do not quote or bid
> from this sheet.

---

## Cost Inputs — `eco_loom_cost_inputs_draft_001.json`

| Field | Value | Source | Confidence |
| --- | --- | --- | --- |
| material_cost | 0 *(pending)* | engineering_estimate | draft |
| machine_runtime_minutes | 0 *(pending)* | engineering_estimate | draft |
| operator_rate | 23.0 | shop_estimate | draft |
| payroll_burden_pct | 25.0 | shop_estimate | draft |
| machine_burden_rate | 19.0 | shop_estimate | draft |
| electricity_rate_per_hour | 1.97 | shop_estimate | draft |
| tooling_rate_per_hour | 8.0 | shop_estimate | draft |
| setup_cost | 0 *(pending)* | engineering_estimate | draft |
| target_margin_pct | 30.0 | shop_estimate | draft |

## Manufacturing Fixture — `eco_loom_manufacturing_fixture_draft_001.json`

| Field | Value | Source | Confidence |
| --- | --- | --- | --- |
| material | *(pending)* | engineering_estimate | draft |
| stock_size | *(pending)* | engineering_estimate | draft |
| machine | *(pending)* | engineering_estimate | draft |
| workholding | *(pending)* | engineering_estimate | draft |
| tooling | *(pending)* | engineering_estimate | draft |
| operations | *(pending)* | engineering_estimate | draft |
| cycle_time_minutes | 0 *(pending)* | engineering_estimate | draft |

---

## Confidence Lifecycle

```text
draft  →  reviewed  →  approved
                          ↓
                      superseded   (when a later capture replaces an approved value)
```

- **draft** — engineering/shop estimate or AutoCAD designer estimate; not verified.
- **reviewed** — a machinist has reviewed the value.
- **approved** — approved for bid or production use.
- **superseded** — replaced by a newer capture; retained for history.

`draft_001` is entirely **draft**. No value advances until the corresponding
party (AutoCAD designer for product specifics; machinist for verification)
provides real data.
