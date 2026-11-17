"""Tests for Step 1 Plan Court and Markdown/YAML compilation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from courtroom.law import load_case_law, record_owner_decision
from courtroom.markdown_compiler import compile_plan_file, compile_rebuttal_file
from courtroom.opus_client import CourtClient
from courtroom.plan_court import RebuttalValidationError, challenge, judge
from courtroom.schemas import SchemaValidationError


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path]:
    law_dir = tmp_path / "law"
    record_owner_decision(law_dir, "OD-1", "2026-01-01", "Delegate narrow defaults to court.")
    src_file = tmp_path / "src_module.py"
    src_file.write_text("def handle_webhook(event_id):\n    return event_id\n", encoding="utf-8")
    return law_dir, tmp_path


def test_markdown_plan_and_rebuttal_compilation(tmp_path: Path) -> None:
    plan_md = tmp_path / "PLAN-007.md"
    plan_md.write_text(
        """---
plan_id: PLAN-007
mode: software
goal: Enforce webhook idempotency via event_id cache.
blast_radius:
  allowed_files:
    - src_module.py
  forbidden_files:
    - auth/*
---

## Evidence
- E1 | source: src_module.py | ast_ref: src_module.py:handle_webhook | finding: Handler currently returns raw event_id without dedup.

## Items
### ITEM-1: Add deduplication check
- change: Store processed event_id before running handler side effects.
- rationale: Prevents duplicate execution on retries.
- evidence_ids: E1
- risks: Memory growth if unbounded
- verification: pytest tests/test_webhook.py
""",
        encoding="utf-8",
    )
    compiled = compile_plan_file(plan_md)
    assert compiled["plan_id"] == "PLAN-007"
    assert compiled["mode"] == "software"
    assert compiled["evidence"][0]["ast_ref"] == "src_module.py:handle_webhook"

    reb_md = tmp_path / "PLAN-007.rebuttal.md"
    reb_md.write_text(
        """---
plan_id: PLAN-007
---

### OBJ-1 (item: ITEM-1)
- stance: concede
- argument: Valid point about unbounded memory.
- amendment: Cap LRU cache to 10,000 entries.

### OBJ-2 (item: ITEM-1)
- stance: defend
- argument: Single stdlib OrderedDict requires zero external deps.
- evidence_ids: E1
""",
        encoding="utf-8",
    )
    reb = compile_rebuttal_file(reb_md)
    assert len(reb["responses"]) == 2
    assert reb["responses"][0]["stance"] == "concede"
    assert reb["responses"][1]["evidence_ids"] == ["E1"]


def test_plan_challenge_rebuttal_validation_and_judge_verdict(tmp_path: Path) -> None:
    law_dir, repo_root = _setup_workspace(tmp_path)
    plan_path = tmp_path / "PLAN-001.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "PLAN-001",
                "mode": "architecture",
                "goal": "Introduce webhook idempotency",
                "items": [
                    {
                        "id": "ITEM-1",
                        "title": "Deduplicate events",
                        "change": "Track seen event_id in BoundedCache",
                        "rationale": "At-least-once delivery causes duplicates",
                        "evidence_ids": ["E1"],
                        "risks": ["Cache eviction window"],
                        "verification": "Unit test duplicate event replay",
                    }
                ],
                "evidence": [
                    {
                        "id": "E1",
                        "source": "src_module.py",
                        "ast_ref": "src_module.py:handle_webhook",
                        "finding": "No dedup check exists today",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    client = CourtClient(tmp_path / "ledger.json", tmp_path / "cache", budget_usd=5.0, provider="mock")
    chal = challenge(plan_path, law_dir, client, repo_root=repo_root)
    assert len(chal["objections"]) == 2
    assert {o["role"] for o in chal["objections"]} == {"prosecutor", "public_defender"}

    # Missing objection response fails validation
    bad_reb = tmp_path / "bad.rebuttal.json"
    bad_reb.write_text(
        json.dumps({"plan_id": "PLAN-001", "responses": []}),
        encoding="utf-8",
    )
    with pytest.raises(RebuttalValidationError):
        judge(
            plan_path,
            bad_reb,
            tmp_path / "PLAN-001.challenge.json",
            law_dir,
            client,
            repo_root=repo_root,
        )

    # Valid rebuttal + Judge recording a delegated precedent
    good_reb = tmp_path / "PLAN-001.rebuttal.json"
    good_reb.write_text(
        json.dumps(
            {
                "plan_id": "PLAN-001",
                "responses": [
                    {
                        "objection_id": "OBJ-1",
                        "item_id": "ITEM-1",
                        "stance": "defend",
                        "argument": "AST citation E1 proves handler lacks idempotency.",
                        "evidence_ids": ["E1"],
                    },
                    {
                        "objection_id": "OBJ-2",
                        "item_id": "ITEM-1",
                        "stance": "concede",
                        "argument": "Keep implementation to in-memory LRU without Redis.",
                        "amendment": "Use functools/OrderedDict in memory only.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def judge_with_precedent(role: str, sys_p: str, usr_p: str) -> dict:
        return {
            "plan_id": "PLAN-001",
            "overall": "approved_with_conditions",
            "item_rulings": [
                {
                    "item_id": "ITEM-1",
                    "verdict": "approve_with_conditions",
                    "conditions": ["Must stay in-memory only"],
                    "rationale": "Satisfies Prosecutor risk and Public Defender YAGNI.",
                }
            ],
            "binding_conditions": ["Must stay in-memory only"],
            "new_precedents": [
                {
                    "id": "PREC-042",
                    "delegation_ref": "OD-1",
                    "holding": "Single-instance webhook idempotency uses bounded LRU before external store.",
                    "scope": "webhooks",
                }
            ],
        }

    verdict = judge(
        plan_path,
        good_reb,
        tmp_path / "PLAN-001.challenge.json",
        law_dir,
        client,
        repo_root=repo_root,
        response_factory=judge_with_precedent,
    )
    assert verdict["overall"] == "approved_with_conditions"
    assert any(p["id"] == "PREC-042" for p in load_case_law(law_dir))

    # Rejecting an item without overall='rejected' must raise SchemaValidationError
    def inconsistent_judge() -> dict:
        return {
            "plan_id": "PLAN-001",
            "overall": "approved",
            "item_rulings": [
                {
                    "item_id": "ITEM-1",
                    "verdict": "reject",
                    "conditions": [],
                    "rationale": "Missing evidence",
                }
            ],
            "binding_conditions": [],
            "new_precedents": [],
        }

    with pytest.raises(SchemaValidationError):
        judge(
            plan_path,
            good_reb,
            tmp_path / "PLAN-001.challenge.json",
            law_dir,
            client,
            out_path=tmp_path / "bad_verdict.json",
            repo_root=repo_root,
            response_factory=inconsistent_judge,
        )
