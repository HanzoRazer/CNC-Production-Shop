# Neck make-or-buy — gap closure

**Dev Order:** `NECK-MAKE-OR-BUY-GAP-CLOSURE-1`
**Base:** `a33c531`, containing the accepted `cec758c` and `ae20bf1`
**Status:** draft. **This authorizes no decision.**

> This analysis is a draft engineering cost model. It does not authorize neck
> production, supplier selection, purchasing, or commercial pricing.

Extends the accepted `NECK-MAKE-OR-BUY-BATCH-COSTING-1` model additively. Read
[`NECK_MAKE_OR_BUY_V1.md`](NECK_MAKE_OR_BUY_V1.md) first; it carries the
batching result, the three corrections, and the back-calculated manufacturing
bracket, none of which changed here.

---

## Purpose

The accepted sprint answered its question and left five things unpoliced:

```
the two governed records had no schema, so their shape was unenforced
three of the four completion states had no buy side at all
the runtime sweep only ever descended from an unverified baseline
runtime had no yield axis
the back-calculation's separation from make-cost was a comment, not a test
```

Nothing accepted was rewritten. Every previously computed cell still recomputes
to the same number: `M4` scarf at quantity 20 is **$187.88**, batching is worth
**$9.34** per neck against a **$9.58** ceiling, and the manufacturing bracket
still runs **$51.30–$96.19**.

## What the buy side was missing

The accepted model held two purchase references and both sat at `M4`. So the
like-for-like rule — the rule that exists because this model once costed an
unfinished neck against a finished purchased one — governed exactly one of four
possible comparisons and was unenforced on the other three.

`B1`–`B4` are now defined, and the mapping is a constraint rather than a
convention: `BuyCompletionState` refuses to construct with the wrong
`make_equivalent`, and `assert_like_for_like` raises on any `Mx`/`By` pair where
`x != y`.

## A delivered price is not a delivered cost

Each buy state retains shop work that buying does not remove — someone opens the
box, measures the neck against the pocket it has to sit in, and corrects what
does not fit.

| Buy state | Retained | Cost | Heaviest retained item |
|---|---:|---:|---|
| `B1` machined only | 27 min | $12.94 | heel and truss channel correction, 12 min |
| `B2` board installed | 29 min | $13.90 | heel plus board levelling, 14 min |
| `B3` complete fretted | 33 min | $15.81 | corrective fretwork, 18 min |
| `B4` production-ready | 35 min | $16.77 | correcting a *finished* neck, 20 min |

Retained cost **rises** with completion state, which reads backwards until you
see what is counted. This is not the work needed to finish the neck — the
comparison is like-for-like, so that work is on neither side. It is inspection
and correction, and a more complete neck presents more surface to inspect and is
dearer to correct once there is finish on it.

That is why the competitive ceiling sits **below** the in-house cost rather than
equal to it.

## Break-even delivered prices

```
maximum compatible delivered purchase price
  = in-house cost per saleable neck − retained buy-side completion cost
```

| | Make cost | Retained | **Ceiling** |
|---|---:|---:|---:|
| `M1` ↔ `B1` | $48.93 | $12.94 | **$35.99** |
| `M2` ↔ `B2` | $100.37 | $13.90 | **$86.47** |
| `M3` ↔ `B3` | $150.23 | $15.81 | **$134.42** |
| `M4` ↔ `B4` | $187.88 | $16.77 | **$171.11** |

Scarf construction, AAA ebony board, 90% yield, quantity 20.

## The four thresholds

Positive means buying at that price costs more than building, so **make** is
lower cost.

| | $90 | $100 | $120 | $140 |
|---|---:|---:|---:|---:|
| `M1` ↔ `B1` | +54.01 M | +64.01 M | +84.01 M | +104.01 M |
| `M2` ↔ `B2` | +3.53 M | +13.53 M | +33.53 M | +53.53 M |
| `M3` ↔ `B3` | −44.42 B | −34.42 B | −14.42 B | **+5.58 M** |
| `M4` ↔ `B4` | −81.11 B | −71.11 B | −51.11 B | −31.11 B |

**This is the finding the accepted sprint could not see.** It reported that
buying wins at a complete neck, which is true and is the bottom row. With all
four states present, the crossover is locatable: in-house wins decisively at
`M1` and `M2`, and loses at `M4` against every price in the range. It flips
between `M2` and `M3`.

What sits between `M2` and `M3` is fretwork — 78 minutes, the largest single
labour operation in the neck. The accepted sprint named fretwork the dominant
cost driver by sensitivity. The completion-state ladder now shows the same thing
structurally: **the shop is competitive at making neck blanks and uncompetitive
at fretting them.**

`M2` clears $90 by only $3.53, so that row is not a margin to rely on. It is
inside the error of two operations that have never been measured.

## Not one row is actionable

Every comparison above reports `commercially_actionable: false`.

The Smart Guitar is headless with a locking clamp nut at a 628.65 mm scale.
Every purchase reference on record — the $45 import, the $125 boutique neck, the
$197 retail listing — is a conventional neck with a headstock and a standard
nut. No supplier of a compatible neck has been identified at **any** completion
state, so all four buy states carry:

```
compatible_supplier_identified: false
purchase_price_status: unresolved
```

The arithmetic is still computed, because a threshold the shop cannot act on
today is still the number it would need the day a source appeared. But the
verdict and the actionability are separate fields on purpose. Collapsing them is
how a threshold becomes mistaken for a quote.

The existing conventional-neck references are **not** attached to `B1`–`B4` as
substitutes. They remain in `buy_references`, as references.

## The runtime sweep was one-sided

The accepted grid was `52, 45, 40, 30, 20` — every point at or below a baseline
that the machine profile explicitly disclaims and that nobody has timed. A grid
that only descends from an unverified assumption can only ever show that
assumption proving favourable.

The grid is now the union of the accepted points and the specified ones, and it
brackets the baseline:

| Runtime | Cost | |
|---:|---:|---|
| 20 min | $170.71 | better |
| 30 min | $176.08 | better |
| 40 min | $181.44 | better |
| 45 min | $184.13 | better |
| **52 min** | **$187.88** | **baseline, unverified** |
| 60 min | $192.17 | worse |
| 75 min | $200.22 | worse |
| 90 min | $208.27 | worse |

**$37.56 of spread across the domain, and half of it was previously invisible.**
If the DDCSV controller is decelerating through a 3D surfacing path worse than
assumed, the real figure is to the right of the baseline, and a `M4` neck is
above $200. Runtime remains the largest single unmeasured lever and it now cuts
both ways.

Sweep grids, both unioned, sorted, deduplicated:

```
machine minutes   20  30  40  45  52  60  75  90
fretwork minutes  20  25  30  35  40  45  50  55  60  65  78  90
```

Every accepted point survives. The fretboard-price axis is retained; it remains
internally valid and was not removed for going unmentioned in a later handoff.

## Matrices

Three, all at `M4` and quantity 20, each recording what it held constant so
every cell recomputes:

| Matrix | Axes | Cells |
|---|---|---:|
| `FRETBOARD_X_FRETWORK_QTY20_M4` | fretboard price × fretwork minutes | 60 |
| `FRETWORK_X_YIELD_QTY20_M4` | yield × fretwork minutes | 60 |
| `RUNTIME_X_YIELD_QTY20_M4` | yield × runtime | 40 |

The third is new. Runtime previously had no yield axis, so the model could not
show what a worse runtime does to a batch that also loses necks — which is the
compounding case, since a rejected neck consumed its machine time and does not
give it back.

## Batch quantity, unchanged

| Quantity | `M4` cost per saleable |
|---:|---:|
| 1 | $196.98 |
| 5 | $189.32 |
| 10 | $188.36 |
| 20 | $187.88 |
| 40 | $187.64 |

Still $9.34 across the whole range against a $9.58 ceiling, because still only
`OP-4100` carries any setup. Batching was never the lever.

## The back-calculation, and why it stayed

The Dev Order that commissioned the accepted sprint forbade retail and margin
fields. A later accepted commit, `ae20bf1`, deliberately added them: a $197.31
shelf price, four channel routes, and the $51.30–$96.19 manufacturing bracket
that showed the owner's sub-$75 instinct was right and the model was what was
wrong.

Enforcing the ban literally would have deleted that. The ruling on this sprint
was to keep it and enforce **separation** instead, which is a stronger claim and
so needs a stronger proof than a comment:

- The scenario and result schemas are closed, `additionalProperties: false`, so
  no commercial field can enter any make-or-buy section. The back-calculation is
  a titled, separately-classified subtree within each.
- The commercial-vocabulary scan covers every section except that subtree.
- **The separation is proven by perturbation.** The validator triples the anchor
  retail price, rewrites all twelve channel margins, doubles every shop-position
  figure, rebuilds, and requires that not one value in `make_scenarios`,
  `batching_effect`, `buy_references`, `buy_completion_states`, `thresholds`,
  `threshold_findings` or `sensitivity` has moved. It also requires that the
  perturbation *did* change the back-calculation, so the test cannot pass
  vacuously.

A test that asserts a section is unused, by making it wrong and checking nothing
downstream notices, is worth more than any amount of documentation saying so.

## Governed contracts

```
schemas/estimates/neck_make_or_buy_scenario_v1.schema.json   NeckMakeOrBuyScenarioV1
schemas/estimates/neck_make_or_buy_result_v1.schema.json     NeckMakeOrBuyResultV1
```

Both strict. The accepted fixtures satisfy them with **no** restructuring; two
places where the schema had to accommodate the record rather than the reverse:

- `operations[].note` is optional. `OP-4400` carries none, and inventing prose
  for an accepted operation is a worse fix than an optional field.
- `materials[]` requires exactly one of `cost` or `cost_source`. The accepted
  record has both kinds — swept materials name a source, fixed ones carry a
  price — and `oneOf` states that properly instead of loosening both.

`fretboard_options[].cost` is nullable and `confidence` admits `unknown`,
because the swept budget fretboard genuinely has no source and no price. A
placeholder there would become the answer.

## Evidence gaps

Everything on the accepted list still stands, and this sprint adds:

```
retained receiving-inspection time                   draft, 5 min, never measured
retained dimensional-verification time               draft, 10 min, never measured
retained corrective-fitting time by state            draft, 12-20 min, never measured
corrective fretwork on a bought fretted neck         draft, 18 min; likely the most
                                                     understated figure in the model
whether ANY supplier makes a headless clamp-nut
  neck at 628.65 mm, at any completion state         UNKNOWN, and it gates the
                                                     entire buy side
machine runtime above the baseline                    now modelled, still unmeasured
```

The retained-cost estimates are the weakest new numbers here. They move the
ceilings by $13–$17, which is enough to matter at `M2` where the margin is
$3.53.

## Decision boundary

Draft throughout. `decision_authorized: false` on the result and on every
finding. No supplier is selected, no purchase order exists, no retail,
wholesale, margin or MSRP field appears in any make-or-buy section.

The honest summary is narrower than the arithmetic looks. **The shop is
competitive at making neck blanks and uncompetitive at fretting them, the
crossover sits between `M2` and `M3`, and none of it is actionable because no
purchased neck fits this instrument at any completion state.** The next useful
measurement is not a cost model. It is a phone call establishing whether a
compatible neck can be bought at all, and one timed CNC run to settle whether 52
minutes is real.
