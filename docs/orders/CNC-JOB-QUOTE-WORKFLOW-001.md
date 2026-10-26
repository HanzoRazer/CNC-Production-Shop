# CNC-JOB-QUOTE-WORKFLOW-001

First operational job → estimate → bid → proposal workflow.

| Field | Value |
|-------|-------|
| Date | 2026-10-25 |
| Target | HanzoRazer/CNC-Production-Shop |
| Status | Implemented on this branch. Not merged, tagged, or released. |
| Authoring baseline | `main` at `54a60932ca5ec4ab2d8f552df6b4fe8cba3f072c` |
| Implementation baseline | Same SHA. `origin/main` had not moved. Open pull requests at start: none. |
| Branch | `cursor/cnc-job-quote-workflow-001-7f77` |

The order suggested `feat/cnc-job-quote-workflow-001`. This checkout uses the cloud-agent branch template instead. The branch was cut from fetched `origin/main`.

## Outcome

An operator supplies a job request that references an existing `GuitarEstimateInputV1` and an explicit pricing assumption. One source-checkout command validates the source records, calculates a draft internal manufacturing estimate, constructs the existing `BidV1` and `BidSummaryV1`, and writes a separate customer-facing draft proposal.

This increment supports exactly:

- estimate contract `guitar_estimate_input_v1`
- quantity 1
- currency USD
- the existing explicit machine profile, cost basis, and V1 calculator
- target-margin pricing, with bid-level risk, overhead, and recovery percentages at zero
- JSON records, an internal Markdown cost report, and a customer Markdown proposal

The baseline solid-body fixture is a verification case. Benedetto remains planning and is not an implementation dependency. No real customer, vendor price, build duration, or production approval is invented. The command writes files. It does not send, approve, publish, tag, or start manufacturing.

## Decisions kept

Calculation, bid construction, orchestration, and filesystem output stay in separate modules. Existing estimate formulas, domain cost categories, money convention, machine rates, fixture totals, Eco-Loom Excel export, and `cam_assist` status are unchanged. `BidV1` and its schema stay intact. The category crosswalk is the mapping below plus the lineage manifest.

No implicit rates, machines, margins, latest-file lookup, or currency conversion. Economic outputs stay `draft` even when an input is reviewed or approved. Confidence on the estimate is not promoted and is not downgraded. Caller-supplied IDs and a UTC `created_at` are required for replay. Additional pricing percentages are fixed at zero: tool wear is already in the technical machine rate, and scrap is already in the estimate.

`business/*` does not import CAM, RMOS, saw code, or network services. The package import does no filesystem I/O.

## Job request

`schemas/workflows/job_quote_request_v1.schema.json`

- `record_type` = `cnc_job_quote_request`, `record_version` = `1.0.0`
- `job_id`, `estimate_id`, `bid_id`, `proposal_id`: nonblank restricted identifiers, not filesystem paths. `estimate_id` must also match the existing guitar estimate id pattern.
- `project_name`, `customer_name`, `revision`: nonblank display strings
- `created_at`: canonical UTC RFC 3339 timestamp ending in `Z`. `effective_date` is its UTC calendar date.
- `estimate_input_contract`: `guitar_estimate_input_v1`
- `estimate_input_ref`: workspace-relative POSIX path
- `quantity`: `1`, and equal to the estimate input quantity
- `currency`: `USD`, and equal to the estimate input currency
- `pricing_policy`: `policy_id` `target_margin`, `policy_version` `1.0.0`, finite `target_margin_pct` with `0 <= value < 100`. No other pricing fields.
- `customer_deliverables`: nonempty explicit public strings
- `customer_exclusions`: explicit public strings
- `internal_notes`: private strings, may be empty
- `additionalProperties` is false on owned objects

`--root` is the source workspace. References resolve against that root, not the job file's directory and not the process working directory. Absolute paths, parent traversal, URLs, and symlinks that escape the root are refused. Each resolved artifact is validated with the canonical schema for its role. Product, machine, and cost-basis identities are checked across records. Labor loaded rate and machine-hour derivation are checked before calculation. JSON is parsed strictly: duplicate keys, `NaN` / `Infinity`, and boolean numerics are refused. JSON Schema format checking is enabled. Canonical `Z` timestamps are also checked with a pattern and `datetime.strptime`, because the installed `jsonschema` format checker does not include `date-time` and this order adds no dependency.

## Runtime

1. Parse `--root`, `--job`, and `--output-dir`.
2. Strictly parse and schema-validate the job and referenced records.
3. Refuse an unsupported contract, quantity, or currency before calculation.
4. Read each source once. Record raw bytes, SHA-256, record identity, and the workspace-relative path.
5. Calculate from those bytes via a temporary snapshot root that keeps the original relative layout, using `load_guitar_estimate_input` and `calculate_guitar_build_estimate`.
6. Build `BidV1` with the mapping below.
7. Generate `BidSummaryV1`.
8. Project a public summary with notes, assumptions, risk factors, and line items cleared. Call `generate_proposal_from_summary` with the caller-supplied `proposal_id` and `created_at`.
9. Set deliverables and exclusions only from the job's public fields, on both the structured fields and the matching sections. The generator's default packaging promise is not inherited.
10. Proposal status is `draft`. `source_summary_ref` and `project_ref` stay null. `proposal.notes` is only the draft-for-review notice.
11. Render Markdown with `include_signature=False` and prepend the same notice.
12. Validate generated JSON, category totals, prices, identity links, and the public projection.
13. Stage the packet beside the destination on the same filesystem. Publish it with a rename only after every check passes.

The destination must be new, inside `--root`, and not a symlink. An existing destination is refused. There is no `--force`. A refusal or a failed publish leaves no final packet. Source records are not modified.

## Estimate to BidV1

The mapping groups existing categories. It does not recalculate them.

| Bid cost basis field | Source |
|----------------------|--------|
| `direct_material_cost` | wood + hardware + electronics + consumables + scrap |
| `direct_labor_cost` | `direct_labor_cost` |
| `machine_time_cost` | `machine_time_cost` |
| `setup_cost` | `inspection_and_setup_cost`, labelled setup and inspection |
| `finishing_cost` | finishing labor |
| `tooling_cost` | 0, already in the technical machine rate |
| `finishing_material_cost` | 0, already in V1 consumables |
| `engineering_cost` | 0, not introduced here |

The mapped sum equals `total_direct_manufacturing_cost` at the existing cent convention. Machine costing is copied, not added again; its derived cost equals `machine_time_cost`. One internal audit line is emitted per source category, including scrap, at quantity 1 with `unit_cost` = `total_cost` = the source amount. Audit totals equal `base_manufacturing_cost`. `tool_wear_pct`, `manufacturing_contingency_pct`, `business_overhead_pct`, and `engineering_recovery_pct` are 0. Pricing uses `calculate_risked_cost`, `calculate_bid_price`, and `calculate_price_per_unit`. Quantity is 1, so `price_per_unit` equals `quote_price`.

Bid notes state that this is direct-cost preliminary pricing and that unallocated overhead, warranty, fulfillment, and NRE are excluded. Those notes stay internal.

`manufacturing_ref` is the packet-relative path `internal/estimate.json`. Machine profile and cost-basis refs keep their source-workspace meaning and resolve through `internal/sources`. The manifest records both namespaces. `dataclasses.asdict` omits the computed `base_manufacturing_cost` property; the bid JSON includes that value and checks it against the component sum.

## Packet

```text
<output-dir>/
  manifest.json
  internal/
    job_request.json
    estimate.json
    bid.json
    bid_summary.json
    cost_report.md
    sources/<original workspace-relative paths>
  customer/
    proposal.json
    proposal.md
```

Only `customer/` is intended for later customer delivery. The manifest contract is `schemas/workflows/job_quote_manifest_v1.schema.json` (`cnc_job_quote_manifest`, version `1.0.0`, status `draft`). It records identities, the request timestamp, calculator id `guitar_build_estimate_v1`, workflow version `1.0.0`, mapping version `1.0.0`, source digests, generated artifact digests, the category mapping, rounding reconciliation, and `direct_manufacturing_cost_only`. `manifest.json` is not in its own hash list.

Generated JSON is UTF-8, sorted keys, two-space indentation, a trailing newline, and no `NaN`. Identical request and source bytes under the same relative layout produce identical output bytes. SHA-256 proves identity, not an approved price or a true measurement.

## Files

| Path | Action |
|------|--------|
| `docs/orders/CNC-JOB-QUOTE-WORKFLOW-001.md` | This order and the check evidence below |
| `schemas/workflows/job_quote_request_v1.schema.json` | Operator input contract |
| `schemas/workflows/job_quote_manifest_v1.schema.json` | Lineage manifest contract |
| `business/workflows/__init__.py` | Package. The plan named `init.py`; the package file is `__init__.py`. No import-time I/O. |
| `business/workflows/models.py` | Request, policy, result, and error records |
| `business/workflows/loading.py` | Strict parse, schema selection, local refs, identity checks, snapshots |
| `business/workflows/estimate_to_bid.py` | Pure mapping. Reuses canonical pricing functions. |
| `business/workflows/quote_pipeline.py` | Orchestration, public projection, lineage. No new cost math. |
| `business/workflows/reporting.py` | Serializers, internal Markdown, staging, publication |
| `business/workflows/cli.py` | `python -m business.workflows.cli run` |
| `business/proposals/generator.py` | Keyword-only `proposal_id` and `created_at`. Omitted values keep the legacy id and clock. |
| `fixtures/jobs/cnc_job_quote_demo_v1.json` | Synthetic `INTERNAL-DEMO` request, margin 30 |
| `tests/workflows/test_job_loading.py` | Input, path, version, finite-number, and identity refusals |
| `tests/workflows/test_estimate_to_bid.py` | Mapping, no double counting, target-margin proof |
| `tests/workflows/test_job_quote_pipeline.py` | Round trip, schemas, replay, snapshots, publication, public projection |
| `tests/workflows/test_job_quote_cli.py` | Exit codes, no partial output, working-directory independence |
| `tests/proposals/test_proposal_generator.py` | Replay overrides. This is the existing owner. The planned name matched, so no second test home was created. |
| `README.md` | Command, contract, and audiences |
| `TASKSPEC_CNC_PRODUCTION_SHOP.md` | Order registered. CNC-COST-CORE-3 and CNC-COST-CORE-4 are not superseded. |

No calculator, rate fixture, legacy bid schema, Eco-Loom export, or dependency was changed.

## Command

```bash
python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_demo_v1.json \
  --output-dir exports/jobs/cnc-job-quote-demo-001
```

| Exit | Meaning |
|------|---------|
| 0 | Validated draft packet written |
| 2 | Invalid invocation or input, unsupported contract, missing or mismatched ref, or existing destination |
| 1 | Output I/O or unexpected internal workflow failure |

Expected invalid input prints `error:` and no traceback. Unexpected programming failures are not relabeled as refusals.

## Baseline fixture math

Recomputed from `fixtures/estimates/guitar/cnc_electric_guitar_baseline_input_v1.json` at quantity 1, USD, 30% target margin:

| Check | Amount |
|-------|--------|
| Material group (115 + 125 + 110 + 75 + 7) | 432.00 |
| Direct labor | 251.55 |
| Machine time (260 min × 28.97/hour) | 125.54 |
| Setup and inspection | 31.14 |
| Finishing labor | 83.86 |
| Bid base = estimate `total_direct_manufacturing_cost` | 924.09 |
| Additional percentages | 0 |
| Risked cost | 924.09 |
| Quote price = price per unit | 1320.13 |

Independent proof, unchanged from the existing calculator: risked cost 1000 at 30% target margin is 1428.57. Margin 0 returns the risked cost. Margin below 0 or at or above 100 is refused.

Demo identities: job `JOB-CNC-QUOTE-DEMO-001`, estimate `GUITAR-BUILD-ESTIMATE-DEMO-001`, bid `BID-CNC-QUOTE-DEMO-001`, proposal `PROP-CNC-QUOTE-DEMO-001`, `created_at` `2026-10-25T16:00:00Z`, customer `INTERNAL-DEMO`.

## Surfaces left in place

The existing proposal generator still emits Next Steps bullets that say "Approve proposal to proceed" and "Production begins upon approval". The workflow sets status `draft`, clears the signature, and adds the draft-for-review notice. It does not change that inherited prose. Changing it would widen `business/proposals` past the authorized replay overrides.

`tests/bids/test_machine_costed_bid.py` scans every Markdown file under `fixtures/proposals` and `exports/` and fails if `28.97` appears. The internal cost report correctly contains that technical rate. A packet left at `exports/jobs/` fails that existing test. The test was not changed. Remove the generated packet before the full suite. `exports/*` stays gitignored except the existing proposal and workbook exceptions.

## Deferred

- Benedetto and other instrument design or procurement
- Thin-skin V2 adapter, a generalized instrument product schema, and multi-unit costing
- General Excel export, actual-cost capture, and full overhead, NRE, and warranty economics
- Generator access, PEM/CAM admission, CAD/CAM, scheduling, and machine execution
- UI, API, database, automatic price refresh, and new publishing automation

Next candidate after review: the second existing estimate contract, thin-skin V2, with its own category mapping. This increment does not accept that contract.

## Verification evidence

Authoring the order was not test execution. The commands below were run on this branch after implementation. The sequential pytest runs finished at 11:49 PM and 11:52 PM America/Chicago on 2026-10-25.

Interpreters:

- CPython 3.12.3, virtualenv `/tmp/venv312`
- CPython 3.11.17, uv virtualenv `/tmp/venv311`

The 3.11 environment was created without pip. An earlier full pytest on that interpreter stopped one release test with `No module named pip` (`tests/releases/test_release_automation.py::test_wheel_installs_into_isolated_venv`). `pip==26.2.2` was then installed into that environment. The same test was re-run and passed (`1 passed in 9.38s`).

### Gates

Both interpreters, before the pytest runs:

```text
ruff check .                                          All checks passed
mypy business --ignore-missing-imports                Success: 40 source files
mypy musical_spatial_mapping --strict                 Success: 15 source files
mypy cnc_version --strict                             Success: 1 source file
mypy scripts/release --ignore-missing-imports         Success: 13 source files
```

`pytest --cov=business --cov-report=term-missing --cov-fail-under=90` was first started on both interpreters at once. Those two processes rewrite `fixtures/estimates/neck/neck_make_or_buy_result_v1.json` in place during tamper tests. They crossed. The 3.12 process reported 4 failed, 1494 passed, 1 skipped. The 3.11 process reported 1 failed, 1497 passed, 1 skipped. The failures were neck make-or-buy validator tests, and the fixture was left with `maximum_compatible_delivered_purchase_price` changed from `35.99` to `999.0`. That edit was restored with `git checkout -- fixtures/estimates/neck/neck_make_or_buy_result_v1.json`. The sequential re-runs are the results that count:

```text
CPython 3.12.3   1498 passed, 1 skipped, 3 warnings in 161.02s
                 3186 statements, 223 missed, 93%
CPython 3.11.17  1498 passed, 1 skipped, 3 warnings in 155.46s
                 3186 statements, 223 missed, 93%
```

The coverage gate is package-wide and was reached on both interpreters. The neck fixture was clean after the sequential runs.

### Demo command

```text
python -m business.workflows.cli run \
  --root . \
  --job fixtures/jobs/cnc_job_quote_demo_v1.json \
  --output-dir exports/jobs/cnc-job-quote-demo-001
```

CPython 3.12.3, exit 0:

```text
job_id: JOB-CNC-QUOTE-DEMO-001
status: draft
direct_manufacturing_cost: 924.09
quote_price: 1320.13
```

Bid cost basis from that packet: material 432.00, labor 251.55, machine 125.54, setup 31.14, finishing 83.86, tooling 0, finishing material 0, engineering 0, base 924.09. Pricing percentages other than the requested 30% target margin were 0. Risked cost 924.09. `price_per_unit` 1320.13. Manifest `record_type` `cnc_job_quote_manifest`, status `draft`, calculator `guitar_build_estimate_v1`, disclosure `direct_manufacturing_cost_only`. Proposal status `draft`, notes limited to the draft-for-review sentence, `source_summary_ref` and `project_ref` null. Deliverables and exclusions matched the job request, including packaging listed as an exclusion. Customer Markdown contained the draft notice and `$1,320.13`, and did not contain `28.97`, `28.75`, `23.00`, `924.09`, `target_margin`, `Authorized Signature`, `Packaging for safe transport`, or source paths. The word `overhead` appeared only inside the operator-supplied exclusion. The packet was deleted before the suite so the commercial-boundary Markdown scan would not see the internal rate.

### Fixture validators and status

On CPython 3.12.3, after the demo packet was removed:

```text
python scripts/validate_guitar_estimates.py     PASS lineage and recomputation
python scripts/validate_bid_fixtures.py         PASS (five bid fixtures)
python scripts/validate_bid_summaries.py        PASS (four summaries)
python scripts/validate_proposals.py            PASS (four proposals)
python scripts/validate_machine_cost_basis.py   PASS bcm_2030ca_atc_cost_basis_v1.json
cam-assist status                               CAM Assist v0.1.1 — Ready
```

No tag, release, or merge was performed.
