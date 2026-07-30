# Neck make-or-buy — batch and sensitivity model

**Dev Order:** `NECK-MAKE-OR-BUY-BATCH-COSTING-1`
**Status:** draft. **This authorizes no decision.**

Generated from `fixtures/estimates/neck/neck_make_or_buy_input_v1.json` by
`scripts/build_neck_make_or_buy.py`, recomputed in full by
`scripts/validate_neck_make_or_buy.py`.

---

## The question, and what changed while answering it

The sprint was called to test a hypothesis: a router that holds twenty necks in
one setup might make in-house neck production competitive with buying.

**It does not, and the reason is that there was never much setup to spread.**
Of the seven operations in a complete neck, exactly one carries any setup at
all — `OP-4100`, at 18 minutes. Everything else is hand work that recurs per
neck no matter how many are on the table.

```
batching benefit, quantity 1 to 40      $9.34 per neck
ceiling at infinite quantity            $9.58 per neck
```

The 2000 × 3000 mm table was never the constraint.

## Two things the sprint found instead

**The construction decision is worth more than the router.** One-piece with an
angled headstock takes 2.464 board feet; a scarf joint with a stacked heel
takes 0.995. At $8/BF that is **$11.75 per neck** — larger than everything
batching can offer, and it is a design choice, not a process one.

**The model was costing an unfinished neck.** Neck finishing does not exist
anywhere in the accepted V2 estimate — every finish operation in it is body
work — and neither does fretboard installation. Both were added here as draft
operations. Their absence meant every prior comparison against a *finished*
purchased neck was not like-for-like.

## Result

Scarf construction, AAA ebony board, 90% yield, quantity 20, complete neck:

```
materials                 $ 66.90
setup                     $  0.48
touch labour              $ 91.04
machine                   $ 27.90
equipment occupancy       $  1.56
                          ───────
cost per SALEABLE neck    $187.88

time split, per saleable neck
  labour                    191.0 min   costed at the loaded rate
  machine                    57.8 min   costed at the machine rate
  equipment occupancy        22.2 min   costed at the spray-booth rate
  elapsed wait              316.7 min   costs NOTHING
```

That 316.7 minutes of calendar time is the fix described below. It was
previously charged as operator labour.

Against the two purchase references:

| Reference | Catalog | Comparable? |
|---|---:|---|
| Boutique finished neck | $125.00 | Yes — quality-matched |
| Budget import | $45.00 | **No** — composite board against AAA ebony, and the owner judges the workmanship may not pass inspection |

**Exactly one combination in the swept grid reaches $125**, and it is extreme:

```
fretwork min:        78       65       55       45       35       25
fretboard $29    187.88   180.96   175.64   170.31   164.99   159.66
fretboard $20    177.88   170.96   165.64   160.31   154.99   149.66
fretboard $15    172.33   165.40   160.08   154.76   149.43   144.11
fretboard $10    166.77   159.85   154.52   149.20   143.88   138.55
fretboard $ 5    161.21   154.29   148.97   143.64   138.32   133.00
```

Only $5 board stock with an **87% fretwork cut** clears it. Nothing else in the
grid does. The result is not "in-house cannot compete" so much as "in-house
competes only under assumptions nobody has measured."

## Three corrections on the record

This model was wrong three times before it was right, and the sequence is kept
rather than tidied away.

**A mid-sprint table showed a $10 fretboard plus a 31% fretwork cut beating
$125.** It was computed before `OP-4150` and `OP-4500` existed, so it costed an
unfinished neck against a finished purchased one — the precise error the
like-for-like rule exists to prevent.

**The corrected model then charged cure time as labour.** `NeckOperation`
carried only setup, touch and machine, dropping the `elapsed_wait_minutes` and
`equipment_occupancy_minutes` fields that are the entire point of the V2
six-field model. Clamp and cure time had nowhere to go, so 29 minutes per neck
of glue drying and finish curing were billed at $28.75/hr. Fixing it took the
complete neck from $201.76 to $187.88.

**And the retail listing was misread as a benchmark.** A $197 Mighty Mite neck
at a retailer contains the manufacturer's, distributor's and retailer's
margins. Comparing it to a manufacturing cost and calling the agreement
vindication was a category error. The relevant comparison is the maker's cost,
plausibly $60-100, which says a commercial manufacturer builds an equivalent
neck for roughly half what this model shows.

## What would overturn this

Not batching, and not the router. The conclusion rests on two operations that
have **never been measured**:

- fretboard installation, 10 touch minutes plus 45 of clamp time, draft
- neck finishing, 15 touch minutes plus 20 of booth and 240 of cure, draft
- **the 52 machine minutes**, carried from the V2 baseline and never checked

That last one is the biggest single lever and the easiest to settle. At the
governed machine rate it is $27.90 of a $187.88 neck, and the machine profile
explicitly disclaims feeds and speeds, so nothing in the repo supports it. The
BCM 2030CA runs a DDCSV 1.1 controller, which is budget-class: a neck profile
is 3D surfacing across thousands of short segments, and limited block-lookahead
makes a machine decelerate at every one. If 52 minutes is real, the controller
is a likelier cause than the toolpath. Run one program and time it.

## Cost allocation

Batch setup divides by **saleable** units, not units started. A neck that fails
inspection consumed its material, its machine time and its share of the fixture
setup, and the necks that survive carry it. Costs are reported both ways so the
loss is visible rather than absorbed.

The 90% baseline yield is an engineering estimate with no measurement behind
it. It is set below 1.0 deliberately: assuming perfect yield would divide fixed
cost by units that were never sold.

## Known limitations

- **`OP-1300` is impure.** It stages body hardware and electronics as well as
  the neck, and is counted wholly to the neck. This overstates neck cost, and
  therefore biases *against* the make case. Splitting an accepted operation was
  outside this sprint.
- **Scarf-joint labour is not modelled.** The construction saves $11.75 of
  timber but adds a scarf cut and a glue-up that no operation covers.
- **Machine runtime stays per neck.** The 52 minutes were not reinterpreted as
  a nested batch runtime; doing so without measured evidence would assume the
  answer.
- **No purchased neck fits the specified instrument.** The Smart Guitar is
  headless with a locking clamp nut, 24 frets, 628.65 mm scale. Every purchase
  reference here — $45 import, $125 boutique, $197 retail listing — is a
  conventional neck with a headstock and a standard nut. The make-or-buy
  question as posed has no buy side for this product.
- **The import's landed cost is unknown.** Freight, duty under HTS 9209 plus
  any current Section 301 line, incoming inspection, corrective fretwork and
  reject rate are all absent. A modelled structure suggests they roughly double
  the catalog figure, but nothing in it is measured, so no value is recorded.

## Evidence gaps for pilot capture

```
fretboard installation time          draft, 22 min, never measured
neck finishing time                  draft, 32 min, never measured
scarf cut and glue-up labour         not modelled at all
neck reject rate and yield           draft, 90%, no history
machine runtime per neck            held at 52 min, UNVERIFIED, largest lever
batch fixture setup                 held at 18 min for 20 necks = 54 sec each,
                                    which is implausible for T-slot fixturing
                                    and probably understates the setup badly
purchased neck landed cost           every component unknown
purchased neck reject rate           unknown
heel-to-pocket fit variation         unquantified, and specific to a CNC shop
```

## Decision boundary

This is a draft engineering estimate. It does not authorize product selection,
supplier selection, production investment, or pricing of any kind. Every
finding carries `decision_authorized: false`.

The honest summary is narrow: **buying wins on cost at a complete neck, and
batching was never the lever that could change that.** Whether cost is the
deciding factor — against consistency, lead time, supply risk and the control
of making your own — is not a question this model answers.
