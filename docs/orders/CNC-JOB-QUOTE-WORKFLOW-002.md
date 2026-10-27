# CNC-JOB-QUOTE-WORKFLOW-002

Thin-skin V2 estimate to an internally auditable, customer-separated draft quote packet.

| Field | Value |
|-------|-------|
| Date | 2026-10-26 |
| Target | HanzoRazer/CNC-Production-Shop |
| Status | Implemented on this branch. Not merged, tagged, or released. |
| Authoring baseline | `origin/main` at `408f88037707be868ae08ff2a0a25b1149a18932` |
| Implementation baseline | Same SHA. Prerequisite PR #19, including review fix `236527c`, is in that commit. |
| Branch | `cursor/cnc-job-quote-workflow-002-884a` |
| Open pull requests at start | None |

The order suggested `feat/cnc-job-quote-workflow-002`. This checkout uses the cloud-agent branch template instead. The branch was cut from freshly fetched `origin/main`, not from the documentation branch and not from the old PR #19 head.

## Outcome

An operator uses the existing source-checkout command to turn either governed thin-skin variant into one draft quote packet. The request is `thin_skin_estimate_input_v2`, quantity 1, USD, with an explicit target margin and explicit caller IDs and time. The V1 solid-body workflow and its output bytes stay compatible.

This is the next candidate named by order 001. It is not a Benedetto implementation. The V2 calculator, equipment costing, product definition, and two variant inputs already existed. This order adds workflow admission, complete source capture, a separate `BidV2`, reporting, and end-to-end checks.

The command does not approve a price, send a proposal, or release manufacturing. The direct manufacturing cost and the draft quote price are different numbers.

## Decisions kept

- Cost authority stays in `load_thin_skin_estimate_input` and `calculate_thin_skin_build_estimate`, called on captured snapshot bytes only.
- `BidCostBasisV2` and `BidV2` live in `business/bids/models_v2.py`. `BidV1` is not subclassed or cast.
- `process_rework_and_yield_reserve` is one additive base-cost field, not a new bid percentage.
- Tool wear, manufacturing contingency, business overhead, and engineering recovery percentages stay zero. Existing target-margin functions run once.
- `generate_bid_summary_v2` copies the 17 audit lines and canonical prices into `BidSummaryV1`. The V1 generator is unchanged.
- Customer output remains `ProposalV1`, with the sanitized summary projection, draft notice, review-only next steps, separate price approval and manufacturing release wording, and no signature.
- V1 request and manifest schemas and bytes are unchanged. V2 request, manifest, and `BidV2` declare `record_version` `2.0.0`.
- V1 workflow and mapping lineage stay `1.0.0`. V2 declares `2.0.0`. Those are contract lineage values, not distribution versions.
- The public command remains `python -m business.workflows.cli run`. Dispatch is the validated `(record_version, contract)` pair. There is no auto-detect or latest-file mode. A fixture name ending in `_v1.json` does not select the contract.
- Quantity 1 and USD only. References, IDs, and the canonical UTC timestamp are explicit. There is no default margin, rate, equipment, or source discovery.
- Publication reuses the exclusive, no-replacement rename from PR #19. An unsupported exclusive rename is a failure.
- Generated economic statuses are forced to `draft`. Source confidence and risk/equipment provenance are preserved. A reviewed input does not authorize pricing or manufacturing.

## Category crosswalk

Calculated, rounded category amounts are copied. Operation costs are not summed again into the bid. Zero-valued categories stay in the audit mapping. The estimate total is the eighteenth summary field and is not another cost.

| V2 estimate category | BidV2 cost-basis field |
|----------------------|------------------------|
| `core_material_cost` | `direct_material_cost` |
| `skin_material_cost` | `direct_material_cost` |
| `adhesive_and_lamination_consumables` | `direct_material_cost` |
| `neck_and_fretboard_cost` | `direct_material_cost` |
| `hardware_cost` | `direct_material_cost` |
| `electronics_cost` | `direct_material_cost` |
| `other_consumables_cost` | `direct_material_cost` |
| `material_scrap_allowance` | `direct_material_cost` |
| `lamination_labor_cost` | `direct_labor_cost` |
| `direct_build_labor_cost` | `direct_labor_cost` |
| `assembly_labor_cost` | `direct_labor_cost` |
| `machine_time_cost` | `machine_time_cost` |
| `equipment_occupancy_cost` | `equipment_occupancy_cost` |
| `setup_and_inspection_cost` | `setup_cost` |
| `finishing_labor_cost` | `finishing_cost` |
| `finish_material_cost` | `finishing_material_cost` |
| `process_rework_and_yield_reserve` | `process_rework_and_yield_reserve` |

`tooling_cost` and `engineering_cost` are zero. Finish material is not zeroed the way the V1 adapter zeroes it. Scrap and the reserve are included once. CNC and equipment detail are evidence, not extra costs.

The estimate total, the ten-field bid base, the mapped total, and the 17 audit-line total are equal at the current money convention. The mapping reconciliation difference is zero. Machine detail equals `machine_time_cost`. Equipment records and per-operation amounts may round at different stages. That cent-level difference is reported and is not a hidden balancing line.

## Source capture

Current fixtures capture 11 sources, in this order: job, estimate input, product, machine profile, machine cost basis, then equipment pairs sorted by equipment ID with the profile before the cost basis (`CURE`, `SPRAY`, `VACUUM`). Shared physical bytes are captured once. A conflicting role, schema, or identity for one reference is refused. Every captured source has a digest and a snapshot entry. Generated artifact hashes stay separate from source hashes.

## Files

| Path | Change |
|------|--------|
| `business/bids/models_v2.py` | `BidCostBasisV2` and `BidV2`. Computed ten-component base. |
| `schemas/bids/bid_v2.schema.json` | Closed draft `BidV2` schema. |
| `business/bids/generator_v2.py` | `generate_bid_summary_v2`. No re-pricing. |
| `schemas/workflows/job_quote_request_v2.schema.json` | V2 request envelope. |
| `schemas/workflows/job_quote_manifest_v2.schema.json` | V2 lineage, equipment roles, 17-line mapping. |
| `business/workflows/models.py` | Typed V2 request and mapping records. V1 constants unchanged. |
| `business/workflows/loading.py` | Pair dispatch. V1 validation behavior kept. |
| `business/workflows/loading_v2.py` | Thin-skin dependency capture and equipment checks. |
| `business/workflows/estimate_to_bid_v2.py` | Pure 17-line crosswalk. No I/O. |
| `business/workflows/quote_pipeline.py` | Explicit V1/V2 selection and public-key checks. |
| `business/workflows/reporting.py` | Serializer dispatch. V1 bytes and exclusive publisher kept. |
| `business/workflows/reporting_v2.py` | V2 bid, internal report, and manifest. |
| `business/workflows/cli.py` | Help names both contracts. Flags and exits unchanged. |
| `fixtures/jobs/cnc_job_quote_thin_skin_a_v2.json` | Variant A request. |
| `fixtures/jobs/cnc_job_quote_thin_skin_b_v2.json` | Variant B request. |
| `tests/bids/test_bid_v2.py` | Schema, computed base, summary copy. |
| `tests/workflows/conftest.py` | Isolated V1 and V2 workspace builders. |
| `tests/workflows/test_job_loading_v2.py` | Admission refusals. |
| `tests/workflows/test_estimate_to_bid_v2.py` | Crosswalk and margin boundaries. |
| `tests/workflows/test_job_quote_pipeline_v2.py` | Both variants, snapshots, privacy, publication. |
| `tests/workflows/test_job_quote_cli.py` | Shared draft and publication cases, plus the V2 command. |
| `tests/workflows/test_job_quote_pipeline.py` | Frozen pre-change V1 packet SHA-256s and import checks. |
| `tests/bids/test_machine_costed_bid.py` | Retained V1 and A/B export scan. |
| `README.md` | Contract matrix, both commands, source dependencies, audiences. |
| `TASKSPEC_CNC_PRODUCTION_SHOP.md` | Order 002 registered. Order 001 recorded as merged via #19. |

The pre-change V1 packet oracle is stored as SHA-256 values inside `tests/workflows/test_job_quote_pipeline.py`. The file plan names that test and does not authorize a new golden-packet directory.

No estimate calculator, source fixture, source schema, pricing formula, existing bid or proposal schema, shared legacy proposal wording, `pyproject.toml`, release tooling, or CI configuration was changed. CNC-COST-CORE-3 and CNC-COST-CORE-4 were not implemented.

## Commands

```bash
python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_thin_skin_a_v2.json \
  --output-dir exports/jobs/thin-skin-a-quote-001

python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_thin_skin_b_v2.json \
  --output-dir exports/jobs/thin-skin-b-quote-001
```

Exit 0 writes a validated draft packet. Exit 2 refuses invalid input, an unsupported contract, a bad reference, or an existing destination. Exit 1 is output I/O or a programming failure. Programming errors are not masked as bad input.

## Synthetic fixture math

These are synthetic draft estimates, not shop actuals. Recomputed with the existing V2 loader, calculator, and target-margin function. USD unless the row says minutes.

| Check | Variant A | Variant B |
|-------|-----------|-----------|
| Direct material, including scrap | 234.40 | 247.56 |
| Direct labor (lamination + build + assembly) | 201.25 | 215.15 |
| Machine time | 46.35 | 46.35 |
| Equipment occupancy | 12.13 | 12.13 |
| Setup | 36.89 | 36.89 |
| Finishing labor | 75.23 | 75.23 |
| Finish material | 53.50 | 53.50 |
| Process rework and yield reserve | 41.14 | 43.78 |
| Tooling / engineering | 0 / 0 | 0 / 0 |
| Base = risked cost | 700.89 | 730.59 |
| Quote price at 30% target margin | 1001.27 | 1043.70 |
| Operator labor minutes | 654 | 683 |
| CNC runtime minutes | 96 | 96 |
| Equipment occupancy minutes | 3050 | 3050 |
| Elapsed wait minutes | 315 | 555 |

V1 compatibility remains cost 924.09 and price 1320.13 at 30% margin. A complete V1 demo packet was captured before these code changes. The same source bytes, fixed IDs, time, and relative layout still hash to that packet.

Both generated thin-skin manifests report equipment operation detail 12.12 against an equipment record total of 12.13 (`equipment_detail_difference` 0.01) and a machine detail difference of 0.00. The mapped estimate total is unchanged.

Independent margin proof, unchanged: risked cost 1000 at 30% is 1428.57. Margin 0 returns the base. Negative, 100 or above, non-finite, and boolean margins are refused.

## Limitations

- Local execution for this order is Linux. It is not macOS or Windows validation.
- One packet per invocation. No multi-unit or batch quoting.
- No new cost formulas or rates. The four extra pricing percentages stay zero.
- No actual-cost capture, full overhead, warranty, fulfillment, NRE, or channel pricing.
- No purchasing, approval or revision automation, proposal delivery, production scheduling, or manufacturing release.
- No UI, API, database, design-generator, CAD/CAM, or Benedetto work.
- No tags, releases, or distribution-version changes.
- CNC-COST-CORE-3 and CNC-COST-CORE-4 remain separate orders.

Rollback is to stop admitting V2 requests and keep using V1. Existing packets are immutable evidence. A code revert, if needed, is a separate reviewed revert PR. Generated draft packets are not a manufacturing authorization.

## Verification evidence

These commands were run on this branch after implementation, on commit `f86042becb90da9e52f063300bd10bae62b1fe98`. They are this order's results. Historical pass claims from order 001 are not reused. The sentence that names that commit was added afterward and does not change application code.

The evidence paragraph was written after the gates. It does not change application code. The three demo packets below stayed in place for the full-suite customer-markdown scan.

Local OS: Linux 6.12.94+ x86_64. This is not macOS or Windows validation.

Interpreters, sequential, one checkout at a time:

- CPython 3.12.3 (GCC 13.3.0), system `python3`
- CPython 3.11.18 (Clang 23.1.3), uv virtualenv `/tmp/venv311`, with `pip==26.2.2` installed before the suite

The 3.12 sequential pytest finished at 10:18 PM America/Chicago on 2026-10-26. The 3.11 sequential pytest finished at 10:21 PM America/Chicago the same evening.

### Gates

Both interpreters:

```text
ruff check .                                          All checks passed
mypy business --ignore-missing-imports                Success: 45 source files
mypy musical_spatial_mapping --strict                 Success: 15 source files
mypy cnc_version --strict                             Success: 1 source file
mypy scripts/release --ignore-missing-imports         Success: 13 source files
```

`pytest --cov=business --cov-report=term-missing --cov-fail-under=90`:

```text
CPython 3.12.3   1577 passed, 1 skipped, 3 warnings in 166.86s
                 3875 statements, 352 missed, 90.92%
CPython 3.11.18  1577 passed, 1 skipped, 3 warnings in 161.14s
                 3875 statements, 352 missed, 90.92%
```

The coverage gate is package-wide and was reached on both interpreters. Warnings were the existing zipfile duplicate-name notice and the Click `isolated_filesystem` deprecation in the CLI test. No checkout fixture was left modified.

### Demo commands

On CPython 3.12.3, before the suite, all three exited 0:

```text
JOB-CNC-QUOTE-DEMO-001        draft   924.09   1320.13
JOB-THIN-SKIN-A-DEMO-001      draft   700.89   1001.27
JOB-THIN-SKIN-B-DEMO-001      draft   730.59   1043.70
```

Packets, left in place for the suite:

- `exports/jobs/cnc-job-quote-demo-001`
- `exports/jobs/thin-skin-a-quote-001`
- `exports/jobs/thin-skin-b-quote-001`

Variant A and B each captured 11 sources in the required order and 17 mapping lines. Mapped totals equal the bid base. Equipment operation detail is 12.12 against a record total of 12.13. Machine detail difference is 0.00. Customer JSON and Markdown contained the draft notice and the draft price (`$1,001.27` / `$1,043.70`) and did not contain `28.97`, `target_margin`, `equipment_hour`, `fixtures/`, `Packaging for safe transport`, `Authorized Signature`, `process_rework`, the internal base costs, or the synthetic internal note. The V1 packet's 13 files matched the pre-change SHA-256 oracle.

### Fixture validators and status

On CPython 3.12.3, after the 3.12 suite and before the 3.11 suite:

```text
python scripts/validate_guitar_estimates.py       PASS lineage and recomputation
python scripts/validate_thin_skin_estimates.py    PASS lineage, recomputation, risk, variants
python scripts/validate_bid_fixtures.py           PASS (five bid fixtures)
python scripts/validate_bid_summaries.py          PASS (four summaries)
python scripts/validate_proposals.py              PASS (four proposals)
python scripts/validate_machine_cost_basis.py     PASS bcm_2030ca_atc_cost_basis_v1.json
cam-assist status                                 CAM Assist v0.1.1 — Ready
```

No tag, release, or merge was performed. Hosted Python 3.11 and 3.12 checks are the pull request's CI, separate from this Linux run.

