# Release evidence — 0.1.1

Status: `released`

This is human-facing evidence for `REL-CNC-0.1.1`. It does not replace
`fixtures/releases/release_manifest_0.1.1.json`.

## Identity

```text
distribution: cnc-production-shop
version:      0.1.1
release ID:   REL-CNC-0.1.1
tag:          v0.1.1
```

## Source

```text
tagged commit (peeled): b143ed22e9215f56bca3ed184131852dd033b3f5
tag object:             b2509cf0417839638ae24c69d72ccefb6f14c011
PR:                     https://github.com/HanzoRazer/CNC-Production-Shop/pull/9
```

`v0.1.1` is an annotated tag. The peeled commit is the merge commit of PR #9,
not the pre-merge branch tip.

## Artifact

```text
wheel:             cnc_production_shop-0.1.1-py3-none-any.whl
SHA-256:           687871562bf49d34605f75630f03109fc4f05b1b8a828072403460fe43c26a00
duplicate members: no (64 unique members)
stored in git:     no (hash only; rebuild from the tagged commit)
```

Rebuild from merge SHA `b143ed2` produced the same hash as the RC record.

See `dist-release/SHA256SUMS`.

## Version parity (fresh venv after tag)

```text
cam_assist:                0.1.1
business:                  0.1.1
parametric:                0.1.1
fretboard:                 0.1.1
materials:                 0.1.1
acoustic:                  0.1.1
musical_spatial_mapping:   0.1.1
MSME_API_VERSION:          0.2.0
```

`cam-assist status` reports `CAM Assist v0.1.1 — Ready`.

## CI

```text
Python 3.11 / 3.12: https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/32782431215
```

## Publication

```text
GitHub Release: no
PyPI / index:   no
```

## Witness tag

`msme-001-foundation-original` is preserved and is not a distribution release.
