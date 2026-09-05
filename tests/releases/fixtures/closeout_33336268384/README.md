# Closeout run 33336268384 evidence

Captured from GitHub Actions run
[33336268384](https://github.com/HanzoRazer/CNC-Production-Shop/actions/runs/33336268384)
(`Release Candidate Verification` on `main` @ `18125a09`).

Layout matches `actions/download-artifact@v4` with `path: artifacts`:

```text
artifacts/release-candidate-3.11/release_evidence_0.1.1.json
artifacts/release-candidate-3.12/release_evidence_0.1.1.json
```

Both legs completed wheel, install, parity, and manifest checks. The only
payload blocker is `canonical tag v0.1.1 already exists`. Wheels are omitted;
the classifier reads only `release_evidence_*.json`.
