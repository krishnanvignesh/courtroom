"""Step 4: Closing Hearing (exhaustive loss-group validation & judge verdict)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from courtroom.agents import build_prompt, default_mock_factory
from courtroom.law import assemble_law
from courtroom.opus_client import DEFAULT_COURT_MODEL, CourtClient
from courtroom.schemas import validate_schema


class LossGroupingError(ValueError):
    """Raised when a closing brief misses losses, duplicates losses, or omits correction."""


def load_round_losses(round_dir: str | Path) -> list[str]:
    """Load the ordered list of Party A loss doc_ids from round-N."""
    r_path = Path(round_dir)
    summary_file = r_path / "summary.json"
    if summary_file.is_file():
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        if "party_a_losses" in summary:
            return list(summary["party_a_losses"])

    losses: list[str] = []
    trials_dir = r_path / "trials"
    if trials_dir.is_dir():
        for tf in sorted(trials_dir.glob("*.json")):
            trial = json.loads(tf.read_text(encoding="utf-8"))
            if trial.get("ruling", {}).get("winner") in ("B", "split"):
                losses.append(str(trial["doc_id"]))
    return losses


def validate_closing_brief(
    brief_data: dict[str, Any],
    round_losses: list[str],
) -> dict[str, Any]:
    """Validate brief schema, exhaustive 1-to-1 loss grouping, and correction statements."""
    brief = validate_schema(brief_data, "closing_brief")

    if brief.get("amends_brief_id") and not (
        brief.get("correction_statement") and str(brief["correction_statement"]).strip()
    ):
        raise LossGroupingError(
            "Corrected brief specifies 'amends_brief_id' and must include explicit 'correction_statement'."
        )

    expected = set(round_losses)
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    unexpected: list[str] = []

    for grp in brief.get("groups", []):
        gid = grp["group_id"]
        for lid in grp["loss_ids"]:
            if lid not in expected:
                unexpected.append(lid)
            if lid in seen:
                duplicates.append(f"{lid} (in {seen[lid]} and {gid})")
            else:
                seen[lid] = gid

    missing = sorted(expected - set(seen.keys()))
    errors: list[str] = []
    if missing:
        errors.append(f"Unassigned losses missing from brief: {missing}")
    if duplicates:
        errors.append(f"Losses assigned to multiple groups: {duplicates}")
    if unexpected:
        errors.append(f"Unknown loss_ids not in round losses: {sorted(set(unexpected))}")

    if errors:
        raise LossGroupingError("; ".join(errors))
    return brief


def append_tracker(
    tracker_path: str | Path,
    round_id: str,
    verdict: dict[str, Any],
) -> None:
    """Append judge closing decision to the progress tracker."""
    t_path = Path(tracker_path)
    t_path.parent.mkdir(parents=True, exist_ok=True)
    existing = t_path.read_text(encoding="utf-8") if t_path.is_file() else "# Progress Tracker\n"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fixes = verdict.get("require_fix", [])
    fix_lines = "\n".join(
        f"  - [{f['group_id']}] {f['rule_or_file']}: {f['action']}" for f in fixes
    )
    entry = (
        f"\n## Closing Hearing {round_id} ({ts})\n"
        f"- Decision: `{verdict['decision']}`\n"
        f"- Summary: {verdict['summary']}\n"
    )
    if fix_lines:
        entry += f"- Require Fix:\n{fix_lines}\n"
    t_path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")


def run_closing_hearing(
    round_dir: str | Path,
    brief_path: str | Path,
    law_dir: str | Path,
    client: CourtClient,
    tracker_path: str | Path | None = None,
    out_path: str | Path | None = None,
    response_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run Step 4 Closing Hearing over a round's losses and closing brief."""
    r_path = Path(round_dir)
    raw_brief = json.loads(Path(brief_path).read_text(encoding="utf-8"))
    round_losses = load_round_losses(r_path)
    brief = validate_closing_brief(raw_brief, round_losses)

    law_text = assemble_law(law_dir)
    summary = (
        json.loads((r_path / "summary.json").read_text(encoding="utf-8"))
        if (r_path / "summary.json").is_file()
        else {"round_id": r_path.name}
    )
    mode = summary.get("mode", "pipeline")
    factory = response_factory or (default_mock_factory if client.provider == "mock" else None)

    sys_prompt, usr_prompt, schema_name = build_prompt(
        "closing_judge",
        mode=mode,
        law=law_text,
        round_summary=summary,
        brief=brief,
    )
    verdict = client.call(
        role="closing_judge",
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        schema_name=schema_name,
        response_factory=factory,
    )

    target = Path(out_path) if out_path else (r_path / "closing_verdict.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")

    if tracker_path:
        append_tracker(tracker_path, r_path.name, verdict)

    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step 4: Courtroom Closing Hearing CLI.")
    parser.add_argument("--round", required=True, help="Round directory (e.g. round-1).")
    parser.add_argument("--brief", required=True, help="Closing brief JSON path (BRIEF.json).")
    parser.add_argument("--law-dir", required=True, help="Law directory with Parts 0-3 files.")
    parser.add_argument("--tracker", help="Optional tracker.md path to record closing decision.")
    parser.add_argument("--out", help="Optional output path for closing_verdict.json.")
    parser.add_argument("--ledger", default=".courtroom_data/ledger.json")
    parser.add_argument("--cache-dir", default=".courtroom_data/cache")
    parser.add_argument("--budget-usd", type=float, default=5.0)
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--model", default=DEFAULT_COURT_MODEL)
    args = parser.parse_args(argv)

    client = CourtClient(
        ledger_path=args.ledger,
        cache_dir=args.cache_dir,
        budget_usd=args.budget_usd,
        model=args.model,
        provider=args.provider,
    )
    verdict = run_closing_hearing(
        round_dir=args.round,
        brief_path=args.brief,
        law_dir=args.law_dir,
        client=client,
        tracker_path=args.tracker,
        out_path=args.out,
    )
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
