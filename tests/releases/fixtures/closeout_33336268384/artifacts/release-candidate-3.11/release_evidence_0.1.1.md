# Release candidate evidence — 0.1.1

RESULT: BLOCKED

## Identity

```text
distribution: cnc-production-shop
version:      0.1.1
release ID:   REL-CNC-0.1.1
state:        release_candidate
```

## Source

```text
commit SHA:   18125a09bfc1d1cf9a8470ce32ccd07970e0e9fb
Python:       3.11
```

## Workflow

```text
run:          github-actions run 33336268384 python 3.11
test summary: pytest passed on Python 3.11 (CI)
CI summary:   github-actions run 33336268384 python 3.11
```

## Artifact

```text
wheel:        cnc_production_shop-0.1.1-py3-none-any.whl
SHA-256:      687871562bf49d34605f75630f03109fc4f05b1b8a828072403460fe43c26a00
duplicates:   []
```

## Verification

```text
version authority: PASS
tests:             PASS
wheel build:       PASS
fresh install:     PASS
package parity:    PASS
MSME resources:    PASS
MSME CLI:          PASS
MSME_API_VERSION:  0.2.0
manifest:          PASS
```

## Tag eligibility

```text
canonical tag: v0.1.1
eligibility:   FAIL
```

## Blockers

- canonical tag v0.1.1 already exists

BLOCKED means this candidate must not be tagged or published on the
basis of this run.
