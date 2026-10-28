# CNC-JOB-QUOTE-VERIFY-001

Offline verification of a saved solid-body V1 or thin-skin V2 draft quote packet.

| Field | Value |
|-------|-------|
| Prepared | 2026-10-27, America/Chicago |
| Repository | HanzoRazer/CNC-Production-Shop |
| Authoring baseline | `origin/main` at `ef4d6e31bda91932dc123eca9702dc086fa3bd87` |
| Implementation branch | `cursor/cnc-job-quote-verify-001-884a` |
| Prerequisites | PR #19 and PR #20 merged. #20 includes test-isolation fix `b392581`. |
| Open pull requests at start | None |

The handoff suggested `feat/cnc-job-quote-verify-001`. This checkout uses the cloud-agent branch template. The branch was cut from freshly fetched `origin/main` at `ef4d6e3`, not from the order-002 branch.

## Outcome

An operator can verify a saved draft packet after it has been copied to another directory or machine. Verification uses the packet bytes and the canonical code and schemas in a supported source checkout. The original source workspace and its current rates are not required.

`run` is unchanged. It still generates a packet and checks that packet before publication. `verify` is the command that admits an existing on-disk packet. It does not approve a price, send a proposal, or release manufacturing.

A valid result means the captured bytes match supported deterministic generation and the economic status is still `draft`. It is internal evidence. It is not a price approval, a customer commitment, or a manufacturing release.

## Decisions kept

- Only the V1 and V2 manifest, request, workflow, and mapping combinations emitted by orders 001 and 002 are accepted. Unknown combinations fail closed.
- Economics stay in `load_job_quote` and `build_job_quote_packet`. This order does not add a calculator, a category crosswalk, or a price formula.
- Replay calls those two functions. It does not call `run_job_quote` or `publish_packet`, and it does not write a quote packet.
- Packet files are not repaired, normalized, overwritten, annotated, or removed. Temporary reconstruction uses a separate directory and is removed on success, refusal, and I/O failure.
- The optional expected digest is supplied by the caller. A match means the manifest bytes equal that supplied anchor. It does not say who authorized the anchor.
- Without an anchor, a coherent packet regenerated from edited sources can verify. That is consistency with the current generator, not origin authentication.
- Neither a valid result nor a matching anchor certifies measurements, vendor prices, economic completeness, or shop readiness.
- SHA-256 is not an authenticity proof. The command validates the captured view. It does not lock the directory, and it does not claim protection against a concurrent writer replacing parent paths. Verify a quiescent packet.
- The result contains no clock, random id, absolute path, cost, or approval field. The same bytes and options produce the same canonical JSON.
- Customer artifacts are compared by replay of the existing public projection. The verification result stays internal.
- CNC-COST-CORE-3 and CNC-COST-CORE-4 stay separate. No competing quote-package or shop-operation record was added.
- Packet schemas, generated packet contracts, rates, calculator inputs, and the distribution version are unchanged. The new contract is the verification result only.

## Command

```bash
python -m business.workflows.cli verify \
  --packet-dir exports/jobs/thin-skin-a-quote-001

python -m business.workflows.cli verify \
  --packet-dir /path/to/copied-packet \
  --expected-manifest-sha256 REPLACE_WITH_RETAINED_64_HEX_DIGEST \
  --json
```

The digest placeholder is not an authority value. Replace it with the caller-retained 64-character lowercase SHA-256 of `manifest.json`.

| Exit | Meaning |
|------|---------|
| 0 | Every supported check passed. Economic status remains `draft`. |
| 2 | Invalid invocation or packet. With `--json`, stdout is the result object and nothing else. |
| 1 | Unreadable file, temporary-storage failure, or an unexpected verifier error. Stdout is not a verification result. |

Malformed flags and digest syntax are Click usage errors. Programming errors are not reclassified as invalid packets.

## Result contract

`schemas/workflows/job_quote_verification_v1.schema.json`

| Field | Contract |
|-------|----------|
| `record_type`, `record_version` | `cnc_job_quote_verification`, `1.0.0` |
| `authority` | `verification_only` |
| `result` | `valid` or `invalid` |
| `manifest_sha256` | Digest of the raw manifest bytes, or null |
| `expected_manifest_sha256` | Caller value, or null |
| `anchor_status` | `matched`, `mismatch`, `not_supplied`, or `not_checked` |
| `packet_version` | `1.0.0`, `2.0.0`, or null before admission |
| `economic_status` | `draft` when valid, otherwise null unless already established |
| ids | Admitted ids, or null before validation |
| `checks` | `inventory`, `schemas`, `hashes`, `source_closure`, `replay` |
| `errors` | Stable code and a packet-relative member, or null |

An anchor mismatch is reported before the five checks run, so those checks stay `not_run`. The first unsafe or invalid phase fails, and later checks stay `not_run`. Diagnostics do not copy packet text.

## Files

| Path | Change |
|------|--------|
| `business/workflows/verification_models.py` | Result, check, and diagnostic records. |
| `business/workflows/packet_loading.py` | Non-following inventory, capture, schema selection, hashes. |
| `business/workflows/verification.py` | Reconstruction, canonical replay, cleanup, result. |
| `schemas/workflows/job_quote_verification_v1.schema.json` | Closed result contract. |
| `business/workflows/cli.py` | `verify` command. `run` is unchanged. |
| `tests/workflows/conftest.py` | Fresh V1/A/B packet builders. |
| `tests/workflows/test_packet_loading.py` | Inventory, confinement, JSON, hashes, capture changes. |
| `tests/workflows/test_job_quote_verification.py` | Relocation, replay, anchors, oracles, cleanup. |
| `tests/workflows/test_job_quote_verification_cli.py` | Output, exits, usage errors. |
| `README.md` | Verification command and trust limits. |
| `TASKSPEC_CNC_PRODUCTION_SHOP.md` | Order 002 merged via #20; this order registered. |

## Actual limitations

- Linux in this environment is not macOS or Windows validation.
- Verification does not authenticate the operator, sign the packet, or prove who retained an anchor.
- A valid unanchored result can be a newly generated packet from edited but still coherent sources.
- Hand-edited, reformatted, or rehashed packets are refused. Change economic content by generating a new draft. Keep the old packet as evidence.
- The reader rejects symlink roots and symlink or special members. It does not use `resolve_workspace_file` as the packet inventory rule, because that loader still permits some in-root symlinks.
- Source counts are not hardcoded. Current V1 packets have five sources. Current thin-skin packets have eleven, including three equipment pairs. Closure comes from `load_job_quote`.
- No tag, release, approval action, or CI configuration change is part of this order.

## Local evidence

Linux 6.12.94+ x86_64. These counts belong to this order. They are not the order-002 results.

```text
ruff check .                                          All checks passed
mypy business --ignore-missing-imports                Success: 48 source files
mypy musical_spatial_mapping --strict                 Success: 15 source files
mypy cnc_version --strict                             Success: 1 source file
mypy scripts/release --ignore-missing-imports         Success: 13 source files
```

`pytest --cov=business --cov-report=term-missing --cov-fail-under=90`:

```text
CPython 3.12.3   1688 passed, 1 skipped, 3 warnings in 198.07s
                 4445 statements, 413 missed, 90.71%
                 finished 7:56 PM America/Chicago, 2026-10-27
CPython 3.11.18  1688 passed, 1 skipped, 3 warnings in 181.24s
                 4445 statements, 413 missed, 90.71%
                 finished 8:00 PM America/Chicago, 2026-10-27
```

The 3.12 run started at 7:53 PM America/Chicago. The 3.11 run started at 7:57 PM America/Chicago, after the 3.12 run finished. Warnings were the existing zipfile duplicate-name notice and the Click `isolated_filesystem` deprecation. No checkout fixture was left modified. Linux execution here is not macOS or Windows validation.

### Hosted checks

GitHub Actions run [40612483207](https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/40612483207) succeeded on `01d833b2021b8ff7f44b5278d7b23228b94d4789`. Both jobs started at 8:01 PM America/Chicago on 2026-10-27. This paragraph records that run. It does not change the verifier.

| Job | Result | Duration | Finished (America/Chicago) | Link |
|-----|--------|----------|----------------------------|------|
| test (3.11) | success | 1m24s | 8:02 PM | https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/40612483207/job/122567107139 |
| test (3.12) | success | 2m22s | 8:03 PM | https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/40612483207/job/122567107311 |

A temporary V1 packet verified with economic status `draft`, packet version `1.0.0`, and manifest SHA-256 `f80398f299f71b3cb3241f1b882bce8390ba356c81dd1764d89c0cf29aa9f239`. That digest matches the existing pre-change V1 manifest oracle. All five checks passed. Appending one byte to `internal/cost_report.md` without updating the manifest failed at `hashes` with `HASH_MISMATCH` and left replay `not_run`. Supplying 64 zeroes as the expected digest failed with `ANCHOR_MISMATCH` before any check ran. The verification text did not include the manufacturing cost or the draft price.
