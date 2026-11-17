"""List all Party A losses in a round with decisive quotes and cited rule IDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def collect_losses(round_dir: str | Path) -> list[dict[str, Any]]:
    """Collect detailed loss entries from round-N/trials/*.json."""
    trials_dir = Path(round_dir) / "trials"
    losses: list[dict[str, Any]] = []
    if not trials_dir.is_dir():
        return losses

    for tf in sorted(trials_dir.glob("*.json")):
        trial = json.loads(tf.read_text(encoding="utf-8"))
        ruling = trial.get("ruling", {})
        if ruling.get("winner") in ("B", "split"):
            losses.append(
                {
                    "doc_id": trial["doc_id"],
                    "winner": ruling["winner"],
                    "disputed_fields": trial.get("disputed_fields", []),
                    "decisive_quote": ruling.get("decisive_quote", ""),
                    "decisive_quote_verified": ruling.get("decisive_quote_verified", False),
                    "cited_rules": ruling.get("cited_rules", []),
                    "rationale": ruling.get("rationale", ""),
                    "trial_path": str(tf),
                }
            )
    return losses


def format_losses(losses: list[dict[str, Any]]) -> str:
    if not losses:
        return "No losses recorded in this round.\n"
    lines = [f"Losses ({len(losses)}):"]
    for item in losses:
        badge = "VERIFIED" if item["decisive_quote_verified"] else "UNVERIFIED"
        rules = ", ".join(item["cited_rules"]) or "none"
        lines.append(
            f"- {item['doc_id']} (winner={item['winner']}, fields={item['disputed_fields']}, "
            f"rules=[{rules}], quote[{badge}]=\"{item['decisive_quote']}\") -> {item['trial_path']}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List losses in a Courtroom round.")
    parser.add_argument("--round", required=True, help="Round directory (e.g. round-1).")
    parser.add_argument("--json", action="store_true", help="Output raw JSON.")
    args = parser.parse_args(argv)

    losses = collect_losses(args.round)
    if args.json:
        print(json.dumps(losses, indent=2))
    else:
        print(format_losses(losses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
