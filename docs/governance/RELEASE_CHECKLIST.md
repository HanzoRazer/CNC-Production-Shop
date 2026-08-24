# Release Checklist

Human-executable. This file does not run code.

Use with `docs/governance/RELEASE_POLICY.md` and
`scripts/release/check_release_readiness.py`.

A checked box is evidence only when the named artifact or log exists.

## Source state

- [ ] Working tree clean (`git status` empty)
- [ ] `local main` equals `origin/main` if releasing from main
- [ ] Proposed commit SHA recorded

## Version state

- [ ] `[project].version` is the intended `MAJOR.MINOR.PATCH` (no `v` prefix)
- [ ] Readiness inspected the release tree (`--root`), not another checkout's env
- [ ] All packaged `__version__` values bind to `cnc_version.distribution_version()`
- [ ] `MSME_API_VERSION` recorded independently from that tree
- [ ] Schema / quote / artifact revisions were not silently retargeted

## Test state

- [ ] `python -m pytest` passed
- [ ] `python -m ruff check .` passed
- [ ] `python -m mypy musical_spatial_mapping --strict` passed
- [ ] `python -m mypy business --ignore-missing-imports` passed
- [ ] All repository validators passed

## CI

- [ ] Python 3.11 CI green on the release commit
- [ ] Python 3.12 CI green on the release commit

## Wheel build

- [ ] `python -m pip wheel . --no-deps -w dist-test` succeeded
- [ ] Wheel filename is `cnc_production_shop-<version>-py3-none-any.whl`
- [ ] No duplicate archive members

## Fresh install

- [ ] Fresh venv installed the wheel
- [ ] Imports resolve to `site-packages`, not the checkout
- [ ] MSME resources load
- [ ] MSME CLI runs
- [ ] All seven packaged `__version__` values equal wheel metadata

## Artifact metadata

- [ ] Wheel `Name` is `cnc-production-shop`
- [ ] Wheel `Version` equals `[project].version`
- [ ] SHA-256 recorded as `sha256:` + 64 hex

## Release notes

- [ ] `CHANGELOG.md` has a section for this version, or Unreleased was
      frozen into that section
- [ ] Notes report `MSME_API_VERSION` when MSME changed
- [ ] Notes do not invent absent categories
- [ ] `scripts/release/render_release_notes.py` output reviewed

## Tag verification

- [ ] Canonical tag `v<version>` did not already exist
- [ ] After authorization: tag points at the verified release commit
- [ ] Witness tags (including `msme-001-foundation-original`) were not
      rewritten or deleted

## Post-release verification

- [ ] Release manifest validates
- [ ] Tagged tree rebuilds the same wheel hash
- [ ] Fresh install from the tagged artifact succeeds
- [ ] Publication steps occurred only if an execution order authorized them

If any required item is missing: `RELEASED: no`.
