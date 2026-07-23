# Guitar Build Estimate Baseline V1

Internal engineering document for **GUITAR-BUILD-ESTIMATE-1**.

## Purpose

Establish a governed, reproducible **internal manufacturing cost** for one
CNC-built solid-body electric guitar:

```text
PRODUCT-CNC-ELECTRIC-GUITAR-BASELINE-V1
```

This is **not** a customer quote, proposal, or commercial price.

## What is included

- Wood blanks (body, neck, fingerboard)
- Purchased hardware and electronics (catalog/draft)
- Consumables, including finish materials
- CNC machine time from governed BCM cost basis (~$28.97/hr technical)
- Loaded shop labor at $28.75/hr (`$23 × 1.25`)
- Finishing labor (separate from finish materials)
- Setup and inspection labor
- Explicit 5% scrap on listed wood + low-value consumables only

## What is excluded

- Customer price, markup, margin, commissions, discounts
- Shipping / packaging materials
- Commercial machine billing rate ($72/hr)
- Acoustic / carved-top / set-neck complexity
- Vendor-confirmed quotes (not yet collected)

## Draft assumptions requiring evidence

| Area | Current basis | Needed next |
|------|---------------|-------------|
| Wood blank prices | `catalog_price` / draft | Vendor quote |
| Hardware / electronics | `catalog_price` / draft | Vendor quote |
| Finish materials | `engineering_estimate` / draft | Measured usage |
| Operation durations | `engineering_estimate` / draft | Measured shop trials |
| Labor rate | `inherited_shop_default` / draft | Owner confirmation |
| Scrap 5% eligibility | `engineering_estimate` / draft | Yield history |

## Machine cost boundary

Machine time uses:

- `MACHINE-BCM2030CA-ATC-V1`
- `MACHINE-COST-BASIS-BCM2030CA-ATC-V1`

Rate role: `internal_technical_cost` only.

## Calculated baseline total

See `fixtures/estimates/guitar/cnc_electric_guitar_baseline_estimate_v1.json`
for recomputable category totals and:

```text
total_direct_manufacturing_cost
```

Any commercial pricing belongs in a later sprint after evidence collection.
