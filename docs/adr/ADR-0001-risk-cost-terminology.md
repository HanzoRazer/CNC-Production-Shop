# ADR-0001 — Two distinct "risked cost" models

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Texas Guitar Exchange (developer)

## Context

Two different cost-uplift formulas existed in the codebase under overlapping
"risked cost" vocabulary, producing different numbers from the same intent:

1. **Additive, four-factor** (`business/bids/calculator.py`):
   ```
   risked = base × (1 + (tool_wear + manufacturing_contingency
                         + business_overhead + engineering_recovery) / 100)
   ```
2. **Multiplicative, two-factor** (`business/calculators/cnc_electricity.py`):
   ```
   risked_job_cost = direct × (1 + scrap/100) × (1 + contingency/100)
   ```

Sharing the name invites cross-wiring and mis-priced quotes.

## Decision

Both formulas are legitimate but represent **different concepts** and will be
named distinctly.

- **Canonical commercial bid model** = the **additive four-factor** model.
  This is the source of truth for `BidV1` and customer quote pricing.
  Canonical name: **`risked_bid_cost`**.
- **Manufacturing / job-cost adjustment model** = the **multiplicative** model.
  Useful for shop-floor job-cost estimation, **not** final bid pricing.
  Canonical name: **`manufacturing_adjusted_cost`** (a.k.a. `adjusted_job_cost`).

Neither formula is deleted.

## Consequences

- Final customer pricing always derives from `risked_bid_cost` (additive).
- The multiplicative model is documented as a manufacturing adjustment and must
  not be used as the bid risked cost.

## Migration (deferred — separate atomic commit)

Renaming the `risked_job_cost` field is a **breaking contract change**: the
identifier appears in `schemas/cnc_cost/quote_scenario_v1.schema.json`, five
committed fixtures, and three test files (26 references across 10 files).

Therefore the rename is scoped as its own migration:

1. Bump `quote_scenario_v1` → `quote_scenario_v2` with the renamed field.
2. Migrate the five `fixtures/cnc_cost/*.json` fixtures to v2.
3. Update `tests/business/test_cnc_*` references.
4. Keep a v1→v2 compatibility note.

Until that migration lands, the field name `risked_job_cost` is retained and
this ADR + a module docstring document its true meaning (non-breaking).
