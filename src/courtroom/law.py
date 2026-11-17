"""Living Case Law & Hierarchical Law Assembly (Parts 0-3)."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_OD_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*\|\s*(OD-\d+)\s*$")
_SUPERSEDES_RE = re.compile(r"^Supersedes:\s*(OD-\d+)\s*$", re.IGNORECASE)


@dataclass
class OwnerDecision:
    id: str
    date: str
    body: str
    supersedes: str | None = None
    raw_block: str = ""


def parse_owner_decisions(source: str | Path) -> list[OwnerDecision]:
    """Parse dated owner decisions from markdown text or file path."""
    text = (
        Path(source).read_text(encoding="utf-8")
        if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file())
        else str(source)
    )
    decisions: list[OwnerDecision] = []
    current_date: str | None = None
    current_id: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_date is None or current_id is None:
            return
        body_lines = list(current_lines)
        supersedes = None
        for line in body_lines:
            sup_match = _SUPERSEDES_RE.match(line.strip())
            if sup_match:
                supersedes = sup_match.group(1)
                break
        header = f"## {current_date} | {current_id}"
        raw = "\n".join([header, *body_lines]).strip()
        decisions.append(
            OwnerDecision(
                id=current_id,
                date=current_date,
                body="\n".join(body_lines).strip(),
                supersedes=supersedes,
                raw_block=raw,
            )
        )

    for line in text.splitlines():
        match = _OD_HEADER_RE.match(line.strip())
        if match:
            _flush()
            current_date = match.group(1)
            current_id = match.group(2)
            current_lines = []
        elif current_id is not None:
            current_lines.append(line)
    _flush()
    return decisions


def validate_owner_decisions_append_only(
    md_text: str,
    previous_md_text: str | None = None,
) -> list[str]:
    """Validate owner_decisions.md format, date ordering, and append-only invariant."""
    errors: list[str] = []
    decisions = parse_owner_decisions(md_text)
    if "## " in md_text and not decisions:
        errors.append("Found markdown headings but no valid '## YYYY-MM-DD | OD-N' owner decisions.")
        return errors

    seen_ids: set[str] = set()
    prev_date: date | None = None
    for dec in decisions:
        if dec.id in seen_ids:
            errors.append(f"Duplicate owner decision ID: {dec.id}")
        seen_ids.add(dec.id)
        try:
            parsed_date = date.fromisoformat(dec.date)
        except ValueError:
            errors.append(f"Invalid ISO date '{dec.date}' in {dec.id}")
            continue
        if prev_date is not None and parsed_date < prev_date:
            errors.append(
                f"Owner decision {dec.id} date {dec.date} is earlier than previous entry {prev_date.isoformat()}."
            )
        prev_date = parsed_date
        if not dec.body.strip():
            errors.append(f"Owner decision {dec.id} has empty body.")
        if dec.supersedes and dec.supersedes not in seen_ids:
            errors.append(f"Owner decision {dec.id} supersedes unknown/later ID {dec.supersedes}.")

    if previous_md_text is not None:
        prev_stripped = previous_md_text.rstrip()
        curr_stripped = md_text.rstrip()
        if prev_stripped and not curr_stripped.startswith(prev_stripped):
            errors.append(
                "owner_decisions.md violated append-only rule: existing entries were modified or removed."
            )

    return errors


def record_owner_decision(
    law_dir: str | Path,
    decision_id: str,
    date_str: str,
    verbatim_quote: str,
    supersedes: str | None = None,
) -> Path:
    """Append a dated verbatim owner decision without editing prior entries."""
    path = Path(law_dir) / "owner_decisions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else "# Owner Decisions (Part 0 Law)\n"

    block_lines = [f"## {date_str} | {decision_id}"]
    if supersedes:
        block_lines.append(f"Supersedes: {supersedes}")
    block_lines.append(f"> {verbatim_quote.strip()}")
    new_block = "\n".join(block_lines) + "\n"

    updated = existing.rstrip() + "\n\n" + new_block
    errors = validate_owner_decisions_append_only(updated, previous_md_text=existing)
    if errors:
        raise ValueError("Cannot record owner decision: " + "; ".join(errors))
    path.write_text(updated, encoding="utf-8")
    return path


def load_case_law(law_dir: str | Path) -> list[dict[str, Any]]:
    """Load court precedents from CASE_LAW.json."""
    path = Path(law_dir) / "CASE_LAW.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("precedents", []))
    if isinstance(data, list):
        return data
    raise ValueError(f"Invalid CASE_LAW.json structure in {path}")


def record_court_precedent(
    law_dir: str | Path,
    precedent_id: str,
    delegation_ref: str,
    holding: str,
    scope: str,
) -> Path:
    """Persist a court precedent decided under owner delegation (OD-x)."""
    path = Path(law_dir) / "CASE_LAW.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    precedents = load_case_law(law_dir)
    if any(p.get("id") == precedent_id for p in precedents):
        return path
    precedents.append(
        {
            "id": precedent_id,
            "delegation_ref": delegation_ref,
            "citation": f"decided by the court under {delegation_ref}",
            "holding": holding,
            "scope": scope,
        }
    )
    path.write_text(json.dumps({"precedents": precedents}, indent=2) + "\n", encoding="utf-8")
    return path


def load_rulebook(law_dir: str | Path) -> dict[str, Any]:
    """Load rulebook.json or return default skeleton."""
    path = Path(law_dir) / "rulebook.json"
    if not path.is_file():
        return {"version": "0.1.0", "changelog": [], "rules": []}
    return json.loads(path.read_text(encoding="utf-8"))


def bump_rulebook_version(
    law_dir: str | Path,
    new_version: str,
    changelog_entry: str,
    rule_updates: list[dict[str, Any]] | None = None,
) -> Path:
    """Bump rulebook.json version, record changelog line, and merge rule updates."""
    path = Path(law_dir) / "rulebook.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    book = load_rulebook(law_dir)
    book["version"] = new_version
    changelog = list(book.get("changelog", []))
    changelog.append(f"{new_version}: {changelog_entry}")
    book["changelog"] = changelog

    if rule_updates:
        existing_rules: list[dict[str, Any]] = list(book.get("rules", []))
        by_id = {r["id"]: idx for idx, r in enumerate(existing_rules) if "id" in r}
        for rule in rule_updates:
            rid = rule["id"]
            if rid in by_id:
                existing_rules[by_id[rid]] = rule
            else:
                existing_rules.append(rule)
        book["rules"] = existing_rules

    path.write_text(json.dumps(book, indent=2) + "\n", encoding="utf-8")
    return path


def assemble_law(law_dir: str | Path) -> str:
    """Assemble Parts 0-3 Law in strict precedence order."""
    root = Path(law_dir)
    sections: list[str] = []

    # Part 0: Owner Decisions
    od_path = root / "owner_decisions.md"
    sections.append("# PART 0: OWNER DECISIONS (HIGHEST AUTHORITY)")
    if od_path.is_file():
        od_text = od_path.read_text(encoding="utf-8")
        decisions = parse_owner_decisions(od_text)
        superseded_ids = {d.supersedes for d in decisions if d.supersedes}
        if not decisions:
            sections.append(od_text.strip() or "(None recorded)")
        else:
            for dec in decisions:
                status_tag = " [SUPERSEDED]" if dec.id in superseded_ids else " [ACTIVE]"
                sections.append(f"## {dec.date} | {dec.id}{status_tag}\n{dec.body}")
    else:
        sections.append("(No owner decisions file found)")

    # Part 1: Researcher Decisions & Court Case Law Precedents
    sections.append("\n# PART 1: DOMAIN-EXPERT DECISIONS & COURT PRECEDENTS")
    res_path = root / "researcher_decisions.md"
    if res_path.is_file() and res_path.read_text(encoding="utf-8").strip():
        sections.append("## Researcher Decisions\n" + res_path.read_text(encoding="utf-8").strip())
    precedents = load_case_law(root)
    if precedents:
        prec_lines = ["## Court Precedents (Stare Decisis)"]
        for prec in precedents:
            cit = prec.get("citation") or f"decided by the court under {prec.get('delegation_ref', 'owner delegation')}"
            prec_lines.append(
                f"- **{prec['id']}** ({cit}, scope={prec.get('scope', 'general')}): {prec['holding']}"
            )
        sections.append("\n".join(prec_lines))
    elif not res_path.is_file():
        sections.append("(No researcher decisions or court precedents recorded)")

    # Part 2: ENABLED Rulebook Rules
    sections.append("\n# PART 2: ENABLED RULEBOOK RULES (STATUTORY LAW)")
    book = load_rulebook(root)
    rules = list(book.get("rules", []))
    enabled_rules = [r for r in rules if r.get("enabled") is True]
    disabled_rules = [r for r in rules if r.get("enabled") is not True]

    sections.append(f"Rulebook Version: {book.get('version', '0.0.0')}")
    if enabled_rules:
        for rule in enabled_rules:
            params = json.dumps(rule.get("params", {}), sort_keys=True)
            sections.append(
                f"- [{rule['id']}] (owner={rule.get('owner', 'unknown')}, status={rule.get('status', 'active')}): "
                f"{rule.get('description', '')} | params={params}"
            )
    else:
        sections.append("(No ENABLED rules)")

    # Part 3: Prompt & Engineering Conventions
    sections.append("\n# PART 3: PROMPT & ENGINEERING CONVENTIONS")
    conv_path = root / "conventions.md"
    if conv_path.is_file() and conv_path.read_text(encoding="utf-8").strip():
        sections.append(conv_path.read_text(encoding="utf-8").strip())
    else:
        sections.append("(No conventions file found)")

    # Non-binding appendix for DISABLED rules
    if disabled_rules:
        sections.append("\n# NON-BINDING APPENDIX: DISABLED RULES (PROPOSAL ONLY - NOT LAW)")
        for rule in disabled_rules:
            sections.append(
                f"- [DISABLED PROPOSAL: {rule.get('id', '?')}] "
                f"(status={rule.get('status', 'proposed')}): {rule.get('description', '')}"
            )

    return "\n".join(sections).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble and inspect Courtroom Parts 0-3 Law.")
    parser.add_argument("--law-dir", required=True, help="Directory containing law files.")
    parser.add_argument("--verify-od", action="store_true", help="Validate owner_decisions.md format.")
    args = parser.parse_args(argv)

    law_dir = Path(args.law_dir)
    if args.verify_od:
        od_path = law_dir / "owner_decisions.md"
        text = od_path.read_text(encoding="utf-8") if od_path.is_file() else ""
        errors = validate_owner_decisions_append_only(text)
        if errors:
            for err in errors:
                print(f"ERROR: {err}")
            return 1
        print("OK: owner_decisions.md valid.")
        return 0

    print(assemble_law(law_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
