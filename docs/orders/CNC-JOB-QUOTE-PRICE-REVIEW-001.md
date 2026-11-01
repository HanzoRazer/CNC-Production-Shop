# CNC-JOB-QUOTE-PRICE-REVIEW-001

Record one caller-asserted human price decision against a verified draft quote packet.

| Field | Value |
|-------|-------|
| Prepared | 2026-10-31, America/Chicago |
| Repository | HanzoRazer/CNC-Production-Shop |
| Authoring baseline | `origin/main` at `d24d637fe70ba7e4ef0d2e99f571579a34ac9c05` |
| Implementation branch | `cursor/cnc-job-quote-price-review-001-884a` |
| Prerequisites | PR #21 merged, including branch tip `63a430c`. PR #19 and PR #20 are also merged. |
| Open pull requests at start | None |

The handoff suggested `feat/cnc-job-quote-price-review-001`. This checkout uses the cloud-agent branch template. The branch was cut from freshly fetched `origin/main` at `d24d637`, not from the verify branch and not from an older PR #21 head.

## Outcome

An operator records what a named human says they decided about one draft packet. The command verifies that packet once with the manifest SHA-256 retained in the request, compares the stated subject and price with that same capture, and publishes a new internal bundle outside the packet.

The price decision is a separate immutable record. The original quote packet, its economic statuses, and both customer artifacts remain draft and unchanged. `approve_price`, `request_changes`, and `reject` are all successful recordings. Passing verification does not infer a decision, and `approve_price` does not open a business or machine gate.

## Decisions kept

- The decision enum is `approve_price`, `request_changes`, or `reject`. The caller supplies it. The command never infers it.
- `authority` is `caller_asserted_price_review_only`. `reviewer_identity_assurance` is `caller_asserted`. Neither authenticates a person, a role, or approval authority.
- No consumer in this order treats the unsigned record as an authenticated approval, a customer-send permission, or a manufacturing-release token.
- The retained manifest digest is required in the request. Fresh verification must be valid and `anchor_status` must be `matched`. There is no default digest, cached report, skip-verify flag, or unanchored path.
- The stated amount, currency, quantity, and revision are compared with the captured packet from that verification. The command does not reopen `customer/proposal.json` to select the price.
- Quantity stays 1, currency stays USD, and the quote price must be finite, nonnegative, and cent-valued. All four additional pricing factors stay zero. The direct-manufacturing-cost-only disclosure is acknowledged and does not make the cost basis commercially complete.
- The review bundle is a new directory. Publication is exclusive and does not replace an existing destination. The bundle is never placed under the quote packet, including `customer/`.
- The caller supplies the review ID and canonical UTC `reviewed_at`. `reviewed_at` must not be earlier than the captured job-request `created_at`. Both are assertions, not a trusted clock.
- The same request bytes, packet bytes, and retained digest produce the same bundle bytes. An identical retry is refused. A later decision uses a new review ID and a new destination.
- `run` and `verify` keep their flags, exit behavior, result schema, and bytes.
- The command does not authenticate a reviewer, sign a record, approve by CI, send a proposal, release manufacturing, or promote packet status.

## Command

```bash
python -m business.workflows.cli record-price-review \
  --packet-dir exports/jobs/thin-skin-a-quote-001 \
  --request /path/to/price-review-request.json \
  --output-dir exports/quote-reviews/PRICE-REVIEW-DEMO-001
```

Relative paths resolve against the current working directory. The retained digest is a field in the request file. The command does not compute one from the packet directory, and it cannot prove how the caller obtained it.

A synthetic request for the thin-skin A demo, whose draft price at the 30% target margin is 1001.27, looks like this. It is not a real review and not an approval:

```json
{
  "record_type": "cnc_job_quote_price_review_request",
  "record_version": "1.0.0",
  "review_id": "PRICE-REVIEW-DEMO-001",
  "reviewed_at": "2026-10-26T16:00:00Z",
  "reviewer_ref": "person-demo-001",
  "reviewer_role": "price-reviewer",
  "decision": "approve_price",
  "reason": "Synthetic rationale. Not an authenticated approval.",
  "internal_notes": [],
  "expected_manifest_sha256": "REPLACE_WITH_RETAINED_64_LOWERCASE_HEX",
  "reviewed_subject": {
    "job_id": "JOB-THIN-SKIN-A-DEMO-001",
    "estimate_id": "THIN-SKIN-GUITAR-BUILD-ESTIMATE-VARIANT-A-DEMO-001",
    "bid_id": "BID-THIN-SKIN-A-DEMO-001",
    "proposal_id": "PROP-THIN-SKIN-A-DEMO-001",
    "revision": "Draft 1",
    "currency": "USD",
    "quantity": 1,
    "quote_price": 1001.27
  },
  "cost_basis_acknowledgment": "direct_manufacturing_cost_only"
}
```

The digest placeholder is not an authority value. Replace it with the SHA-256 of `manifest.json` that the human retained. The solid-body demo price is 1320.13 and thin-skin B is 1043.70. Those are the existing synthetic quotes. This order does not change them.

| Exit | Meaning |
|------|---------|
| 0 | A new validated review bundle was written. Stdout prints the stated decision. |
| 2 | Invalid request or subject, rejected packet, unmatched anchor, unsafe or existing output, or invalid invocation. No bundle. |
| 1 | Operational I/O or an unexpected implementation failure. No bundle. Programming errors are not relabelled as bad input. |

Refusal text is a stable code. It does not print reviewer notes, internal values, or packet contents. `reject` is a human disposition, not an execution failure.

## Bundle

```text
<review directory>/
  review_request.json
  verification.json
  review.json
  review.md
```

`review_request.json` is the raw admitted request. `verification.json` is the canonical verification payload from this run. `review.json` binds the request, subject, and verification result. It does not hash itself or `review.md`. `review.md` is an internal summary of the subject, digests, rationale, decision, and the asserted-identity limitation. All four files are internal. The directory is not a quote packet and is not a customer deliverable.

## Contracts

`schemas/workflows/job_quote_price_review_request_v1.schema.json` is the closed request. `schemas/workflows/job_quote_price_review_v1.schema.json` is the closed internal record. Duplicate keys, unknown fields, booleans used as numbers, nonfinite constants, invalid dates, and unsupported versions are refused. Extra `signed_by`, `identity_verified`, release, or sent fields are refused. The authority and identity-assurance constants are written by the recorder and cannot be supplied by the request.

The subject carries the verified packet version, manifest digest, admitted IDs, revision, USD, quantity 1, quote price, and `economic_status: draft`. It does not copy manufacturing cost, margin, equipment rates, or reserve detail.

## Capture seam

`verify_job_quote_packet` still returns only `JobQuoteVerification` and discards the capture. `require_verified_packet` requires an explicit digest, admits and replays once, and returns `VerifiedQuotePacket` with that capture. An invalid result raises the existing `PacketRejectedError`. `ensure_captured_unchanged` uses the verifier's current identity check immediately before publication. `CapturedPacket` stays out of `verification_models.py`.

## Files

| Path | Change |
|------|--------|
| `schemas/workflows/job_quote_price_review_request_v1.schema.json` | Strict human-request contract. |
| `schemas/workflows/job_quote_price_review_v1.schema.json` | Internal review record. |
| `business/workflows/price_review_models.py` | Typed request result, subject, and errors. |
| `business/workflows/price_review.py` | Admission, subject comparison, anchored verification, publication. |
| `business/workflows/price_review_reporting.py` | Canonical payload, Markdown, four-file bundle. |
| `business/workflows/verification.py` | Capture-returning core, `require_verified_packet`, unchanged check. |
| `business/workflows/cli.py` | `record-price-review`. `run` and `verify` stay as they were. |
| `tests/workflows/conftest.py` | Request builder over fresh temporary packets. |
| `tests/workflows/test_price_review.py` | Decisions, anchors, subject, publication, immutability. |
| `tests/workflows/test_price_review_cli.py` | Exits, cwd paths, no sending or execution. |
| `tests/workflows/test_job_quote_verification.py` | One admission/replay and unchanged public results. |
| `README.md` | Command, retained digest, and authority limits. |
| `TASKSPEC_CNC_PRODUCTION_SHOP.md` | Verifier merged via #21. This order registered. |

Packet loading, verification models, existing schemas, calculators, rates, source fixtures, proposal wording, legacy quote models, dependencies, release tooling, and CI were not modified.

## Actual limitations

- Linux in this environment is not macOS or Windows validation. Exclusive rename still uses the existing publisher.
- The command records the caller's asserted identity and decision. It does not authenticate either one.
- The retained digest is trusted only as a byte anchor. The command cannot prove who retained it or when.
- A detected packet change after capture refuses publication. There is no filesystem lock and no claim about a later concurrent writer.
- Parent traversal, symlink destinations, and symlink parent components are refused. A malicious replacement of a parent after the path check is outside this guarantee.
- The review does not reprice the packet and does not make the direct-cost disclosure commercially complete.
- No tag, release, approval action, or CI configuration change is part of this order.

## Local evidence

Linux 6.12.94+ x86_64. These counts belong to this order. They are not the verify-order results. The Python sources and tests in this commit are the tree that passed the gates below. This evidence section was written immediately afterward and does not change executable code.

```text
ruff check .                                          All checks passed
mypy business --ignore-missing-imports                Success: 51 source files
mypy musical_spatial_mapping --strict                 Success: 15 source files
mypy cnc_version --strict                             Success: 1 source file
mypy scripts/release --ignore-missing-imports         Success: 13 source files
```

Both interpreters reported those mypy and ruff results. `pytest --cov=business --cov-report=term-missing --cov-fail-under=90`:

```text
CPython 3.12.3   1788 passed, 1 skipped, 3 warnings in 206.55s
                 4810 statements, 414 missed, 91.39%
                 started 10:25 PM, finished 10:28 PM America/Chicago, 2026-10-31
CPython 3.11.18  1788 passed, 1 skipped, 3 warnings in 190.76s
                 4810 statements, 414 missed, 91.39%
                 started 10:34 PM, finished 10:37 PM America/Chicago, 2026-10-31
```

The 3.12 run started at 10:25 PM America/Chicago. The 3.11 run started at 10:34 PM America/Chicago, after the 3.12 run finished. Warnings were the existing zipfile duplicate-name notice and the Click `isolated_filesystem` deprecation. The single skip is the existing Windows `py` launcher check. No checkout fixture was left modified. Linux execution here is not macOS or Windows validation.

The 3.11 interpreter was installed for this run. Its first pytest could not build a wheel because that environment had no `pip` module. After `pip` was installed, the suite above passed, including the release wheel test. That was an environment gap, not a product failure.

Nine decision and packet combinations recorded. V1 stayed 1320.13 with internal manufacturing total 924.09, variant A stayed 1001.27 with 700.89, and variant B stayed 1043.70 with 730.59. Those costs remain in the packet. They are not copied into the review subject. Each recorded bundle kept `economic_status: draft`, `authority: caller_asserted_price_review_only`, and `reviewer_identity_assurance: caller_asserted`. `reject` and `request_changes` exited 0 after a successful recording. The original packet files were unchanged, and `verify` still accepted them.

### Hosted checks

GitHub Actions run [41270009257](https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/41270009257) succeeded on `05f9caf86207d0e8b8fb74d82e5dcf073cbee135`. Both jobs started at 10:38 PM America/Chicago on 2026-10-31. This paragraph records that run. It does not change the recorder.

| Job | Result | Duration | Finished (America/Chicago) | Link |
|-----|--------|----------|----------------------------|------|
| test (3.11) | success | 2m30s | 10:41 PM | https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/41270009257/job/124740666553 |
| test (3.12) | success | 1m50s | 10:40 PM | https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/41270009257/job/124740666441 |
