# Vendored Smart Guitar outline sources

Reference geometry for `scripts/export_smart_guitar_dxf.py`, copied from the
`luthiers-toolbox` repository on 2026-08-01.

| File | Origin in `luthiers-toolbox` |
|---|---|
| `smart_guitar_front_v5.dxf` | `docs/archive/instrument_references/smart_guitar/smart_guitar_front_v5.dxf` |
| `smart_guitar_back_v5.dxf` | `docs/archive/instrument_references/smart_guitar/smart_guitar_back_v5.dxf` |
| `smart_guitar_back_trace_v1.json` | `services/api/app/instrument_geometry/body/traced_outlines/smart_guitar_back_v1.json` |

## Why these are vendored

The exporter previously read them through an absolute Windows path
(`C:/Users/thepr/Downloads/luthiers-toolbox/...`). That path exists on one
machine, so the exporter and its fifteen tests errored on every CI runner —
which is why the DXF suite was failing on the pull request while passing
locally. Copying ~58 KB of static reference geometry into the repo makes the
export reproducible anywhere, which is the same argument
`SMART-GUITAR-CAVITY-GEOMETRY-1` makes for deriving cavities instead of
transcribing them.

## Keeping them current

These are **copies, not the canon**. `luthiers-toolbox` remains the source of
truth for the body outline. To check this repo against a live checkout without
re-vendoring:

```bash
SG_GEOMETRY_SOURCE_DIR=/path/to/luthiers-toolbox/docs/archive/instrument_references/smart_guitar \
    python scripts/export_smart_guitar_dxf.py --source back_v5
```

The trace JSON lives in a different directory upstream, so an override pointing
at the DXF directory will not find it; copy an updated trace in directly.

Note that the outline is **not settled** — `CONF-TRACE-REGISTRATION` scopes the
trace to the silhouette and through-body voids only, and `SG-ELECTRONICS-BAY-V1`
deliberately carries no `body_position` for that reason. Re-vendor when the
upstream outline is revised, and re-run
`python scripts/validate_smart_guitar_geometry.py` afterwards.
