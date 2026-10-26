# Task Spec — CNC Production Shop Headless Runs

Use for GREEN/YELLOW tasks you kick off at the desk and monitor via Remote Control.
Runs on your machine — dies on the 48h reboot, so keep it short enough to finish in one window,
or make it restartable (idempotent + reads its own SPRINT_LOG to resume).

---

## Current Sprint: CNC-COST-CORE

### CNC-COST-CORE-1 — Simple Electricity + Job Costing Foundation
**Status:** COMPLETE / LOCAL PASS

### CNC-COST-CORE-2 — Simple Quote Scenario Fixtures
**Status:** IN PROGRESS

---

## Quick Reference

| Field | Value |
|-------|-------|
| **Repo** | CNC-Production-Shop |
| **Path** | `C:\Users\thepr\Downloads\CNC-Production-Shop` |
| **Main branch** | main |
| **Test command** | `python -m pytest tests/ -v` |
| **Boundary rule** | `business/*` cannot import from `cam/*`, `rmos/*`, `saw_lab/*` |

---

## Task Template

```powershell
cd C:\Users\thepr\Downloads\CNC-Production-Shop
git checkout -b auto/[SPRINT-ID]/[task-slug]

claude -p "[TASK DESCRIPTION].
Before modifying any file, scan at least 95 percent of it (CBSP21).
Verify the live execution path before claiming any feature works (DEV_GUARDRAILS).
Append one factual line per step to docs/sprints/[SPRINT-ID]/SPRINT_LOG.md — observable facts only, no interpretation.
Commit atomically using the format type(scope): description.
Stop when: [STOP CONDITION]." `
  --allowedTools "[Read,Grep,Glob,Edit,Write,Bash]" `
  --max-turns [N] `
  --permission-mode plan
```

---

## Ready-to-Run: CNC-COST-CORE-2

**Task:** Add realistic quote scenario fixtures using Texas Guitar Exchange shop configuration.

**Color:** GREEN (pure test additions, no API/frontend)

**Stop condition:** All scenario tests pass AND no boundary violations

**Reversible:** Yes — branch + revert

```powershell
cd C:\Users\thepr\Downloads\CNC-Production-Shop
git checkout -b auto/CNC-COST-CORE-2/quote-scenarios

claude -p "Add realistic CNC quote scenario fixtures to tests/business/test_cnc_quote_scenarios.py.
Use Texas Guitar Exchange shop configuration:
- Operator wage: $23/hr, 25% payroll burden
- Machine: $60k amortized 5yr, 1200 billable hrs/yr
- Electricity: $0.13/kWh
- Equipment: 9kW spindle, 5.5kW vacuum, 3kW dust collector, 2kW compressor
- Tooling: $8/hr

Create fixtures for:
1. Single guitar body routing (~$400-450 quote)
2. Batch pickguards (10 units, per-unit pricing)
3. Premium fretboard slotting (45% margin)
4. Monthly electricity projection
5. Machine burden vs utilization comparison

Before modifying any file, scan at least 95 percent of it (CBSP21).
Run pytest after changes. Commit atomically.
Stop when: all scenario tests pass." `
  --allowedTools "Read,Grep,Glob,Edit,Write,Bash" `
  --max-turns 10 `
  --permission-mode plan
```

---

## Ready-to-Run: Future Sprints

### CNC-COST-CORE-3 — Quote Result Export (JSON/Dict)

**Disposition:** Not superseded by CNC-JOB-QUOTE-WORKFLOW-001. That order serializes existing estimate, bid, and proposal records. It does not add `SimpleJobCostResult.to_dict()` or `to_json()`.

```powershell
cd C:\Users\thepr\Downloads\CNC-Production-Shop
git checkout -b auto/CNC-COST-CORE-3/quote-export

claude -p "Add to_dict() and to_json() methods to SimpleJobCostResult for export.
Include all fields plus computed per-unit pricing when quantity provided.
Add tests proving JSON round-trip works.
Stop when: export tests pass." `
  --allowedTools "Read,Grep,Glob,Edit,Write,Bash" `
  --max-turns 5
```

### CNC-COST-CORE-4 — CLI Demo Script

**Disposition:** Not superseded by CNC-JOB-QUOTE-WORKFLOW-001. That order requires an explicit job request, machine profile, and cost basis. It does not add `scripts/demo_cnc_quote.py` or a shop-default-rate demo.

```powershell
cd C:\Users\thepr\Downloads\CNC-Production-Shop
git checkout -b auto/CNC-COST-CORE-4/cli-demo

claude -p "Create scripts/demo_cnc_quote.py using Click CLI.
Accept: material cost, runtime hours, operator hours, quantity.
Use Texas Guitar Exchange defaults for rates.
Output: formatted quote summary to stdout.
No API, no frontend, just CLI.
Stop when: python scripts/demo_cnc_quote.py --help works AND demo produces valid quote." `
  --allowedTools "Read,Grep,Glob,Edit,Write,Bash" `
  --max-turns 8
```

---

## Monitoring

- Start in `--permission-mode plan` for anything YELLOW — shows plan without touching files
- `--max-turns` is your cost + runaway fence. Mechanical task: 3–5. Analysis: 8–12.
- To monitor from phone: start session, then `/rc` inside it, scan QR
- When back at desk: review diff on branch before merging. Never auto-merge to main.

---

## Boundary Rules (from consultant)

```text
business/* CANNOT import from:
  - cam/*
  - rmos/*
  - saw_lab/*
  - business/estimator/*

Calculators must operate on numbers passed in, not introspect CAM/toolpaths.
```

---

## Percentage Convention

All percentage fields use **percentage POINTS**, not decimals:
- `target_margin_pct = 35.0` means 35%
- `scrap_pct = 5.0` means 5%
- `payroll_burden_pct = 25.0` means 25%

Exception: `load_factor` is physical ratio (0.65 = 65% load)

---

## Critical Formula

Target margin pricing (NOT markup):

```
quote_price = risked_cost / (1 - target_margin_pct / 100)
```

Proof test:
```
cost = 1000, margin = 30%
quote = 1428.57 ✓
NOT 1300.00 ✗
```

---

## Registered order: CNC-JOB-QUOTE-WORKFLOW-001

**Status:** Implemented on branch `cursor/cnc-job-quote-workflow-001-7f77`. Not merged, tagged, or released by this order.

**Date:** 2026-10-25

**Baseline:** `main` at `54a60932ca5ec4ab2d8f552df6b4fe8cba3f072c`

Source-checkout command for one draft packet: validate a `guitar_estimate_input_v1` job request, recompute the existing V1 guitar estimate, build `BidV1` and `BidSummaryV1`, and write a separate customer draft proposal. Quantity is 1, currency is USD, and additional bid-level risk, overhead, and recovery percentages are zero. The synthetic sample is `fixtures/jobs/cnc_job_quote_demo_v1.json` (`INTERNAL-DEMO`). Record and evidence: `docs/orders/CNC-JOB-QUOTE-WORKFLOW-001.md`.

CNC-COST-CORE-3 and CNC-COST-CORE-4 stay ready-to-run. This order does not replace them.
