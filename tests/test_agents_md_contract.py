"""Repo-local contract for ``AGENTS.md``.

Validates the instruction file that lives in this repository. Does not import
or depend on ``scripts/scaffold_agents_md.py``, which is not part of
CNC Production Shop; that scaffolder is tested in ``portfolio-repo-tools``.
Existing CI already runs pytest over ``tests/``.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def _body() -> str:
    return AGENTS.read_text(encoding="utf-8")


def test_agents_md_exists() -> None:
    assert AGENTS.is_file()


def test_agents_md_names_the_actual_repository() -> None:
    first = _body().splitlines()[0]
    assert first == "# Agent instructions — CNC Production Shop"


def test_agents_md_requires_branching_from_main() -> None:
    body = _body()
    assert "## Branch from current `main`. Always." in body
    assert "origin/main" in body


def test_agents_md_has_pr_self_check() -> None:
    body = _body()
    assert "## Nothing enforces this. Check it yourself." in body
    assert "Before you open a pull request" in body
    assert "The merge base must BE the tip of main" in body


def test_agents_md_delegates_to_claude_without_copying_authority() -> None:
    body = _body()
    assert "`CLAUDE.md`" in body
    assert "applies too" in body


def test_agents_md_contains_no_unfilled_scaffolder_todos() -> None:
    body = _body()
    assert "<!-- INCIDENTS" not in body
    assert "<!-- VERIFICATION GATES" not in body
