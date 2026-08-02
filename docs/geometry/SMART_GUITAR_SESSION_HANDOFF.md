# Smart Guitar — session handoff, 2026-07-28

Branch **`thin-skin-guitar-build-estimate-1`** — note the name; there is also a
stale `guitar-build-estimate-1` on origin sitting at an old commit. Pushed and
verified at `618a2d8`, working tree clean. 779 tests, seven validators green, ruff clean.

## Before anything technical

**Name the change contact on the RFI.** `SUBASSEMBLY-SG-AUDIO-FRONTEND-V1` has
been issued to designers and `document_control.change_contact` still says
nobody owns change requests. Twelve open questions are addressed to people with
nowhere to send answers, and a Q&A period is coming. Nothing else in the
document matters as much.

## Settled this session

| | |
|---|---|
| Electronics bay | `SG-ELECTRONICS-BAY-V1`, 210 × 125, ruled the **usable opening** |
| Placements | POD_PI 0/0 · POD_HAT 135/0 · BATT_A 0/67 · BATT_B 100/67 — bay-local |
| Pod separation | **42.0 mm**, up from 7.0 |
| GPIO ribbon | **150 mm**, spanning 125.0 header to header |
| Battery | 4 × 18650 in 2S2P, as **two** modules of 90 × 55 × 21 |
| Cutter | **6.35 mm** → every internal radius r3.175 |
| Bridge block | 110.8 × 115.0, needing **35.0 mm of solid** |
| NVMe | dropped; Pi boots from microSD |
| RFI | **Rev L**, issued, 12 open questions |

The ribbon was the finding that mattered. Each 40-pin header sits at its
board's centre, so the run is centre-to-centre — a 100 mm part was holding the
Pi 7 mm from the analog front end, and lengthening it to a stock 150 mm moved
the constraint to the bay.

## Open

Three conflicts: `CONF-PICKUP-TYPE` — the only one that is a *decision* —
`CONF-PICKUP-ROUTE-DIMS`, which follows from it, and `CONF-SINGLE-PICKUP-EMC`,
which needs the bench measurement in
`docs/geometry/SG_PICKUP_EMC_MOCKUP_PROCEDURE.md`. That procedure has never
been run.

Two things not tracked as conflicts and more limiting than any of them:

- **The body outline curve has no trustworthy source.** Length, width and
  thickness are sound; the curve between them is not.
- **The bay has no `body_position`.** It is fully specified and internally
  verified but not placed on the outline, so every back-face position on the
  instrument is still unknown.

## Traps

- **The traced outline is stale.** Four voids; the design has three. What it
  plots as a fourth on the lower treble side is the electronics cavity itself.
  Believing it produced a confident "no electronics pocket fits anywhere"
  finding that was wrong in every part.
- **`front_v5` is deficient** — three void layers, positions off by up to
  30 mm. `back_v5` and the trace agree exactly; `front_v5` does not.
- **DO-NOT-CUT guards key on `body_position` being null**, not on any
  conflict. Anchored to a diagnosis they cleared themselves twice while the
  drawings were still wrong. Leave them keyed to the condition.
- **The 25 surplus mini-amp boards are not for this instrument.** They are 5 V,
  which fights `REQ-POWER-ARCH`'s raw-pack-voltage architecture, and the
  company that made them is a recipient of the RFI. Rev L withdrew the question
  that invited their reuse; do not reopen it.

## Regenerating

Everything under `exports/` is gitignored and rebuilt from fixtures:

```
scripts/export_frontend_brief.py        RFI, markdown
scripts/export_frontend_brief_html.py   RFI, styled HTML
scripts/export_frontend_delta.py        change list, Rev A to current
scripts/export_cad_dimensions.py        CAD dimension sheet (writes to docs/)
scripts/export_smart_guitar_dxf.py      body DXF
scripts/solve_khaya_pocket_layout.py    the packing search
scripts/validate_smart_guitar_geometry.py
```

Published artifacts, private: RFI `a55ac80e-0029-41f3-ab25-48a2bf7de1d9`,
change list `2d2ac04f-c09e-4bfe-82bb-9ea85969a7a2`, dimension sheet
`bbe489e7-bfec-46be-bcf7-9f3487861282`.
