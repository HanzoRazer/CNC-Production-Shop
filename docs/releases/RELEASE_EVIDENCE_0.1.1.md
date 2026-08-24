# Release evidence — 0.1.1

Status: `release_candidate`

This is human-facing evidence for `REL-CNC-0.1.1`. It does not replace
`fixtures/releases/release_manifest_0.1.1.json`.

## Identity

```text
distribution: cnc-production-shop
version:      0.1.1
release ID:   REL-CNC-0.1.1
tag:          v0.1.1 (not created until post-merge verification)
```

## Source

```text
version-freeze commit: aeff825f3492bc96db5869044255a3bc9f47345f
base main:             182406fcab7ea92dc534e8d47780e588e67d9b8d
```

The canonical tag will point at the verified post-merge evidence-bearing
commit, not the pre-merge branch tip.

## Artifact

```text
wheel:             cnc_production_shop-0.1.1-py3-none-any.whl
SHA-256:           687871562bf49d34605f75630f03109fc4f05b1b8a828072403460fe43c26a00
duplicate members: no (64 unique members)
stored in git:     no (hash only; rebuild from the tagged commit)
```

See `dist-release/SHA256SUMS`.

## Version parity (editable install after version freeze)

Recorded locally during candidate preparation. Fresh-venv proof is repeated
from the exact merge SHA before tagging.

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

## Publication

```text
GitHub Release: no
PyPI / index:   no
```

## Witness tag

`msme-001-foundation-original` is preserved and is not a distribution release.
