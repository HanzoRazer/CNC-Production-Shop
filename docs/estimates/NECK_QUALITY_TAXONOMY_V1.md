# Neck defect-mode taxonomy — one yardstick for build and buy

**Dev Order:** `NECK-QUALITY-TAXONOMY-1`
**Status:** draft. **This authorizes no decision.**

Generated from `fixtures/estimates/neck/neck_defect_taxonomy_v1.json` by
`scripts/build_neck_quality.py`, recomputed in full by
`scripts/validate_neck_quality.py`.

---

## Why this exists

The make-or-buy model compared **$35** to **$187.88** as though they were two
prices on one object. They were prices on two different objects. The $35 necks
the owner holds are basswood — a body wood, janka **410** against khaya's
**1070** — and every hardware interface on a neck is a compression joint into
wood. The cost model had no field capable of noticing that.

So it costed a noun it could not define. This retires that noun. A neck is a
set of **defect modes** that a source either addresses or does not, and two
necks may be compared on cost only when their coverage matches.

## Three distinctions carry the model

**What eliminates a defect** decides what it costs to avoid:

| | Modes | Prevention cost | Prevention minutes |
|---|---:|---:|---:|
| `PROCESS` — machine precision removes it | 6 | **$0.00** | 0.0 |
| `SPECIFICATION` — the right material removes it | 6 | $31.97 | 0.0 |
| `LABOUR` — a person removes it | 5 | $54.14 | 113.0 |

**When it can be found** — `AT_RECEIPT` or `LATENT`. A latent defect emerges in
service, so no inspection catches it at purchase.

**Whether money can close it** — a non-remediable mode makes a comparison
**void, not expensive**. Softness is not a defect you can pay to remove.

## The answer to build-versus-buy

Both sources face the same 17 criteria. The decisive difference is not score:

```
source                    arrives at         criteria runnable
built here                MATERIAL_RECEIPT        17 / 17   (100%)
bought finished           M4                       3 / 17    (18%)
                                    cannot be run:  14
                     of those, also irrecoverable:   7
```

**Buying doesn't only cost less — it costs you the ability to check.** Fourteen
criteria describe stages that happened in another shop to another standard. The
truss channel is under a glued fretboard; the blank's moisture history is gone;
the fret slots were cut to somebody else's table. Those are not failures. They
are **blanks**, and recording a blank as a pass is exactly the assumption that
made $35 look like a bargain.

Seven of the fourteen are also irrecoverable: they can neither be found on
arrival nor fixed once they show themselves. On a finished instrument they come
back as warranty against **your** name.

### The same fault, priced on each side

`DEF-TRUSS-CHANNEL-CENTRING`, one fault, both routes:

```
EX-BUILD-CHANNEL-M1       measured at M1, before glue-up    SCRAP     loss $ 48.93
EX-BUY-CHANNEL-ESCAPED    no M1 exists to inspect at        SCRAP     loss $187.88
```

Identical verdict, **3.8× the loss**. Owning the early stages is worth money
even when the fault rate is identical on both sides. That mode is classified
latent and irremediable *only because a fretboard gets glued over it* — judged
at M1 it is neither.

## Where the comparison is refused

```
SRC-OBSERVED-IMPORT-35 against SRC-SHOP-CNC:  NOT COMPARABLE
7 modes cannot be closed by any spend:
  DEF-FRET-SLOT-POSITION      DEF-SPECIES-SUBSTITUTION
  DEF-GRAIN-RUNOUT            DEF-TRUSS-CHANNEL-CENTRING
  DEF-MOISTURE-CONTENT        DEF-TRUSS-ROD-GRADE
  DEF-WOOD-HARDNESS
```

No remediation figure is reported. A number there would say parity is
purchasable, and it is not.

## Two things this changes about the cost model

**Six modes are free.** They are removed because the machine indexes every
feature from one datum, not because anyone tried harder — and they include the
canonical forum complaint about bought necks, misaligned tuner peg holes. This
is quality an hourly rate cannot erode.

**113 of the shop's minutes are the product, not waste.** Against the 191
labour minutes in the cost model, the majority of the neck's labour content goes
to the five labour-eliminated modes, at $54.14. The import spends none of it.
The earlier finding that the shop must reach "23 labour minutes or $3.46/hr"
measured a gap against a product the shop is deliberately not building.

## What is measured here

**Nothing.** No neck has been built, no threshold has been set by the owner, and
`owner_confirmed` is `false` on all 17 criteria. The gate is a **structure
awaiting numbers**, not a specification.

The shop's 100% verifiability is an *opportunity*, not a result: owning the
stages means the checks **can** be run, not that they have been. Its full
coverage is intent. That row is the one most likely to be wrong, and the
validator refuses to let it be recorded as anything but assumed.

```
species identification        owner assessment from feel and weight, not lab
forum complaints              relayed by the owner; no survey, no thread cited
17 acceptance thresholds      draft proposals, 0 confirmed
6 criteria                    judged by method with no numeric threshold
shop coverage                 intent; no build session has occurred
stage value-at-risk           from the cost model, itself draft throughout
```

## Rebuild trigger

The first completed build sessions with captured times and recorded inspection
dispositions. At that point the gate stops being a structure and starts
producing the yield number the cost model currently assumes at 90% with nothing
behind it — **but only for modes that have a criterion.** An ungated mode cannot
appear in a yield figure, so the figure would undercount the ways a neck can be
wrong.

## Decision boundary

Draft engineering estimate. Authorizes no product selection, supplier selection,
production investment, or pricing. Every finding carries
`decision_authorized: false`.

The narrow summary: **held to one yardstick, the purchase is not a cheaper
version of the build — it is an object 82% of whose quality claims cannot be
checked, and 7 of whose defects no spend can repair.** Whether that matters
more than $150 is a judgement this model does not make.
