"""Tests for Step 4 closing.py, reporting tools, and build_sample.py."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from courtroom.build_sample import build_sample_manifest
from courtroom.closing import LossGroupingError, run_closing_hearing, validate_closing_brief
from courtroom.law import record_owner_decision
from courtroom.list_losses import collect_losses, format_losses
from courtroom.opus_client import CourtClient
from courtroom.report import generate_report
from courtroom.show_title import format_title, get_title_record
from courtroom.show_trial import format_trial, load_trial


def _seed_round_with_losses(tmp_path: Path) -> tuple[Path, Path]:
    round_dir = tmp_path / "round-1"
    trials_dir = round_dir / "trials"
    trials_dir.mkdir(parents=True)

    trial_payload = {
        "doc_id": "DOC-2",
        "round_id": "round-1",
        "mode": "pipeline",
        "reused_from": None,
        "ours_a": {"status": "PENDING"},
        "independent_b": {"status": "REVOKED"},
        "disputed_fields": ["status"],
        "advocate_a": {"opening": "A", "rebuttal": "", "conceded_fields": [], "citations": []},
        "advocate_b": {"opening": "B", "rebuttal": "", "conceded_fields": [], "citations": []},
        "fact_check": [],
        "ruling": {
            "winner": "B",
            "field_rulings": {"status": {"winner": "B"}},
            "decisive_quote": "Permit is REVOKED",
            "decisive_quote_verified": True,
            "retried": False,
            "accepted_but_wrong": False,
            "rationale": "Explicitly revoked.",
            "cited_rules": ["R-1"],
        },
    }
    (trials_dir / "DOC-2.json").write_text(json.dumps(trial_payload), encoding="utf-8")
    (round_dir / "summary.json").write_text(
        json.dumps(
            {
                "round_id": "round-1",
                "mode": "pipeline",
                "total_docs": 2,
                "agreements": 1,
                "contested": 1,
                "party_a_wins": 0,
                "party_b_wins": 1,
                "splits": 0,
                "party_a_losses": ["DOC-2"],
                "party_a_fully_correct": 1,
                "accepted_but_wrong": 0,
                "void_rulings_retried": 0,
                "rule_tuning_score": 50.0,
                "round_cost_usd": 0.01,
                "baseline_check": {"passed": True},
            }
        ),
        encoding="utf-8",
    )

    law_dir = tmp_path / "law"
    record_owner_decision(law_dir, "OD-1", "2026-01-01", "Never publish wrong status.")
    return round_dir, law_dir


def test_closing_brief_grouping_invariants_and_corrections(tmp_path: Path) -> None:
    round_dir, law_dir = _seed_round_with_losses(tmp_path)

    # Missing loss raises LossGroupingError
    with pytest.raises(LossGroupingError):
        validate_closing_brief({"round_id": "round-1", "groups": []}, ["DOC-2"])

    # Duplicate loss across two groups raises LossGroupingError
    with pytest.raises(LossGroupingError):
        validate_closing_brief(
            {
                "round_id": "round-1",
                "groups": [
                    {
                        "group_id": "G1",
                        "title": "A",
                        "root_cause": "R1",
                        "loss_ids": ["DOC-2"],
                        "position": "fix_rule",
                        "facts": ["fact"],
                        "proposed_change": "fix",
                    },
                    {
                        "group_id": "G2",
                        "title": "B",
                        "root_cause": "R2",
                        "loss_ids": ["DOC-2"],
                        "position": "fix_code",
                        "facts": ["fact"],
                        "proposed_change": "fix",
                    },
                ],
            },
            ["DOC-2"],
        )

    # Corrected brief without explicit correction_statement raises LossGroupingError
    with pytest.raises(LossGroupingError):
        validate_closing_brief(
            {
                "round_id": "round-1",
                "amends_brief_id": "BRIEF-1",
                "groups": [
                    {
                        "group_id": "G1",
                        "title": "A",
                        "root_cause": "R1",
                        "loss_ids": ["DOC-2"],
                        "position": "fix_rule",
                        "facts": ["fact"],
                        "proposed_change": "fix",
                    }
                ],
            },
            ["DOC-2"],
        )

    brief_path = tmp_path / "BRIEF.json"
    brief_path.write_text(
        json.dumps(
            {
                "round_id": "round-1",
                "amends_brief_id": "BRIEF-0",
                "correction_statement": "Prior brief misstated rule R-1 line number; corrected here.",
                "groups": [
                    {
                        "group_id": "G1",
                        "title": "Missing REVOKED rule",
                        "root_cause": "law/rulebook.json",
                        "loss_ids": ["DOC-2"],
                        "position": "fix_rule",
                        "facts": ["Permit is REVOKED in source text."],
                        "proposed_change": "Enable R-REVOKE rule.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    tracker = tmp_path / "tracker.md"
    client = CourtClient(tmp_path / "ledger.json", tmp_path / "cache", budget_usd=5.0, provider="mock")
    verdict = run_closing_hearing(
        round_dir=round_dir,
        brief_path=brief_path,
        law_dir=law_dir,
        client=client,
        tracker_path=tracker,
    )
    assert verdict["decision"] == "continue"
    assert len(verdict["require_fix"]) == 1
    assert "Closing Hearing round-1" in tracker.read_text(encoding="utf-8")


def test_report_list_losses_show_tools_and_build_sample(tmp_path: Path) -> None:
    round_dir, _ = _seed_round_with_losses(tmp_path)

    rpt = generate_report(round_dir)
    assert "Rule-Tuning Score" in rpt
    assert "DOC-2" in rpt

    losses = collect_losses(round_dir)
    assert len(losses) == 1
    assert losses[0]["cited_rules"] == ["R-1"]
    assert "Permit is REVOKED" in format_losses(losses)

    trial_txt = format_trial(load_trial(round_dir, "DOC-2"))
    assert "Decisive Quote [VERIFIED]" in trial_txt

    corpus = tmp_path / "corpus"
    (corpus / "permits").mkdir(parents=True)
    (corpus / "permits" / "D1.txt").write_text("Permit D1 GRANTED.", encoding="utf-8")
    (corpus / "permits" / "D2.txt").write_text("Permit D2 REVOKED.", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest = build_sample_manifest(corpus, manifest_path, limit=10, seed=7)
    assert manifest["sample_size"] == 2

    title_txt = format_title(get_title_record(manifest_path, "D1"))
    assert "Permit D1 GRANTED." in title_txt
