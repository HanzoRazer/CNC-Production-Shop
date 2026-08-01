# PR Review Checklist by Subsystem

Use this checklist when reviewing large cross-cutting PRs that touch multiple subsystems, especially:
- estimates
- geometry
- fixtures
- docs
- exporters

> Recommended review order: `estimates` -> `geometry` -> `fixtures` -> `docs` -> `exporters`

---

## `estimates`
- [ ] **V1 baseline estimate is internally consistent**
  - [ ] `business/estimates/guitar.py`, `models.py`, `loading.py`, and baseline fixtures agree on fields and totals
  - [ ] V1 result still recomputes cleanly from its input fixture

- [ ] **V2 thin-skin contract is coherent**
  - [ ] Labor, CNC runtime, equipment occupancy, elapsed wait, and rework are kept separate
  - [ ] No category silently collapses these back into generic labor

- [ ] **Aggregate vs per-operation costing is intentional**
  - [ ] Aggregate machine/equipment totals are the source of truth
  - [ ] Per-operation machine/equipment costs are clearly informational only

- [ ] **Risk mechanisms do not double count**
  - [ ] Scrap allowance and process/yield reserve are separate
  - [ ] Reserve base excludes scrap allowance exactly as documented

- [ ] **`reserve_eligible` is applied intentionally**
  - [ ] Eligible operations reflect explicit policy
  - [ ] No accidental defaults or category leakage

- [ ] **Equipment costing path is correct**
  - [ ] Equipment-hour rates derive correctly from burden + electricity + consumables
  - [ ] Repo-relative refs, ID validation, and provenance handling are strict

- [ ] **Neck make-or-buy model is like-for-like**
  - [ ] Comparisons only happen at matching completion states
  - [ ] Saleable vs started unit math is sound
  - [ ] Batch amortization and yield handling make economic sense

- [ ] **Cure/wait time is no longer charged as labor**
  - [ ] No remaining neck operations misclassify elapsed wait or occupancy as labor
  - [ ] Final neck totals/docs reflect the corrected semantics

- [ ] **Back-calculation respects pricing boundaries**
  - [ ] Third-party manufacturing-cost inference is kept separate from pricing this shop’s product
  - [ ] Margin assumptions remain explicit and bounded

- [ ] **Neck quality taxonomy is appropriate as executable logic**
  - [ ] Team agrees comparability refusal / verifiability / defect logic belongs in model code
  - [ ] Assumption-heavy conclusions are structurally marked as draft/unconfirmed

---

## `geometry`
- [ ] **Final geometry model is canonical**
  - [ ] No lingering dependency on superseded outline/void assumptions
  - [ ] Final branch state reflects the corrected Smart Guitar geometry story

- [ ] **Stated vs derived dimensions are used correctly**
  - [ ] `stated_*` values are comparison inputs only
  - [ ] Derived geometry is the only source of computed fit/clearance decisions

- [ ] **Conflict/ruling model is consistent**
  - [ ] Ruled / open / withdrawn conflicts are represented consistently in code, fixtures, and docs
  - [ ] Withdrawn findings are not still consumed by tooling

- [ ] **Thickness / bridge envelope assumptions are final-state consistent**
  - [ ] Final 47.0 mm blank assumptions are used where intended
  - [ ] Headless bridge envelope logic matches current product assumptions

- [ ] **Pod split and ribbon-based layout are fully propagated**
  - [ ] Final model is split pod, not one-piece pod
  - [ ] Ribbon/channel geometry matches final connector assumptions
  - [ ] Old pod assumptions are gone from live geometry consumers

- [ ] **Electronics bay semantics are stable**
  - [ ] Bay-local placements are internally valid
  - [ ] `body_position = null` is treated as unresolved placement, not implicitly safe

- [ ] **Battery topology is settled**
  - [ ] Final 2S / 2S2P interpretation is consistent across geometry consumers
  - [ ] Old “4x 18650” ambiguity no longer leaks into active geometry logic

- [ ] **Void interpretation is final**
  - [ ] No stale “nothing fits anywhere” conclusion remains active
  - [ ] Final hollow/void interpretation is what current tooling/docs assume

- [ ] **Cutter/radius/reach logic is manufacturable**
  - [ ] 6.35 mm cutter and 3.175 mm radius are used consistently
  - [ ] Reach/stickout caveats are carried where geometry is technically valid but machining-sensitive

- [ ] **Geometry does not overstate certainty**
  - [ ] Unsettled outline/placement questions remain visibly unsettled in model outputs

---

## `fixtures`
- [ ] **Estimate fixtures recompute from source logic**
  - [ ] Baseline guitar fixtures are current
  - [ ] Thin-skin variant A/B fixtures are current
  - [ ] Neck make-or-buy fixtures are current
  - [ ] Neck quality fixtures are current

- [ ] **Fixture totals match code, not stale docs**
  - [ ] Category totals, reserve bases, occupancy rates, and summaries align with implementation

- [ ] **Fixture IDs and references are strict**
  - [ ] `equipment_id`, `cost_basis_id`, `machine_id`, `estimate_input_id`, etc. all align with code/schema expectations

- [ ] **Repo-relative refs are consistent**
  - [ ] No absolute/local-path leakage remains

- [ ] **Conflict fixtures reflect final rulings**
  - [ ] Late geometry/product conflict changes are reflected in final fixture state

- [ ] **Withdrawn/superseded assumptions are not still encoded as active data**
  - [ ] No stale values or narratives remain machine-consumable

- [ ] **Fixture provenance is honest**
  - [ ] Draft / engineering_estimate / catalog_price / inherited defaults are represented consistently
  - [ ] Nothing implies measured or owner-confirmed status without support

- [ ] **Generated result fixtures were actually regenerated**
  - [ ] Large result JSONs match the final implementation, not earlier branch states

---

## `docs`
- [ ] **Docs describe final state, not intermediate branch history**
  - [ ] Current docs do not present invalidated conclusions as live truth

- [ ] **Narrative reversals are handled correctly**
  - [ ] Preserved mistakes are explicitly framed as superseded
  - [ ] Final docs are not silently mixing old and new assumptions

- [ ] **Product state is consistent across docs**
  - [ ] Smart Guitar / Khaya distinctions are consistent
  - [ ] Headless / passive / onboard-compute state is consistent
  - [ ] NRE-sharing assumptions match final product state

- [ ] **Neck docs reflect the cure-time fix**
  - [ ] Final neck totals and conclusions use post-fix values

- [ ] **EMC docs only cite live geometry where intended**
  - [ ] Withdrawn distances are removed unless explicitly historical/retracted

- [ ] **CAD dimension sheet matches current records**
  - [ ] Pod dimensions
  - [ ] Battery dimensions
  - [ ] Route sizes
  - [ ] Separation values
  - [ ] Routing schedule assumptions

- [ ] **RFI / front-end brief revisions are coherent**
  - [ ] Final brief, HTML export, and change list agree on current revision state
  - [ ] Withdrawn amp-board reuse question is clearly dead

- [ ] **Vendor-facing process messaging is correct**
  - [ ] Issued-status and change-contact text does not imply process completeness where gaps remain

---

## `exporters`
- [ ] **Exported outputs reflect only current safe states**
  - [ ] No exporter still relies on stale embedded constants
  - [ ] Outputs are derived from current fixtures/records

- [ ] **Unsafe/incomplete geometry is visibly marked**
  - [ ] DO-NOT-CUT behavior keys off the actual unsafe condition
  - [ ] Warning survives in the artifact, not just terminal output

- [ ] **Coordinate frames are consistent in exports**
  - [ ] Origin, axes, centerline, and top-edge datum match current conventions

- [ ] **Layer naming conveys state correctly**
  - [ ] Invalid/provisional geometry cannot appear production-ready by hiding a notes layer

- [ ] **Regeneration tests are meaningful**
  - [ ] Exporter tests would catch stale hardcoded text and withdrawn values

- [ ] **Markdown/HTML brief exporters read from fixtures directly**
  - [ ] No hand-maintained duplicated content path remains

- [ ] **Exported clearances/separations are recomputed**
  - [ ] EMC-sensitive distances and bay-packing dimensions are derived from final records

- [ ] **Dependencies are fully declared**
  - [ ] Export/runtime dependencies like `ezdxf` are declared and exercised in CI

---

## Blocking-focus reminder
- [ ] Trace all downstream effects of the geometry invalidation/recovery sequence
- [ ] Confirm final neck economics after the cure-time labor fix
- [ ] Confirm final product canon after the Khaya reversals
- [ ] Confirm policy-like logic in `neck_quality` is intended as executable business logic
