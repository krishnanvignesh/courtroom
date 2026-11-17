"""Tests for Step 3a replay_gate.py and blast-radius contract enforcement."""

from __future__ import annotations

import json
from pathlib import Path

from courtroom.replay_gate import run_replay_gate


def test_replay_gate_exact_expectation_and_unpredicted_diff(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(
            {
                "DOC-1": {"status": "PENDING"},
                "DOC-2": {"status": "PENDING"},
            }
        ),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(
            {
                "DOC-1": {"status": "GRANTED"},
                "DOC-2": {"status": "PENDING"},
            }
        ),
        encoding="utf-8",
    )

    ok = run_replay_gate(baseline, candidate, expectations=["DOC-1.status=GRANTED"])
    assert ok["passed"] is True
    assert len(ok["expected_matched"]) == 1
    assert ok["unpredicted_diffs"] == []

    # Unpredicted change fails the gate
    candidate.write_text(
        json.dumps(
            {
                "DOC-1": {"status": "GRANTED"},
                "DOC-2": {"status": "REVOKED"},
            }
        ),
        encoding="utf-8",
    )
    fail_unpredicted = run_replay_gate(baseline, candidate, expectations=["DOC-1.status=GRANTED"])
    assert fail_unpredicted["passed"] is False
    assert len(fail_unpredicted["unpredicted_diffs"]) == 1

    # Missing expected change fails the gate
    fail_missing = run_replay_gate(
        baseline,
        candidate,
        expectations=["DOC-1.status=GRANTED", "DOC-2.status=REVOKED", "DOC-3.status=HOLD"],
    )
    assert fail_missing["passed"] is False
    assert len(fail_missing["missing_expectations"]) == 1


    # Internal _meta keys are ignored by default unless include_meta=True
    baseline.write_text(
        json.dumps({"DOC-1": {"status": "PENDING", "_meta": {"applied_rules": ["R0"]}}}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"DOC-1": {"status": "GRANTED", "_meta": {"applied_rules": ["R0", "R1"]}}}),
        encoding="utf-8",
    )
    meta_ignored = run_replay_gate(baseline, candidate, expectations=["DOC-1.status=GRANTED"])
    assert meta_ignored["passed"] is True
    meta_checked = run_replay_gate(
        baseline, candidate, expectations=["DOC-1.status=GRANTED"], include_meta=True
    )
    assert meta_checked["passed"] is False


def test_replay_gate_software_blast_radius(tmp_path: Path) -> None:
    baseline = tmp_path / "b.json"
    candidate = tmp_path / "c.json"
    baseline.write_text('{"T1": {"passed": true}}', encoding="utf-8")
    candidate.write_text('{"T1": {"passed": true}}', encoding="utf-8")

    plan = tmp_path / "PLAN-002.json"
    plan.write_text(
        json.dumps(
            {
                "plan_id": "PLAN-002",
                "mode": "software",
                "goal": "Update billing helper",
                "blast_radius": {
                    "allowed_files": ["src/billing/*.py", "tests/test_billing.py"],
                    "forbidden_files": ["src/auth/*"],
                    "expected_deltas": {},
                },
                "items": [
                    {
                        "id": "ITEM-1",
                        "title": "Fix tax rounding",
                        "change": "Use Decimal.quantize",
                        "rationale": "Avoid float drift",
                        "evidence_ids": ["E1"],
                        "risks": [],
                        "verification": "pytest tests/test_billing.py",
                    }
                ],
                "evidence": [
                    {"id": "E1", "source": "src/billing/tax.py", "finding": "Uses float"}
                ],
            }
        ),
        encoding="utf-8",
    )

    clean = run_replay_gate(
        baseline,
        candidate,
        plan_path=plan,
        changed_files=["src/billing/tax.py", "tests/test_billing.py"],
    )
    assert clean["passed"] is True

    violated = run_replay_gate(
        baseline,
        candidate,
        plan_path=plan,
        changed_files=["src/billing/tax.py", "src/auth/tokens.py"],
    )
    assert violated["passed"] is False
    assert len(violated["blast_radius_violations"]) == 2
