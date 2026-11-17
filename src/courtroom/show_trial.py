"""Display full trial transcript, Bailiff fact-check badges, and Judge ruling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_trial(round_dir: str | Path, doc_id: str) -> dict[str, Any]:
    """Load trial JSON for doc_id from round-N/trials/<doc_id>.json."""
    trial_path = Path(round_dir) / "trials" / f"{doc_id}.json"
    if not trial_path.is_file():
        raise FileNotFoundError(f"Trial file not found: {trial_path}")
    return json.loads(trial_path.read_text(encoding="utf-8"))


def format_trial(trial: dict[str, Any]) -> str:
    ruling = trial.get("ruling", {})
    lines = [
        f"=== Trial: {trial['doc_id']} (round={trial['round_id']}, mode={trial.get('mode', 'pipeline')}) ===",
        f"Reused From: {trial.get('reused_from') or 'fresh'}",
        f"Disputed Fields: {trial.get('disputed_fields', [])}",
        f"Party A (ours): {json.dumps(trial.get('ours_a', {}), sort_keys=True)}",
        f"Party B (independent): {json.dumps(trial.get('independent_b', {}), sort_keys=True)}",
        "",
        "--- Advocate A ---",
        f"Opening: {trial['advocate_a'].get('opening', '')}",
        f"Rebuttal: {trial['advocate_a'].get('rebuttal', '')}",
        f"Conceded: {trial['advocate_a'].get('conceded_fields', [])}",
        "",
        "--- Advocate B ---",
        f"Opening: {trial['advocate_b'].get('opening', '')}",
        f"Rebuttal: {trial['advocate_b'].get('rebuttal', '')}",
        f"Conceded: {trial['advocate_b'].get('conceded_fields', [])}",
        "",
        "--- Bailiff Fact-Check ---",
    ]
    fact_check = trial.get("fact_check", [])
    if not fact_check:
        lines.append("(No citations checked)")
    else:
        for fc in fact_check:
            lines.append(
                f"[{fc['status']}] Party {fc['party']} ({fc['field']}): "
                f"\"{fc['quote_or_ref']}\" — {fc.get('details', '')}"
            )

    badge = "VERIFIED" if ruling.get("decisive_quote_verified") else "UNVERIFIED"
    lines.extend(
        [
            "",
            "--- Judge Ruling ---",
            f"Winner: {ruling.get('winner')}",
            f"Decisive Quote [{badge}]: \"{ruling.get('decisive_quote', '')}\"",
            f"Retried on Void: {ruling.get('retried', False)}",
            f"ACCEPTED-but-wrong: {ruling.get('accepted_but_wrong', False)}",
            f"Cited Rules: {ruling.get('cited_rules', [])}",
            f"Rationale: {ruling.get('rationale', '')}",
        ]
    )
    if trial.get("appeal"):
        app = trial["appeal"]
        lines.extend(
            [
                "",
                "--- Appeal ---",
                f"Outcome: {app.get('outcome')}",
                f"Appeal Quote Verified: {app.get('appeal_verified')}",
                f"Appeal Quote: \"{app.get('appeal_quote', '')}\"",
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Display full trial transcript for a document.")
    parser.add_argument("--round", required=True, help="Round directory (e.g. round-1).")
    parser.add_argument("--id", required=True, dest="doc_id", help="Document ID.")
    args = parser.parse_args(argv)

    trial = load_trial(args.round, args.doc_id)
    print(format_trial(trial))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
