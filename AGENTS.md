# Agent instructions — CNC Production Shop

Read this before creating a branch or opening a pull request. It is read by
Cursor, Codex, and other coding agents; `CLAUDE.md` carries the project and
architecture context and applies too.

## Branch from current `main`. Always.

```bash
git fetch origin
git switch -c <branch-name> origin/main
```

Not from the workspace's current `HEAD`. Not from another branch. Not from a
branch belonging to a pull request that has not merged yet.

This is not style. Three pull requests in a row — #12, #13, #14 — were opened
off a stale head, and every one of them had to be reconciled by hand:

- **#12 and #13** each branched from `18125a09`, which was the tip of `main`
  at the time, and independently implemented the same dev order. When #12
  merged, #13 conflicted. Both were correct; neither was redundant to write;
  the duplication was pure waste.
- **#14** branched from `02c84cd`, the *head of #12's branch*. By the time it
  was reviewed, `main` had moved twice. Merging it as submitted would have
  deleted four files and reverted #13 in full. Two automated reviews looked at
  it and both advised "rebase onto main" — which would have discarded merged
  work silently.

If your branch is not cut from current `main`, "make it match `main`" and
"keep my changes" start pulling in opposite directions, and no mechanical
resolution is correct any more.

## If `main` moves while your branch is open

Merge, do not rebase:

```bash
git fetch origin && git merge origin/main
```

A rebase rewrites shas a reviewer has already read, and on a branch that was
cut from unmerged work it drops that work without saying so.

## Before you start

Check whether an open pull request already touches the surface you are about
to change:

```bash
gh pr list --state open --json number,title,headRefName,files
```

If one does, say so and stop rather than implementing the same order twice.
Nothing will catch this for you. #12 and #13 were both correct, both worth
writing, and one of them was waste.

## One dev order per branch

Do not fold an adjacent fix into an open order because it is convenient. If a
governance document names the authorized surfaces for a change, changing
anything else needs an owner ruling first — say so in the PR body rather than
merging it quietly. See `docs/governance/` .

## Nothing enforces this. Check it yourself.

There is no bot and no gate. The owner merges every pull request by hand and
is the reviewer, deliberately — the same principle as the release automation,
which refuses to tag or publish on its own. So this file is the only thing
standing between you and the failure above. Before you open a pull request:

```bash
# The merge base must BE the tip of main, not merely an ancestor of it.
test "$(git merge-base HEAD origin/main)" = "$(git rev-parse origin/main)"   && echo "base is current" || echo "STALE — read this file again"
```

If the merge base turns out to be the head of an open pull request rather than
an old commit on `main`, you are stacked on unmerged work: do not rebase, see
above.

## Verifying locally

The release tooling refuses to run outside its supported matrix, so a default
interpreter newer than 3.12 fails these tests with
`unsupported Python version`, having found nothing wrong:

```bash
py -3.11 -m venv .venv311 && .venv311/Scripts/python -m pip install -e ".[dev]"
```

Full gates, matching CI:

```bash
ruff check .
mypy business --ignore-missing-imports
mypy musical_spatial_mapping --strict
mypy cnc_version --strict
pytest --cov=business --cov-report=term-missing --cov-fail-under=90
```
