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
touch labour              $106.48
machine                   $ 27.90
                          ───────
cost per neck started     $181.58
cost per SALEABLE neck    $201.76
yield loss                $ 20.18
```

Against the two purchase references:

| Reference | Catalog | Comparable? |
|---|---:|---|
| Boutique finished neck | $125.00 | Yes — quality-matched |
| Budget import | $45.00 | **No** — composite board against AAA ebony, and the owner judges the workmanship may not pass inspection |

**In-house does not reach $125 at any point in the swept grid.** Not at any
fretboard price, not at any fretwork time. The floor test says why:

```
free fretboard AND zero fretwork, everything else as specified
  materials  34.68   touch  64.95   machine  27.90   setup  0.48
  total     128.01   vs boutique 125.00      short by $3.01
```

Both levers at their physical limit still miss. That is a structural result,
not an artefact of the swept range.

## A correction on the record

An earlier table in this sprint showed a $10 fretboard plus a 31% fretwork
reduction beating $125. **That table was wrong.** It was computed before
`OP-4150` and `OP-4500` existed, so it costed an unfinished neck against a
finished purchased one — the precise error the Dev Order's like-for-like rule
was written to prevent. Adding the two missing operations and a 90% yield
closes the gap off entirely. The correction is preserved in
`FINDING-BOTH-LEVERS-INSUFFICIENT` rather than quietly overwritten.

## What would overturn this

Not batching, and not the router. The conclusion rests on two operations that
have **never been measured**:

- fretboard installation, 22 minutes, draft
- neck finishing, 32 minutes, draft

Together they are 54 of the 200 touch minutes in a complete neck. If they are
materially smaller in practice, the result moves. If they are larger, it
hardens. Nothing else in the model has that leverage.

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
nested batch runtime per neck        held at 52 min, unverified
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
