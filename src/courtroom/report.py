"""Round summary reporting & baseline comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def generate_report(round_dir: str | Path, previous_round_dir: str | Path | None = None) -> str:
    """Format a Markdown summary report for an evaluation court round."""
    r_path = Path(round_dir)
    summary_file = r_path / "summary.json"
    if not summary_file.is_file():
        raise FileNotFoundError(f"Round summary not found: {summary_file}")
    summary: dict[str, Any] = json.loads(summary_file.read_text(encoding="utf-8"))

    lines = [
        f"# Courtroom Round Report: {summary.get('round_id', r_path.name)}",
        f"- **Mode**: `{summary.get('mode', 'pipeline')}`",
        f"- **Total Docs**: {summary.get('total_docs', 0)}",
        f"- **Agreements**: {summary.get('agreements', 0)}",
        f"- **Contested**: {summary.get('contested', 0)}",
        f"- **Party A Wins**: {summary.get('party_a_wins', 0)}",
        f"- **Party B Wins (Losses)**: {summary.get('party_b_wins', 0)}",
        f"- **Splits**: {summary.get('splits', 0)}",
        f"- **Party A Fully Correct**: {summary.get('party_a_fully_correct', 0)}",
        f"- **ACCEPTED-but-wrong**: {summary.get('accepted_but_wrong', 0)}",
        f"- **Void Rulings Retried**: {summary.get('void_rulings_retried', 0)}",
        f"- **Rule-Tuning Score**: {summary.get('rule_tuning_score', 0.0)}%",
        f"- **Round Cost (USD)**: ${summary.get('round_cost_usd', 0.0):.4f}",
    ]

    baseline = summary.get("baseline_check", {})
    if previous_round_dir is not None and (Path(previous_round_dir) / "summary.json").is_file():
        prev = json.loads((Path(previous_round_dir) / "summary.json").read_text(encoding="utf-8"))
        prev_correct = prev.get("party_a_fully_correct", 0)
        prev_score = prev.get("rule_tuning_score", 0.0)
        passed = (
            summary.get("accepted_but_wrong", 0) == 0
            and summary.get("party_a_fully_correct", 0) >= prev_correct
            and summary.get("rule_tuning_score", 0.0) >= prev_score
        )
        lines.append(
            f"- **Baseline vs {Path(previous_round_dir).name}**: "
            f"{'PASS' if passed else 'FAIL'} "
            f"(correct {summary.get('party_a_fully_correct', 0)} vs {prev_correct}, "
            f"score {summary.get('rule_tuning_score', 0.0)}% vs {prev_score}%)"
        )
    elif baseline:
        lines.append(
            f"- **Baseline Check**: {'PASS' if baseline.get('passed') else 'FAIL'}"
        )

    losses = summary.get("party_a_losses", [])
    if losses:
        lines.append(f"- **Remaining Losses ({len(losses)})**: {', '.join(losses)}")
    else:
        lines.append("- **Remaining Losses**: None")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize an Evaluation Court round.")
    parser.add_argument("--round", required=True, help="Round directory (e.g. round-1).")
    parser.add_argument("--previous-round", help="Optional previous round for comparison.")
    args = parser.parse_args(argv)
    print(generate_report(args.round, args.previous_round))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
