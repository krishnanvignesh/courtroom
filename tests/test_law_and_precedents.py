"""Tests for law.py: Parts 0-3 hierarchy, append-only owner decisions, and precedents."""

from __future__ import annotations

from pathlib import Path
import pytest

from courtroom.law import (
    assemble_law,
    bump_rulebook_version,
    record_court_precedent,
    record_owner_decision,
    validate_owner_decisions_append_only,
)


def test_assemble_law_precedence_and_disabled_rules(tmp_path: Path) -> None:
    law_dir = tmp_path / "law"
    record_owner_decision(law_dir, "OD-1", "2026-01-01", "Original owner rule.")
    record_owner_decision(
        law_dir, "OD-2", "2026-02-01", "Updated owner rule.", supersedes="OD-1"
    )
    record_court_precedent(
        law_dir,
        precedent_id="PREC-010",
        delegation_ref="OD-2",
        holding="Idempotency keys required on webhook handlers.",
        scope="webhooks",
    )
    bump_rulebook_version(
        law_dir,
        new_version="0.2.0",
        changelog_entry="Added enabled + disabled sample rules",
        rule_updates=[
            {
                "id": "R-ACTIVE",
                "owner": "arch",
                "status": "active",
                "enabled": True,
                "stage": "derive",
                "description": "Binding rule",
                "params": {},
            },
            {
                "id": "R-DRAFT",
                "owner": "arch",
                "status": "proposed",
                "enabled": False,
                "stage": "derive",
                "description": "Unapproved draft",
                "params": {},
            },
        ],
    )
    (law_dir / "conventions.md").write_text("- Keep diffs minimal.\n", encoding="utf-8")

    assembled = assemble_law(law_dir)
    p0 = assembled.index("# PART 0:")
    p1 = assembled.index("# PART 1:")
    p2 = assembled.index("# PART 2:")
    p3 = assembled.index("# PART 3:")
    app = assembled.index("# NON-BINDING APPENDIX:")
    assert p0 < p1 < p2 < p3 < app

    assert "OD-1 [SUPERSEDED]" in assembled
    assert "OD-2 [ACTIVE]" in assembled
    assert "decided by the court under OD-2" in assembled
    assert "[R-ACTIVE]" in assembled
    assert "[DISABLED PROPOSAL: R-DRAFT]" in assembled


def test_owner_decisions_append_only_enforcement() -> None:
    orig = "# Owner Decisions\n\n## 2026-01-01 | OD-1\n> First rule.\n"
    assert validate_owner_decisions_append_only(orig) == []

    # Editing an earlier entry breaks append-only invariant
    edited = "# Owner Decisions\n\n## 2026-01-01 | OD-1\n> Mutated rule.\n"
    errs = validate_owner_decisions_append_only(edited, previous_md_text=orig)
    assert any("append-only" in e.lower() for e in errs)

    # Chronological inversion fails
    out_of_order = orig + "\n## 2025-12-01 | OD-2\n> Backdated.\n"
    errs2 = validate_owner_decisions_append_only(out_of_order, previous_md_text=orig)
    assert any("earlier" in e.lower() for e in errs2)
