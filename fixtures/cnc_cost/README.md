# CNC Cost Scenario Fixtures

Governed quote scenario fixtures for CNC job costing validation.

## Purpose

These fixtures exercise the `business.calculators.cnc_electricity` module against realistic shop scenarios. They provide:

1. Repeatable validation of the cost calculation kernel
2. Authoritative input/output pairs for regression testing
3. Foundation for future CLI demo, quote export, and bid generation

## Scenarios

| Fixture | Description | Quantity | Margin |
|---------|-------------|----------|--------|
| `guitar_body_routing_v1.json` | Single Les Paul body from mahogany | 1 | 35% |
| `pickguard_batch_v1.json` | Custom acrylic pickguards | 10 | 40% |
| `fretboard_slotting_v1.json` | Precision ebony fretboards | 5 | 45% |
| `hardwood_panel_routing_v1.json` | Furniture panels (non-lutherie) | 4 | 30% |
| `machine_burden_sensitivity_v1.json` | Low vs high utilization comparison | 1 | 35% |

## Percentage Convention

All percentage fields use **percentage POINTS**, not decimals:

```
target_margin_pct = 35.0   means 35%
scrap_pct = 5.0            means 5%
contingency_pct = 10.0     means 10%
payroll_burden_pct = 25.0  means 25%
```

## Schema

Fixtures validate against `schemas/cnc_cost/quote_scenario_v1.schema.json`.

## Important Notes

1. **These are internal costing scenarios, not customer bid documents.**
2. Fixture inputs are authoritative — expected outputs are derived from inputs.
3. The kernel uses target-margin pricing: `quote = cost / (1 - margin/100)`
4. Do not confuse with Eco-Loom manufacturing fixtures (`fixtures/eco_loom/`).

## Shop Defaults (Texas Guitar Exchange)

```
operator_wage_per_hour = 23.0
payroll_burden_pct = 25.0
machine_burden_rate_per_hour = 19.0  (at 1200 hrs/yr utilization)
electricity_cost_per_hour = 1.97
tooling_cost_per_hour = 8.0
```
