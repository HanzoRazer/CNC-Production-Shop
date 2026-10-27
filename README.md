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

The repository produces one Python distribution: `cnc-production-shop`.

```bash
pip install -e .
python -c "import business.bids.calculator"   # verifies the engine is installed
```

Subsystems may carry separately named API/contract versions (for example
`musical_spatial_mapping.MSME_API_VERSION`), but a subpackage `__version__`
reflects the containing distribution when it is exposed.

Version authority, release lifecycle, and the changelog:

- `docs/governance/VERSIONING_POLICY.md`
- `docs/governance/RELEASE_POLICY.md`
- `CHANGELOG.md`

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

## Draft job quote

From a source checkout, one command validates a job request, recomputes an
existing estimate, builds an internal bid and summary, and writes a customer
draft proposal. It does not approve a price, send the proposal, or release
manufacturing. The direct manufacturing cost and the draft quote price are
different numbers: the price applies the caller-supplied target margin to that
cost. A 30% target margin is not a 30% markup.

Dispatch uses the validated request `record_version` and `estimate_input_contract`.
The fixture filename does not select the contract. Quantity is 1 and currency
is USD. Additional bid-level tool wear, contingency, overhead, and engineering
recovery percentages are zero. Schemas are read from the checkout. The command
is not a wheel-only operation.

| Request | Version | Estimate contract | Workflow / mapping | Bid | Summary | Proposal |
|---------|---------|-------------------|--------------------|-----|---------|----------|
| Solid-body demo | `1.0.0` | `guitar_estimate_input_v1` | `1.0.0` | `BidV1` | `bid_summary_v1` | `proposal_v1` |
| Thin-skin A or B | `2.0.0` | `thin_skin_estimate_input_v2` | `2.0.0` | `bid_v2` `2.0.0` | `bid_summary_v1` | `proposal_v1` |

Workflow and mapping versions are contract lineage, not a distribution version.
Unknown versions, unknown contracts, and V1/V2 cross-pairs are refused before
the estimate is loaded.

```bash
python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_demo_v1.json \
  --output-dir exports/jobs/cnc-job-quote-demo-001

python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_thin_skin_a_v2.json \
  --output-dir exports/jobs/thin-skin-a-quote-001

python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_thin_skin_b_v2.json \
  --output-dir exports/jobs/thin-skin-b-quote-001
```

The three job files are synthetic `INTERNAL-DEMO` requests. They are not
customer orders and not price approvals. The solid-body request names the
guitar estimate input, product, machine profile, and machine cost basis. Each
thin-skin request also names that product's definition, the same machine pair,
and the vacuum-press, spray-booth, and cure-rack equipment profile and cost
basis. Those dependencies must already be in the checkout. The workflow does
not invent rates or discover a latest file.

`BidV2` keeps equipment occupancy and the process rework and yield reserve as
their own base-cost amounts. They are not relabelled as CNC time, labor,
tooling, or overhead. The customer proposal is still `ProposalV1`: notes,
assumptions, rates, margin, reserve, time, and risk stay in `internal/`.

`--root` is the source workspace. Every referenced record resolves under that
root. The output directory must be new, inside the root, and not a symlink.
An existing destination is refused, including one created concurrently during
publication. Publication uses Windows' non-replacing rename, Linux
`renameat2(RENAME_NOREPLACE)`, or macOS `renamex_np(RENAME_EXCL)`. If the
platform/filesystem cannot provide exclusive rename, the command fails without
publishing a partial packet.

| Path | Audience |
|------|----------|
| `customer/proposal.json`, `customer/proposal.md` | Draft for later customer delivery. The command does not send it. |
| `internal/` | Job request, estimate, bid, bid summary, cost report, and captured source bytes. |
| `manifest.json` | Lineage, digests, and the category mapping. A digest proves byte identity, not an approved price. |

Exit 0 writes a validated draft packet. Exit 2 refuses invalid input or an
existing destination and writes no packet. Exit 1 is an output or internal
failure.

A packet can remain under `exports/jobs/` when running the full suite. The
commercial-boundary test still scans `fixtures/proposals/` and `exports/`,
including every job-packet `customer/` directory. It excludes the private
`internal/` subtree beneath a packet manifest, which correctly retains its
technical cost details. Customer drafts require separate price
approval and manufacturing release in both their JSON and Markdown next steps.
The orders are `docs/orders/CNC-JOB-QUOTE-WORKFLOW-001.md` and
`docs/orders/CNC-JOB-QUOTE-WORKFLOW-002.md`.

## License

MIT License — Copyright © 2026 Texas Guitar Exchange LLC
