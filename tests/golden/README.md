# `tests/golden/` — protected behavioral spec (MSME-001)

This directory is the **canonical behavioral specification** for the Musical
Spatial Mapping Engine. Files here are golden vectors: stable, implementation-
independent input→output records that the engine must reproduce exactly.

**Protected directory.** Changing a golden vector is changing the spec, not the
test. A vector may only change with a deliberate, reviewed decision — never to make
a failing implementation pass.

**Status:** empty in Phases 1–2 (contracts + geometry). The first vector file,
`msme_v1_vectors.json` (≥20 vectors covering fretted, fretless, and course-based
mapping), lands in **Phase 6** once candidate generation, scoring, selection, and
annotation exist to produce mapping results.
