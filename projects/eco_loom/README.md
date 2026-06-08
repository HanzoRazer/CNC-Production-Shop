# ECO-LOOM Project Capture

Customer opportunity intake and assumption governance for the Eco-Loom project.

## Status

```
DRAFT — Awaiting customer information
```

## Purpose

This directory captures all known, estimated, and unknown information about the Eco-Loom opportunity in a governed, auditable format.

This is **not** a quote.
This is **not** a bid.
This is **not** a cost calculation.

This is the structured project record that feeds:

```
Project Capture
      ↓
Manufacturing Assumptions
      ↓
Cost Engine
      ↓
Quote Export
      ↓
Bid Package
```

## Files

| File | Purpose |
|------|---------|
| `eco_loom_project_capture_v1.json` | Core project facts |
| `eco_loom_assumption_register_v1.json` | Tracked assumptions with provenance |
| `eco_loom_open_questions_v1.json` | Unresolved questions |
| `ECO_LOOM_VALUE_REGISTER.md` | Human-readable working sheet |

## Governance Rules

1. **Unknown is a valid state** — Never force completion with invented values
2. **Assumptions require provenance** — Every estimate must identify source, confidence, captured_by, date
3. **Customer facts are immutable** — Changes create new revisions, not overwrites

## Relationship to Manufacturing Fixtures

Project capture is **upstream** of manufacturing fixtures:

```
projects/eco_loom/          ← Customer requirements, assumptions
fixtures/eco_loom/          ← Manufacturing data, operations, cycle times
```

Do not duplicate manufacturing data here.
Do not overwrite manufacturing fixtures from here.

## Open Questions

See `eco_loom_open_questions_v1.json` for current blockers.

## Validation

```bash
python scripts/validate_eco_loom_project.py
```
