# Debt Gate Discovery Report

**Date:** 2026-06-11  
**Branch:** tech-debt-complexity-baseline-1  
**Purpose:** Identify origin of "debt-gates" tooling and "123 violations" before creating baseline

---

## Summary

**debt-gates tooling: NOT FOUND in this repository**  
**CBSP21 gate: NOT a complexity gate**  
**123 violations: origin unknown — not reproducible from this checkout**

---

## Search Results

### debt-gates / debt_gates

| Search | Result |
|--------|--------|
| `grep -r "debt-gates"` | No files found |
| `grep -r "debt_gates"` | No files found |
| `glob **/debt*` | No files found |
| `glob **/*gate*` | No files found |

**Conclusion:** No debt-gates tooling exists in this repository.

---

### CBSP21

| Search | Result |
|--------|--------|
| `grep -r "CBSP21"` | Found in TASKSPEC_CNC_PRODUCTION_SHOP.md |

**Context from TASKSPEC:**
```
Before modifying any file, scan at least 95 percent of it (CBSP21).
```

**Conclusion:** CBSP21 is a **process guideline** for developers ("read the file before editing"), NOT an automated complexity gate. It is not enforced by CI and does not produce violation counts.

---

### Complexity Tooling

| Tool | Search | Result |
|------|--------|--------|
| radon | `grep -r "radon"` | No files found |
| xenon | `grep -r "xenon"` | No files found |
| mccabe | `grep -r "mccabe"` | No files found |
| ruff C90 | `grep "C9" pyproject.toml` | No matches |
| cyclomatic | `grep -r "cyclomatic"` | No files found |
| cognitive | `grep -r "cognitive"` | No files found |
| complexity | `grep -r "complexity"` | No files found |

**Conclusion:** No complexity measurement tooling is installed or configured.

---

### CI Workflow

**File:** `.github/workflows/ci.yml`

**Checks present:**
- ruff check (lint only — no C90 complexity rules enabled)
- mypy business (type checking)
- pytest with coverage
- Fixture validators

**Checks NOT present:**
- No complexity gate
- No debt-gates step
- No radon/xenon/mccabe

---

### pyproject.toml Ruff Configuration

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

**C90 (complexity rules) NOT enabled.**

---

### Scripts

| Script | Purpose |
|--------|---------|
| validate_eco_loom_fixture.py | JSON schema validation |
| validate_eco_loom_project.py | JSON schema validation |
| validate_bid_fixtures.py | JSON schema validation |
| validate_bid_summaries.py | JSON schema validation |
| validate_proposals.py | JSON schema validation |
| export_proposal.py | Markdown export |

**No complexity measurement scripts exist.**

---

## Origin of "123 Violations"

The handoff referenced "123 existing violations" from a "debt-gates complexity report."

**This count cannot be reproduced from this repository because:**

1. No debt-gates tooling exists
2. No complexity measurement is configured
3. No CI step produces complexity violations
4. No script emits a violation count

**Possible origins:**

| Possibility | Likelihood |
|-------------|------------|
| Different repository | Possible |
| External CI system (not GitHub Actions) | Possible |
| Prior planning document with assumed tooling | Likely |
| Output from a tool run locally but never committed | Possible |

---

## Recommended Next Step

**Do NOT proceed with baseline document creation.**

The handoff assumes tooling that does not exist. Choose one of:

### Option A — Add Complexity Tooling First

1. Install radon or enable ruff C90 rules
2. Run complexity check to get actual violation count
3. THEN create baseline from real data

### Option B — Clarify Source

Identify where the "123 violations" originated:
- Which tool?
- Which repository?
- Which CI system?

### Option C — Descope Sprint

If debt-gates and complexity baselines are not relevant to CNC-Production-Shop, close this sprint as "not applicable" and proceed with ECO-LOOM-BID-REVISION-1.

---

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| debt-gates origin identified | NOT FOUND |
| CBSP21 origin identified | Found — process guideline, not gate |
| Toolchain documented | No complexity tooling present |
| 123 count reproducible | NO — no tool to produce it |
| Recommendation produced | YES — see above |

---

**Awaiting approval before Phase 1.**
