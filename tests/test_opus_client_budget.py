"""Tests for opus_client.py: disk cache, ledger, budget cap, blinding, and retry."""

from __future__ import annotations

from pathlib import Path
import pytest

from courtroom.opus_client import BudgetExceededError, CourtClient, blind_payload
from courtroom.schemas import SchemaValidationError


def test_blind_payload_neutralizes_provenance() -> None:
    raw = "Compare Party A (production) vs Party B (independent). Check ours output."
    blinded = blind_payload(raw)
    assert "production" not in blinded.lower()
    assert "ours" not in blinded.lower()
    assert "Submission A" in blinded
    assert "Submission B" in blinded


def test_disk_cache_and_ledger_accounting(tmp_path: Path) -> None:
    calls = 0

    def factory(role: str, sys_p: str, usr_p: str) -> dict:
        nonlocal calls
        calls += 1
        return {
            "plan_id": "PLAN-001",
            "objections": [
                {
                    "id": "OBJ-1",
                    "item_id": "ITEM-1",
                    "role": "prosecutor",
                    "severity": "minor",
                    "attack": "Check bounds",
                    "required_evidence": "E1",
                }
            ],
        }

    client = CourtClient(
        ledger_path=tmp_path / "ledger.json",
        cache_dir=tmp_path / "cache",
        budget_usd=2.0,
        provider="mock",
    )

    first = client.call("prosecutor", "sys", "usr", "challenge", response_factory=factory)
    assert first["plan_id"] == "PLAN-001"
    assert calls == 1
    spend_after_first = client.current_spend()
    assert spend_after_first > 0.0

    # Identical call hits disk cache -> zero extra factory calls and zero extra cost
    second = client.call("prosecutor", "sys", "usr", "challenge", response_factory=factory)
    assert second == first
    assert calls == 1
    assert client.current_spend() == spend_after_first

    entries = client.read_ledger()
    assert len(entries) == 2
    assert entries[0]["cached"] is False
    assert entries[1]["cached"] is True
    assert entries[1]["cost_usd"] == 0.0


def test_budget_exceeded_hard_cap(tmp_path: Path) -> None:
    client = CourtClient(
        ledger_path=tmp_path / "ledger.json",
        cache_dir=tmp_path / "cache",
        budget_usd=0.0001,
        provider="mock",
    )

    called = False

    def factory() -> dict:
        nonlocal called
        called = True
        return {"plan_id": "PLAN-001", "objections": []}

    with pytest.raises(BudgetExceededError):
        client.call("prosecutor", "sys", "long prompt " * 50, "challenge", response_factory=factory)
    assert called is False


def test_retry_once_on_invalid_json_then_succeed(tmp_path: Path) -> None:
    attempts: list[int] = []

    def flaky_factory(role: str, sys_p: str, usr_p: str, attempt: int) -> str | dict:
        attempts.append(attempt)
        if attempt == 0:
            return "{not valid json"
        return {"plan_id": "PLAN-001", "objections": []}

    client = CourtClient(
        ledger_path=tmp_path / "ledger.json",
        cache_dir=tmp_path / "cache",
        budget_usd=2.0,
        provider="mock",
    )
    res = client.call("prosecutor", "sys", "usr", "challenge", response_factory=flaky_factory)
    assert res["plan_id"] == "PLAN-001"
    assert attempts == [0, 1]
    assert len(client.read_ledger()) == 2

    # Second failure after retry raises SchemaValidationError
    def always_bad() -> str:
        return "invalid json"

    with pytest.raises(SchemaValidationError):
        client.call(
            "prosecutor",
            "sys",
            "different prompt",
            "challenge",
            response_factory=always_bad,
        )
