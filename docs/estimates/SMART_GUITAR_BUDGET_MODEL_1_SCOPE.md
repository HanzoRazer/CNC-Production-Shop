# SMART-GUITAR-BUDGET-MODEL-1 — Dev Order Scope

**Status:** proposed, not started
**Prerequisites:** `SMART-GUITAR-CAVITY-GEOMETRY-1` (complete), product records
split and ruled, `SUBASSEMBLY-SG-AUDIO-FRONTEND-V1` (concept)
**Product:** `PRODUCT-SMART-GUITAR-V1` only — hollow thin-skin, headless

## The question it answers

> Under explicit draft assumptions, can the Smart Guitar plausibly reach a
> cost that supports its intended price?

It is an **exploratory scenario model**. It calculates scenarios; it does not
approve a cost, a price, or production readiness. Everything it produces is
`exploratory` / `draft` until pilot evidence exists.

## What changed since this was first asked

The original request described four scenarios across two conflated products.
That has resolved into something narrower and more answerable:

| Then | Now |
|---|---|
| Two products conflated in one record | Two governed records; **only the Smart Guitar is in scope** |
| Body architecture undecided | Hollow thin-skin box, ruled and load-bearing |
| Electronics package assumed | Custom front-end board, specified as an RFI |
| Neck sourcing open | Shop-machined, ruled |
| Geometry unverified | Derived, with 20 conflicts recorded |

The Khaya is **out of scope**. It reverted to passive on 2026-07-27 and no
longer depends on the front-end board. It should get its own, much simpler
estimate later.

## Cost model layers

Strictly separated, because conflating them is what the earlier work kept
tripping over.

### Layer 1 — Direct manufacturing cost

Reuses the V2 thin-skin contract from `THIN-SKIN-GUITAR-BUILD-ESTIMATE-1`: the
six-field time model, equipment occupancy costed separately from CNC machine
time, and two non-compounding risk mechanisms. That contract already exists and
validates; this Dev Order supplies a new input fixture, not a new calculator.

New categories this product needs beyond the thin-skin baseline:

```text
smart_electronics_hardware_cost     Pi 5, storage, battery, BMS, fan, wiring
audio_frontend_board_cost           per-unit BOM + assembly, NOT the NRE
power_system_cost                   pack, charging, protection
firmware_provisioning_cost          image build, per-unit flashing, calibration
smart_system_assembly_cost          fitting, harnessing, cavity shielding
smart_system_test_cost              bench test, latency check, thermal check
```

### Layer 2 — Non-recurring cost

**Kept out of unit cost, on its own line.** The front-end board carries
schematic, layout, prototype runs, bring-up, MCU firmware and EMC
certification. With the Khaya now passive there is **no second product line to
amortise across**, so the whole of it lands on this instrument's volume — which
makes the amortisation assumption a headline output rather than a footnote.

### Layer 3 — Fully burdened cost

Facility, administration, insurance, depreciation, non-billable support,
packaging, warranty reserve, fulfilment. Explicit draft allocations, never
mixed into layer 1.

### Layer 4 — Channel scenarios

DTC, wholesale, MSRP as **calculated scenarios, not approved prices**.

## Scenario axes

The original four-scenario table collapses, because body and neck are now
ruled. What remains genuinely variable:

| Axis | Values |
|---|---|
| Core material | governed input, at least two candidates |
| Skin material and thickness | unselected |
| Pickup configuration | fluid — single coil, split humbucker, stacked noiseless |
| Front-end board | in-house NRE amortised, versus an external interface with no NRE |
| Volume | 1, 10, 50, 250 |

That last axis matters more than it looks: with NRE on one product line, unit
cost at volume 10 and volume 250 are different products commercially.

## Inputs required, and their state

| Input | State |
|---|---|
| Thin-skin V2 calculator and contract | **exists**, validates |
| Machine cost basis $28.97/hr, labour $28.75/hr | **exists**, governed |
| Cavity geometry and machining operations | **exists**, derived |
| Core species | **not selected** |
| Skin material and thickness | **not selected** |
| Finish system | **not selected** |
| Front-end board BOM | **not quoted** — the RFI exists to obtain it |
| Front-end NRE and certification | **not quoted** — same |
| Pi 5, battery, BMS, fan prices | catalog, needs refresh |
| Quantity and schedule | **not stated** — blocks the RFI too |

Six of eleven are unresolved. That is normal for a scenario model and is
exactly why it produces scenarios rather than a cost.

## Findings already banked that this model must carry

- **Void edge cost.** The through-body voids double finished edge length from
  1.51 m to 3.01 m, landing on WBS 3600 and 5100 — roughly 48 min and $23 per
  unit. Deliberate, and it must appear as a line rather than vanish into
  finishing labour.
- **Thin-skin weighs 48% of solid Khaya**, so body size is not weight-limited.
- **The shop-machined neck is the largest single line** in the thin-skin
  estimate at about $162, and fret preparation alone is the biggest operation
  in the build at 78 minutes.
- **The thin-skin estimate missed its own sub-$550 target** at $700.89, and
  that was before any smart electronics.

That last one deserves stating plainly at the top of the model: the passive
thin-skin instrument already exceeded its target, and this product adds roughly
$400 of electronics plus NRE on top.

## Out of scope

- Approved retail pricing, dealer contracts, warranty policy
- Exact annual overhead allocation
- The Khaya line
- Production scheduling, inventory, accounting integration
- Final component selection

## Governance

Everything `exploratory` / `draft`. Inputs may use `catalog_price`,
`engineering_estimate`, `inherited_shop_default`, `calculated`. Nothing uses
`vendor_quote`, `measured_trial` or `approved` without an artifact.

## Deliverables

```text
business/estimates/smart_guitar_scenarios.py     scenario calculator
schemas/estimates/smart_guitar_scenario_v1.schema.json
fixtures/estimates/smart_guitar/*.json           one input per scenario
scripts/validate_smart_guitar_budget.py
tests/estimates/test_smart_guitar_budget.py
docs/estimates/SMART_GUITAR_BUDGET_MODEL_V1.md
```

## The honest risk

The most likely output is that this instrument cannot reach a sensible price.
Roughly: $700 of thin-skin body and neck, plus $400 of electronics, plus a
custom board's BOM, plus NRE on a single line, before overhead. If that is what
the model says, it has done its job — the value is in learning it from a
spreadsheet rather than from a first article.

## Sequence

```text
SMART-GUITAR-BUDGET-MODEL-1          <- this
        v
SMART-GUITAR-PROTOTYPE-COST-CAPTURE-1
        v
SMART-GUITAR-BATCH-ECONOMICS-1
        v
SMART-GUITAR-OVERHEAD-ALLOCATION-1
        v
SMART-GUITAR-CHANNEL-PRICING-1
```

## What I need before starting

**Quantity and schedule.** They block the RFI as well, and without them the
volume axis is guesswork. Everything else the model can carry as a governed
assumption; those two it cannot invent.
