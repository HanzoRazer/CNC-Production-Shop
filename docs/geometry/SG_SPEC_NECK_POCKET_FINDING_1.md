# SG-SPEC-NECK-POCKET-FINDING-1

**Raised:** 2026-09-07 · **Closed:** 2026-09-08 · **Status: NOT SENT — do not dispatch**

**`sg-spec` is not part of the neck-pocket authority chain.** Ruled 2026-09-08.
It was searched because this project's notes suggested it might hold cavity
authority; the search found nothing relevant. No query goes to its maintainer
and **no cross-repo work is opened from this finding.**

This document was drafted as an outbound query and is retained as the evidence
record instead. Nothing in it was sent. Nothing in `sg-spec` was modified.

Two things in it survive the closure, for different reasons:

- **The `bass_chamber` constraint defect is real** and is the most actionable
  repository defect in this area once the CAD sprint returns its geometry —
  see *The finding* below. It is not repaired now, and specifically not with
  repository arithmetic. The next CAD release supplies the actual neck-pocket /
  fretboard / pickup relationship first.
- **The framing correction is worth keeping visible.** The first draft said
  `sg-spec` "was believed to be" one of two disagreeing neck-pocket sources.
  That was false. **No document in CNC-Production-Shop has ever named `sg-spec`
  in connection with the neck pocket** — the claim named *neither* source.
  `sg-spec` was checked, not accused. Corrected before anything was sent, which
  is the only reason it never left the repository with that error in it.

Separately and explicitly **out of scope for this branch**: the reported
uncommitted edits to quarantined files in `sg-spec` and its stale "canon:
22 frets" note. Those are worth its owner checking and are a different incident.
Do not fold them in here.

The text below was written to be pasted whole into an issue or a coding agent.
It is preserved verbatim, unsent, in case the decision is ever revisited.

---

## The query

````text
# sg-spec: a cavity constraint depends on neck geometry this repo does not define

## The finding

`smart_guitar_cavity_map.json` — `bass_chamber.constraints`:

    "Maintain rim_min from body edge",
    "Do not cross centerline spine",
    "Clear of neck pocket projection"        <-- this one

The first two resolve to quantified values in the same file:

    "rim_min_in": 0.5,          "rim_min_mm": 12.7
    "spine_width_min_in": 1.5,  "spine_width_min_mm": 38.1

The third resolves to nothing. sg-spec appears to define no neck pocket — no
dimensions, no position, no projection footprint. So a back-face chamber carries
a clearance requirement against geometry the repo does not own, and the
constraint cannot be evaluated from sg-spec alone.

Constraints in that file are free text, and most are unquantified:

      2  Maintain rim_min from body edge          <- resolves
      2  Do not cross centerline spine            <- resolves
      1  Clear of neck pocket projection          <- does not
      1  Must not overlap pod keep-out zone       <- does not
      1  Must clear treble chamber                <- does not
      1  Avoid tailpiece stud mounting zones      <- does not
      1  Stability risk - consider web bridges    <- not a constraint
      1  Shallower if structural concerns         <- not a constraint

This is your repo's issue regardless of anything below.

## Why a downstream project went looking

For context, not as an accusation. CNC-Production-Shop's generated CAD dimension
sheet carried the line:

    | Neck pocket | Two sources disagree on size and position. |

It named neither source. Tracing it: the sentence was born as a hardcoded string
literal on 2026-07-28, replaced nothing, and the previous version of that sheet
did not mention the neck pocket at all. It has since been removed.

**It was not merely unsupported — it was contradicted.** The Smart Guitar neck
pocket appears with dimensions in exactly two documents, both in a third repo
(luthiers-toolbox), and they agree to the decimal:

    specs/smart_guitar_v1.json                76.2 x 55.9 x 15.9  r6.35  x=0  y=53.3
    docs/archive/.../SMART_GUITAR_V1_CNC_HANDOFF.md
                                              76.2 x 55.9 x 15.9         x=0  y=53.3

The handoff derives from the spec and says so, so that is one source and a
document about it, not two sources. **sg-spec was never named as either.** It
was searched because it is recorded elsewhere as canonical for cavity
dimensions.

That is why the only live question for you is the negative below, plus what your
own constraint means.

## Confirm the negative from inside

I could not find neck-pocket geometry in sg-spec. That is a negative produced
from outside your repo, which is weaker than one produced from inside it.

Reproduce what I ran:

    grep -rniE "neck_pocket|neck pocket|pickup_route|neck_pickup" . \
      --include=*.json --include=*.py --include=*.md

One hit: the constraint string above.

What I could NOT check:

- Only `.json`, `.py`, `.md`. The repo also has 21 `.ts`, 1 `.yml`, 1 `.toml`
  and 4 `.txt` files that were never searched.
- Working tree of one local clone. No git history, no other branches, no tags.
- No generated or build artifacts, nothing under `node_modules`.
- `contracts/`, `agentic-ai/` and `sg_spec/` were read only where grep hit them.

To close the history gap:

    git log --all -S "neck_pocket" --oneline
    git log --all -S "neck pocket" --oneline

## Questions

1. Does sg-spec define neck-pocket geometry anywhere — current, historical, or
   generated? If it ever did, when was it removed and by what change?
2. What is "neck pocket projection" meant to denote, and against what source was
   `bass_chamber` intended to be checked?
3. Is this constraint evaluated by anything — a validator, a test, a build step
   — or has it only ever been prose?
4. Are the other unquantified constraints in the same position: real rules with
   no evaluable definition?

**2, 3 and 4 are the ones that matter**, and they are answerable from inside
sg-spec alone. 1 is now largely a formality: nothing downstream depends on
sg-spec having neck-pocket geometry, so a plain "never had any" closes it.

## Please do NOT

- Do not add neck-pocket dimensions to satisfy the constraint. The Smart Guitar
  is in an active CAD sprint that owns that geometry, and the model is not under
  version control in any repo. Inventing a number here creates exactly the false
  authority this started from.
- Do not delete the constraint if it encodes a real rule. If it does, the fix is
  to name what owns it — which, on current evidence, is the CAD sprint and not a
  file — rather than to drop the requirement.
````

---

## What each answer changes here

Hypothetical — no answer is being sought. Retained because it records what the
closure is betting on: that the third row is not the world we are in.

| Answer to Q1 | Consequence for this repository |
|---|---|
| Never had neck-pocket geometry | Expected. Confirms the cleanup. No change. |
| Had it, removed at some point | Interesting but not load-bearing — the claim named no source, so a removal in sg-spec cannot have been what it referred to. Worth a footnote. |
| Has it, somewhere I could not reach | The only outcome that costs anything: a third dimensioned source would exist, and whether it agrees with the 76.2 × 55.9 × 15.9 pair decides whether "sources disagree" was accidentally true. `SMART-GUITAR-GEOMETRY-AUTHORITY-CLEANUP-1` would need revising before submittal. |

Q2 matters independently of all three. If `bass_chamber` was ever meant to be
checked against a real projection, that is a structural constraint going
unevaluated, and it belongs in collision work rather than in a prose list.

## Response

**None, and none expected.** The query was closed unsent on 2026-09-08. The
table above is retained only because its third row describes the one outcome
that would have cost something, and recording a road not taken is cheaper than
re-deriving why it was not taken.
