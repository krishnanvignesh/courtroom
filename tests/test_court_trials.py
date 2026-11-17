"""Tests for Step 3c court.py: full trial order, void retry, appeals, reuse-b, and modes."""

from __future__ import annotations

import json
from pathlib import Path

from courtroom.court import run_court_round
from courtroom.law import record_owner_decision
from courtroom.opus_client import CourtClient


def _write_fixture_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    law_dir = tmp_path / "law"
    record_owner_decision(law_dir, "OD-1", "2026-01-01", "Source text controls over defaults.")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "DOC-AGREE",
                        "text": "<p>Permit 101 is GRANTED permanently.</p>",
                        "oracle_hint": {"status": "GRANTED"},
                    },
                    {
                        "doc_id": "DOC-DISPUTE",
                        "text": "<p>Permit 202 is REVOKED immediately due to noncompliance.</p>",
                        "oracle_hint": {"status": "REVOKED"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    ours = tmp_path / "ours-r1.json"
    ours.write_text(
        json.dumps(
            {
                "DOC-AGREE": {"status": "GRANTED"},
                "DOC-DISPUTE": {"status": "PENDING"},
            }
        ),
        encoding="utf-8",
    )
    return law_dir, manifest, ours


def test_court_trial_void_retry_appeals_and_reuse_b(tmp_path: Path) -> None:
    law_dir, manifest, ours = _write_fixture_workspace(tmp_path)
    client = CourtClient(tmp_path / "ledger.json", tmp_path / "cache", budget_usd=10.0, provider="mock")

    judge_calls = 0

    def custom_factory(role: str, sys_p: str, usr_p: str) -> dict:
        nonlocal judge_calls
        if role == "generator":
            return {
                "doc_id": "DOC-AGREE" if "DOC-AGREE" in usr_p else "DOC-DISPUTE",
                "extraction": {"status": "GRANTED" if "DOC-AGREE" in usr_p else "REVOKED"},
                "blind_assertions": [],
            }
        if role == "advocate_a":
            return {
                "opening": "Submission A applied fallback default.",
                "rebuttal": "No contrary clause seen.",
                "conceded_fields": [],
                "citations": [{"field": "status", "quote": "HALLUCINATED QUOTE NOT IN DOC"}],
            }
        if role == "advocate_b":
            return {
                "opening": "Source explicitly revokes permit 202.",
                "rebuttal": "Default does not override explicit revocation.",
                "conceded_fields": [],
                "citations": [{"field": "status", "quote": "Permit 202 is REVOKED immediately"}],
            }
        if role == "trial_judge":
            judge_calls += 1
            if judge_calls == 1:
                # First call cites unverified quote -> must trigger automatic VOID retry once!
                return {
                    "winner": "B",
                    "field_rulings": {"status": {"winner": "B"}},
                    "decisive_quote": "FABRICATED JUDGE QUOTE",
                    "accepted_but_wrong": False,
                    "rationale": "First attempt with unverified quote.",
                    "cited_rules": ["OD-1"],
                }
            if judge_calls == 2:
                # Second call (retry) uses the Bailiff-verified quote
                return {
                    "winner": "B",
                    "field_rulings": {"status": {"winner": "B"}},
                    "decisive_quote": "Permit 202 is REVOKED immediately",
                    "accepted_but_wrong": False,
                    "rationale": "Verified quote proves REVOKED.",
                    "cited_rules": ["OD-1"],
                }
            # Third call (appeal)
            return {
                "winner": "A",
                "field_rulings": {"status": {"winner": "A"}},
                "decisive_quote": "Permit 202 is REVOKED immediately",
                "accepted_but_wrong": False,
                "rationale": "Appeal upheld for A under test override.",
                "cited_rules": ["OD-1"],
            }
        raise AssertionError(f"Unexpected role {role}")

    round1_dir = tmp_path / "round-1"
    summary1 = run_court_round(
        ours_path=ours,
        manifest_path=manifest,
        law_dir=law_dir,
        out_dir=round1_dir,
        client=client,
        response_factory=custom_factory,
    )

    assert summary1["agreements"] == 1
    assert summary1["party_b_wins"] == 1
    assert summary1["void_rulings_retried"] == 1
    assert summary1["accepted_but_wrong"] == 0
    assert judge_calls == 2

    trial_dispute = json.loads((round1_dir / "trials" / "DOC-DISPUTE.json").read_text(encoding="utf-8"))
    assert trial_dispute["ruling"]["retried"] is True
    assert trial_dispute["ruling"]["decisive_quote_verified"] is True
    assert trial_dispute["fact_check"][0]["status"] == "UNVERIFIED"
    assert trial_dispute["fact_check"][1]["status"] == "VERIFIED"

    # Now test Round 2 with --reuse-b and --appeals
    appeals_file = tmp_path / "appeals.json"
    appeals_file.write_text(
        json.dumps(
            {
                "DOC-DISPUTE": {
                    "field": "status",
                    "appeal_quote": "Permit 202 is REVOKED immediately",
                    "argument": "Test appeal check",
                }
            }
        ),
        encoding="utf-8",
    )

    gen_calls_before = sum(1 for e in client.read_ledger() if e["role"] == "generator")
    round2_dir = tmp_path / "round-2"
    summary2 = run_court_round(
        ours_path=ours,
        manifest_path=manifest,
        law_dir=law_dir,
        out_dir=round2_dir,
        client=client,
        reuse_b_dir=round1_dir,
        previous_round_dir=round1_dir,
        appeals_path=appeals_file,
        response_factory=custom_factory,
    )
    gen_calls_after = sum(1 for e in client.read_ledger() if e["role"] == "generator")
    assert gen_calls_after == gen_calls_before  # Party B reused at zero generator calls
    assert summary2["party_a_wins"] == 1  # Appeal overturned DOC-DISPUTE to A
    assert summary2["baseline_check"]["passed"] is True

    appealed_trial = json.loads((round2_dir / "trials" / "DOC-DISPUTE.json").read_text(encoding="utf-8"))
    assert appealed_trial["appeal"]["outcome"] == "overturned"
    assert appealed_trial["appeal"]["appeal_verified"] is True


def test_software_and_architecture_modes_court_round(tmp_path: Path) -> None:
    law_dir = tmp_path / "law"
    record_owner_decision(law_dir, "OD-1", "2026-01-01", "All blind spec tests must pass.")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "SPEC-AUTH",
                        "text": "Token expiry MUST reject expired JWT tokens with HTTP 401.",
                        "oracle_hint": {"reject_expired": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ours = tmp_path / "ours-sw.json"
    ours.write_text(json.dumps({"SPEC-AUTH": {"reject_expired": True}}), encoding="utf-8")

    client = CourtClient(tmp_path / "ledger.json", tmp_path / "cache", budget_usd=5.0, provider="mock")
    summary = run_court_round(
        ours_path=ours,
        manifest_path=manifest,
        law_dir=law_dir,
        out_dir=tmp_path / "round-sw",
        client=client,
        mode="software",
    )
    assert summary["mode"] == "software"
    assert summary["agreements"] == 1
