# SG-SPEC-NECK-POCKET-QUERY-1

**Raised:** 2026-09-07 · **To:** the `sg-spec` maintainer · **Status:** sent? no — drafted, awaiting dispatch
**Answer received:** — *(record it in "Response" below, do not edit the question)*

Outbound query, not a governed record. It exists because
`SMART-GUITAR-GEOMETRY-AUTHORITY-CLEANUP-1` removed a claim that `sg-spec` was
one of two disagreeing neck-pocket sources, and that removal rests on a
**negative search result produced from outside `sg-spec`**. A negative from
outside a repository is weaker than a negative from inside it, so the finding is
put to its maintainer before it is treated as settled.

`sg-spec` is not a working directory of this project and was not modified. Under
ruling 6 there was nothing to remove there in any case — see the cleanup doc.

The text below is written to be pasted whole into an issue, an email, or a
coding agent working in `sg-spec`. It deliberately states what the search could
not reach.

---

## The query

````text
# sg-spec: a cavity constraint depends on neck geometry this repo does not define

## Why you're getting this

A downstream repository (CNC-Production-Shop) carried a claim that Smart Guitar
neck-pocket geometry had "two disagreeing sources", one of which was believed to
be sg-spec. That claim was removed as unsupported: I could not find neck-pocket
geometry in sg-spec at all. Before that removal is final, I want you to confirm
or refute the negative from inside your own repo, and answer where the belief
came from.

## What I found

`smart_guitar_cavity_map.json` — `bass_chamber.constraints`:

    "Maintain rim_min from body edge",
    "Do not cross centerline spine",
    "Clear of neck pocket projection"        <-- this one

The first two resolve to quantified values in the same file:

    "rim_min_in": 0.5,          "rim_min_mm": 12.7
    "spine_width_min_in": 1.5,  "spine_width_min_mm": 38.1

The third does not resolve to anything. sg-spec appears to define no neck pocket
— no dimensions, no position, no projection footprint. So a back-face chamber
carries a clearance requirement against geometry the repo does not own, and the
constraint cannot be evaluated from sg-spec alone.

This matters beyond the one string: a reader who sees a neck-pocket constraint
stated with the same syntax as two quantified ones can reasonably infer sg-spec
knows where the neck pocket is. That inference is a plausible origin of the
downstream "sg-spec is a neck-pocket source" claim.

Constraints in that file are free text, and most are unquantified:

      2  Maintain rim_min from body edge          <- resolves
      2  Do not cross centerline spine            <- resolves
      1  Clear of neck pocket projection          <- does not
      1  Must not overlap pod keep-out zone       <- does not
      1  Must clear treble chamber                <- does not
      1  Avoid tailpiece stud mounting zones      <- does not
      1  Stability risk - consider web bridges    <- not a constraint
      1  Shallower if structural concerns         <- not a constraint

## Reproduce what I ran

    grep -rniE "neck_pocket|neck pocket|pickup_route|neck_pickup" . \
      --include=*.json --include=*.py --include=*.md

One hit, the constraint string above.

## What I could NOT check — please cover these

- Only `.json`, `.py`, `.md`. The repo also has 21 `.ts`, 1 `.yml`, 1 `.toml`
  and 4 `.txt` files that were never searched.
- Working tree of one local clone only. No git history, no other branches, no
  tags.
- No generated or build artifacts, and nothing under `node_modules`.
- I did not read `contracts/`, `agentic-ai/`, or `sg_spec/` beyond grep hits.

A clean way to close the history gap:

    git log --all -S "neck_pocket" --oneline
    git log --all -S "neck pocket" --oneline

## Questions I need answered

1. Does sg-spec define neck-pocket geometry anywhere — current, historical, or
   generated? If it ever did, when was it removed and by what change?
2. What is "neck pocket projection" meant to denote, and against what source was
   `bass_chamber` intended to be checked?
3. Is this constraint evaluated by anything — a validator, a test, a build step
   — or has it only ever been prose?
4. Are the other unquantified constraints in the same position: real rules with
   no evaluable definition?

## Please do NOT

- Do not add neck-pocket dimensions to satisfy the constraint. The Smart Guitar
  is in an active CAD sprint that owns that geometry; inventing a number here
  creates exactly the false authority this started from.
- Do not delete the constraint if it encodes a real rule. If it does, the fix is
  to name its owning source, not to remove the requirement.

If the answer to (1) is "never had any", say so plainly — that is a useful
result and closes the question.
````

---

## What each answer changes here

| Answer to Q1 | Consequence for this repository |
|---|---|
| Never had neck-pocket geometry | The cleanup stands as written. The "two sources" claim was wrong at every point in its life, and the neck pocket has exactly one historical source (`luthiers-toolbox`, withdrawn). |
| Had it, removed at some point | The claim was once true and went stale. The cleanup's wording needs a note saying when it stopped being true, and the removal commit becomes the citation. |
| Has it, somewhere I could not reach | The claim may be live. `SMART-GUITAR-GEOMETRY-AUTHORITY-CLEANUP-1` must be revised before submittal, and ruling 6's removal clause becomes live work in `sg-spec`. |

Q2 matters independently of Q1: if `bass_chamber` was ever meant to be checked
against a real projection, that is a structural constraint currently going
unevaluated, and it belongs in the collision work rather than in a prose list.

## Response

*Nothing received yet. Record the reply verbatim, with its date and author, and
then revise the cleanup if the third row above applies.*
