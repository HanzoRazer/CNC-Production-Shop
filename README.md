# CNC Production Shop

Manufacturing cost, bid, and proposal engine for a CNC lutherie shop.

## What this repository actually is

This repo is the **commercial engine** for Texas Guitar Exchange: it turns
captured job inputs into margin-correct bids and customer-facing proposals,
with internal economics kept separate from what the customer sees.

It is **not** a full design/CAM platform. Design, toolpath, materials, and
acoustic capabilities live in sibling repositories (see *Planned / External*).

## Implemented core

- **Manufacturing cost engine** (`business/calculators`) — electricity, loaded
  labor, machine burden, and simple job-cost calculators. Pure functions, no
  CAM/toolpath coupling.
- **Bid records** (`business/bids`) — internal `BidV1` with line items, cost
  basis, risk factors, and target-margin pricing.
- **Bid summaries** (`business/bids/summary.py`) — review-stage `BidSummaryV1`.
- **Proposal records** (`business/proposals`) — customer-facing `ProposalV1`,
  generated from a bid summary and **never** exposing margin, risk, or
  contingency.
- **Proposal / export path** — bid → summary → proposal, contract-backed by
  JSON schemas in `schemas/` and exercised by fixtures in `fixtures/`.

## Pricing invariant

Target-margin pricing, **not** markup:

```
quote_price = risked_cost / (1 - target_margin_pct / 100)
```

Percentages are **percentage points** (`30.0` = 30%), except `load_factor`,
which is a physical ratio (`0.65` = 65% of rated load). See
`docs/adr/ADR-0001-risk-cost-terminology.md` for the two distinct risk models.

## Planned / External (NOT implemented in this repository)

The following package stubs are intentionally empty. The real implementations
live in sibling repos or are future work. Do not assume local functionality.

| Stub | Status | Real home |
|------|--------|-----------|
| `parametric/` | External | `ltb-parametric-guitar` |
| `fretboard/`  | External | `fret_slot_strategy_package` |
| `materials/`  | Future / external | TBD |
| `acoustic/`   | Future / external | Luthier's ToolBox / related |
| `cam_assist/` | Reference | `CAM-Assist-Blueprint` |

## Requirements

- Python 3.11+
- See `pyproject.toml` for dependencies

## Installation

```bash
pip install -e .
python -c "import business.bids.calculator"   # verifies the engine is installed
```

## Development

```bash
pip install -e ".[dev]"
pytest                      # full suite
mypy business               # type-check the engine
ruff check .
```

## Verification

```bash
python scripts/validate_eco_loom_fixture.py
python scripts/validate_eco_loom_project.py
python scripts/validate_bid_fixtures.py
python scripts/validate_bid_summaries.py
python scripts/validate_proposals.py
```

## License

MIT License — Copyright © 2026 Texas Guitar Exchange LLC
