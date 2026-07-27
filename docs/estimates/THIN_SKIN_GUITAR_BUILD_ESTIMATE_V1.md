# Thin-Skin Guitar Build Estimate V1

Internal engineering document for **THIN-SKIN-GUITAR-BUILD-ESTIMATE-1**.

## Purpose

Establish a governed, reproducible **internal direct manufacturing cost** for one
laminated thin-skin electric guitar:

```text
PRODUCT-THIN-SKIN-ELECTRIC-GUITAR-BASELINE-V1
```

This is **not** a customer quote, proposal, or commercial price. It stops at
direct manufacturing cost. Overhead allocation, warranty reserve, fulfilment,
wholesale, dealer margin, DTC price, and MSRP belong to later governed layers.

The hypothesis under test is not "can inexpensive body materials reduce cost".
It is:

> Can the thin-skin architecture reduce total saleable-unit cost by lowering
> machining, finishing, handling, rework, and touch labor?

Cheap skins prove nothing if lamination cleanup, edge repair, sanding, and
finishing add labor hours. The record is therefore structured so that
lamination, finishing, equipment occupancy, and process yield cannot hide
inside a generic labor number.

## Relationship to V1 solid-body records

The V1 solid-body records are **retained and still validate**. They are not
superseded; they become comparison variant C.

| Layer | Solid body (V1) | Thin skin (V2) |
|---|---|---|
| Product | `PRODUCT-CNC-ELECTRIC-GUITAR-BASELINE-V1` | `PRODUCT-THIN-SKIN-ELECTRIC-GUITAR-BASELINE-V1` |
| Input schema | `guitar_estimate_input_v1` | `thin_skin_estimate_input_v2` |
| Estimate schema | `guitar_build_estimate_v1` | `thin_skin_build_estimate_v2` |
| Calculator | `business/estimates/guitar.py` | `business/estimates/guitar_v2.py` |
| Validator | `scripts/validate_guitar_estimates.py` | `scripts/validate_thin_skin_estimates.py` |
| Cost categories | 10 | 18 |
| Time fields per operation | 4 | 6 |
| Risk mechanisms | 1 (scrap) | 2 (scrap + yield reserve) |

## Governed variants

One product identity, two governed estimate inputs. Core material is an
**input**, not a product invariant, so architectures can be compared without
forking the product.

```text
VARIANT-A-PLYWOOD-CORE   hardboard/HDF skins over a birch plywood core
VARIANT-B-POPLAR-CORE    hardboard/HDF skins over a solid poplar core
```

The two variants differ in exactly two governed places, and a validator check
enforces it: the `core_material` input line, and the WBS 1100 core-preparation
times. The second difference is not padding — a dimensional poplar core must be
edge-jointed and glued up before it can be laminated, and plywood does not.

## Calculated results

Quantity 1, USD, draft confidence throughout.

| Category | Variant A | Variant B |
|---|---:|---:|
| core_material_cost | 10.56 | 23.10 |
| skin_material_cost | 3.38 | 3.38 |
| adhesive_and_lamination_consumables | 4.70 | 4.70 |
| neck_and_fretboard_cost | 63.25 | 63.25 |
| hardware_cost | 49.10 | 49.10 |
| electronics_cost | 72.00 | 72.00 |
| finish_material_cost | 53.50 | 53.50 |
| other_consumables_cost | 25.80 | 25.80 |
| machine_time_cost | 46.35 | 46.35 |
| equipment_occupancy_cost | 12.13 | 12.13 |
| lamination_labor_cost | 29.23 | 29.23 |
| direct_build_labor_cost | 119.32 | 133.22 |
| finishing_labor_cost | 75.23 | 75.23 |
| assembly_labor_cost | 52.70 | 52.70 |
| setup_and_inspection_cost | 36.89 | 36.89 |
| material_scrap_allowance | 5.61 | 6.23 |
| process_rework_and_yield_reserve | 41.14 | 43.78 |
| **total_direct_manufacturing_cost** | **700.89** | **730.59** |

Process behaviour, reported independently of cost:

| Measure | Variant A | Variant B |
|---|---:|---:|
| Operator labor | 654 min (10.9 h) | 683 min (11.4 h) |
| CNC runtime | 96 min | 96 min |
| Equipment occupancy | 3,050 min (50.8 h) | 3,050 min |
| Elapsed wait | 315 min | 555 min |
| Rework | 0 min (see below) | 0 min |

## Findings

These follow from the numbers above. Every one is an engineering estimate, not
evidence.

**1. This is a labor problem, not a materials problem.** Labor is $313.38 of
Variant A's $700.89 (45%). Core and skin material together are $13.94 (2.0%).
Halving body material cost moves the unit cost by under $7. Removing one hour
of touch labor moves it by $28.75. Any further work aimed at the material line
is optimising the smallest term in the equation.

**2. Equipment occupancy is a throughput constraint, not a cost.** 50.8 hours
of press, booth, and rack occupancy cost $12.13, or 1.7% of the total. Now that
occupancy is priced rather than assumed, the conclusion is that pricing it was
not where the money was. Its real consequence is work-in-process and floor
space, which are overhead questions deferred to `GUITAR-FULL-UNIT-COST-1`.

**3. The thin-skin architecture currently costs more than it saves — provisional.**
Architecture-specific labor (lamination 2100–2500 at 61 min, edge and skin
cleanup at 3600 for 26 min, edge sealing at 5100 for 22 min) totals 109 minutes,
or $52.23. Variant A's entire core-plus-skin-plus-adhesive material cost is
$18.64. A conventional solid poplar body blank would run roughly $28–32 on the
same assumptions, so the material saving is on the order of $10–13 against a
labor addition of about $52.

That is the central hypothesis failing at draft confidence, by roughly $40 per
unit. **It is not yet a conclusion.** Variant C has not been computed under the
V2 contract, and every figure on both sides is an engineering estimate. It does
establish what `THIN-SKIN-ARCHITECTURE-COMPARISON-1` must actually settle, and
which numbers decide it: edge cleanup at 3600, edge sealing at 5100, and total
lamination touch time.

**4. The shop-machined neck is the largest cost in the build and is unrelated to
the hypothesis.** WBS 4100–4400 carry 154 minutes of labor ($73.79), 52 minutes
of CNC ($25.11), and $63.25 of material — about $162 per unit. Fret preparation
alone (4200) is 78 minutes, the single largest operation in the build. A
purchased complete fretted neck at value tier would plausibly land near
$90–140, making it cost-neutral to cheaper while removing the highest-variance
hand operation in the process.

The governed product definition specifies `shop_machined`, and this estimate
models that faithfully. Flagged for review: sourcing the neck is a larger and
more certain lever than anything the thin-skin architecture offers, and it is
independent of the core-material question.

**5. Labor is roughly double the controlled-production target.** 10.9 hours
against a 4–6 hour target. Most of the gap is quantity 1 (setup absorbed by a
single unit) and hand fretwork. Batch allocation is deferred to
`THIN-SKIN-BATCH-COSTING-1`.

**6. Variant B's labor penalty exceeds its material penalty.** The poplar core
costs $12.54 more in material but $13.90 more in core-preparation labor. The
correct comparison metric is cost per saleable completed unit, not raw body
material cost, and this is a small worked example of why. A test asserts this
relationship so a future edit cannot erase it silently.

## Costing policy

### Labor

```text
Base labor rate:    $23.00/hr
Load factor:             1.25
Loaded labor rate:  $28.75/hr
```

The $45–$75/hour mature composite shop rate discussed in the production analysis
is a **different concept** — a future burdened commercial shop rate — and is
deliberately not substituted here. Both the validator and the test suite fail if
45, 72, or 75 appears in any rate-like field.

### Machine

```text
$28.97 per machine hour   MACHINE-COST-BASIS-BCM2030CA-ATC-V1
```

The $72/hour commercial machine rate is not used.

### Equipment occupancy

Three new governed cost-basis records, each assembled as
`burden + electricity + consumables`, mirroring the machine cost-basis contract:

| Equipment | Rate | Occupancy | Cost |
|---|---:|---:|---:|
| `EQUIPMENT-VACUUM-PRESS-V1` | $1.38/hr | 118 min | $2.71 |
| `EQUIPMENT-SPRAY-BOOTH-V1` | $4.22/hr | 52 min | $3.66 |
| `EQUIPMENT-CURE-RACK-V1` | $0.12/hr | 2,880 min | $5.76 |

All three are `draft`. Every component is an unconfirmed engineering estimate
built from assumed capital cost and assumed annual utilisation. None carries an
owner-confirmation artifact, and a test enforces that nothing claims
`owner_confirmed` without supporting references.

### Risk: two mechanisms, no compounding

```text
material_scrap_allowance          5%  x eligible stock materials
process_rework_and_yield_reserve  10% x eligible conversion cost
```

10% is the documented midpoint of the 8–15% draft range for a new laminated
process. Reserve base for Variant A:

```text
eligible materials       129.14
machine time              46.35
equipment occupancy       12.13
body-process labor       223.78
-----------------------------
reserve base             411.40   x 10% = 41.14
```

Excluded from both bases: pickups, bridge, tuners, prewired harness, strings,
packaging. **The material scrap allowance is excluded from the reserve base**, so
the two mechanisms never compound. The validator recomputes both bases and fails
if either is assembled differently.

Labor eligibility is carried per operation by `reserve_eligible`, not by a
category sweep, so adding a high-value purchased part can never silently inflate
the reserve. Lamination, direct build, and finishing labor are eligible;
assembly, setup, and inspection are not.

**Deviation from the sprint brief, stated explicitly.** The brief excluded a
"completed purchased neck" from the reserve base. No purchased neck exists in
this bill — the neck is shop-machined — so the neck blank, fretboard, and neck
machining labor are treated as **reserve-eligible**. A shop-machined neck
carries genuine yield risk (fret slot placement, blowout, truss channel errors)
that a purchased neck would not. If the neck is later sourced complete, it
should move to the exclusion list.

### Rework and the double-count rule

`rework_minutes` exists on every operation but is **0.0 throughout**. No
measured rework data exists yet, and process risk is carried once, by the
reserve.

When `THIN-SKIN-PILOT-CAPTURE-1` supplies real rework times, populating
`rework_minutes` **requires reducing the reserve rate at the same time**, or
process risk is counted twice. The validator enforces this: it fails if any
operation books rework minutes while the reserve is still above 5%.

## Work breakdown

Every WBS leaf carries exactly one operation record, including leaves with no
time, so the breakdown stays auditable. 39 leaves, asserted by test.

```text
1000  Material receiving and preparation   1100 1200 1300
2000  Lamination                           2100 2200 2300 2400 2500
3000  CNC body manufacturing               3100 3200 3300 3400 3500 3600
4000  Neck and fretwork                    4100 4200 4300 4400
5000  Finish                               5100 5200 5300 5400 5500 5600
6000  Electronics and hardware             6100 6200 6300 6400
7000  Final assembly                       7100 7200 7300
8000  Setup and quality control            8100 8200 8300 8400 8500
9000  Packaging readiness                  9100 9200 9300
```

## Time model

Six fields per operation, because a single labor number hides the behaviour the
estimate exists to reveal:

```text
setup_minutes                operator present, job preparation
operator_touch_minutes       operator present, process labor
machine_runtime_minutes      CNC time attributable to the job
equipment_occupancy_minutes  non-CNC equipment held by the job
elapsed_wait_minutes         calendar time consuming neither
rework_minutes               operator present, in-process correction
```

Labor is `setup + operator_touch + rework`. Machine runtime, equipment
occupancy, and elapsed wait never become labor and may overlap freely:

```text
Press occupancy  != labor      2400: 90 min occupancy,  0 min labor
Cure time        != labor      5500: 2880 min occupancy, 6 min labor
CNC runtime      != labor      4100: 52 min runtime,    30 min labor
Finish drying    != labor      5400: 120 min wait,      30 min labor
```

## What is excluded

- Customer price, margin, markup, commissions, discounts
- Overhead allocation, warranty reserve, fulfilment cost
- Wholesale, dealer, DTC, and MSRP pricing
- Packaging materials (packing *labor* at 9300 is included)
- Commercial machine rate ($72/hr) and burdened shop rate ($45–75/hr)
- Batch setup allocation (quantity is 1)
- Variant C, conventional solid body, under the V2 contract

Schema `additionalProperties: false` plus validator and test scans on both field
names and rate values enforce these boundaries.

## Draft assumptions requiring evidence

Nothing in this estimate is a vendor quote or a measured shop trial.

| Area | Current basis | Needed next |
|---|---|---|
| Core and skin sheet prices, yield per sheet | engineering_estimate | Vendor quote + nesting trial |
| Adhesive consumption per body | engineering_estimate | Measured usage |
| Hardware, electronics, neck stock | catalog_price | Vendor quote |
| Finish material consumption | engineering_estimate | Measured usage |
| All 39 operation durations | engineering_estimate | Measured shop trials |
| Lamination cycle and press occupancy | engineering_estimate | Timed pilot cycle |
| Equipment capital and utilisation | engineering_estimate | Owner confirmation |
| Labor rate | inherited_shop_default | Owner confirmation |
| 5% scrap eligibility | engineering_estimate | Pilot yield data |
| 10% yield reserve | engineering_estimate | Pilot defect and disposition data |
| Chamber geometry and body weight | not yet dimensioned | Design + pilot measurement |
| Bond durability, neck-pocket bearing strength | unvalidated | Structural trial |

## Pilot capture requirements

`THIN-SKIN-PILOT-CAPTURE-1` must record, **per serial-numbered unit**, not as
averages: core and skin material issued, adhesive used, material discarded, CNC
setup and runtime, operator touch time, press occupancy, bonding labor, edge
cleanup time, sanding time, finish touch and elapsed time, assembly time, setup
time, rework time, bond/edge/finish/alignment defects, final body weight, and
saleable/rework/scrap disposition.

Individual-unit data must be preserved. Averages hide the process variation and
the worst cases, which are what decide whether this architecture is viable.

## Sprint sequence

```text
THIN-SKIN-GUITAR-BUILD-ESTIMATE-1     <- this sprint, complete at draft
        v
THIN-SKIN-PILOT-CAPTURE-1             per-unit time, material, defect, yield
        v
THIN-SKIN-ARCHITECTURE-COMPARISON-1   plywood vs poplar vs conventional body
        v
THIN-SKIN-BATCH-COSTING-1             quantities 1, 5, 10, 25
        v
GUITAR-FULL-UNIT-COST-1               overhead, warranty, fulfilment
        v
GUITAR-CHANNEL-PRICING-1              DTC, wholesale, MSRP scenarios
        v
GUITAR-BID-GENERATION-1               governed commercial bid records
```

## Reproducing

```bash
python scripts/validate_thin_skin_estimates.py
pytest tests/estimates/test_thin_skin_build_estimate.py
```

The validator recomputes both estimates from their inputs, re-derives every
equipment hour rate from its components, checks that the 18th category equals
the sum of the other 17, verifies both risk bases, and enforces that the two
variants differ only where this document says they do.
