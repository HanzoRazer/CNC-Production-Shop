# `tests/golden/` — protected behavioral spec (MSME-001)

This directory is the **canonical behavioral specification** for the Musical
Spatial Mapping Engine. Files here are golden vectors: stable, implementation-
independent input→output records that the engine must reproduce exactly.

**Protected directory.** Changing a golden vector is changing the spec, not the
test. A vector may only change with a deliberate, reviewed decision — never to make
a failing implementation pass.

**Status:** populated. `msme_v1_vectors.json` holds **30 vectors** (MSME-002),
above the 20 this directory originally called for, covering fretted, fretless and
course-based mapping across all three shipped profiles and all three selection
statuses — `SELECTED`, `AMBIGUOUS` and `UNPLAYABLE`.

**Vectors are generated, never hand-written.** Inputs are declared in
`tests/musical_spatial_mapping/msme_vectors.py`; every expected output comes from
running the engine. Regenerate with:

```bash
python -m tests.musical_spatial_mapping.msme_vectors
```

Doing so and committing the result is how you change the spec — which is a
reviewed decision, not a way to make a failing implementation pass. The tests in
`test_serialization_result.py` rebuild every vector from its inputs and compare
structurally, so a drifted file fails rather than silently redefining correct.

**The file is deliberately environment-independent**: pure ASCII, no timestamps,
no paths, and byte-identical across Python versions. That last property is not
free — CPython 3.12 changed `sum()` to compensated summation for floats, which
made a score differ in its last bit between 3.11 and 3.14 until scoring moved to
`math.fsum`. Tests enforce all of these properties.
