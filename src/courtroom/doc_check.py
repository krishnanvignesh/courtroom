"""Validate Courtroom documentation, SKILL.md structure, law integrity, and rulebook sync."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from courtroom.law import load_rulebook, validate_owner_decisions_append_only

REQUIRED_SKILL_SECTIONS: tuple[str, ...] = (
    "Purpose",
    "Audience",
    "Authority",
    "Non-negotiables",
    "Locations",
    "Step 1",
    "Step 2",
    "Step 3",
    "Step 4",
    "Related",
)

_UNRESOLVED_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def check_skill_doc(
    skill_path: str | Path,
    require_rendered: bool = False,
) -> tuple[list[str], list[str]]:
    """Verify SKILL.md contains required headings and optionally no unresolved placeholders."""
    errors: list[str] = []
    warnings: list[str] = []
    p = Path(skill_path)
    if not p.is_file():
        return [f"SKILL.md not found at {p}"], warnings

    text = p.read_text(encoding="utf-8")
    headings = [line.strip() for line in text.splitlines() if line.strip().startswith("#")]
    heading_blob = "\n".join(headings).lower()

    for section in REQUIRED_SKILL_SECTIONS:
        if section.lower() not in heading_blob:
            errors.append(f"SKILL.md missing required section heading containing '{section}'.")

    placeholders = sorted(set(_UNRESOLVED_PLACEHOLDER_RE.findall(text)))
    if placeholders:
        msg = f"Unresolved template placeholders in {p.name}: {placeholders}"
        if require_rendered:
            errors.append(msg)
        else:
            warnings.append(msg)

    return errors, warnings


def check_rulebook_sync(law_dir: str | Path) -> list[str]:
    """Verify rulebook.json has valid version, changelog entry for version, and rule IDs."""
    errors: list[str] = []
    rb_path = Path(law_dir) / "rulebook.json"
    if not rb_path.is_file():
        return [f"rulebook.json not found at {rb_path}"]

    book = load_rulebook(law_dir)
    version = str(book.get("version", "")).strip()
    if not version:
        errors.append("rulebook.json is missing a non-empty 'version' field.")
    changelog = book.get("changelog", [])
    if not isinstance(changelog, list):
        errors.append("rulebook.json 'changelog' must be a list.")
    elif version and not any(version in str(entry) for entry in changelog):
        errors.append(f"rulebook.json changelog does not mention current version '{version}'.")

    seen_ids: set[str] = set()
    for rule in book.get("rules", []):
        rid = rule.get("id")
        if not rid:
            errors.append("Rule entry missing 'id'.")
            continue
        if rid in seen_ids:
            errors.append(f"Duplicate rule ID in rulebook.json: '{rid}'.")
        seen_ids.add(rid)
        if "enabled" not in rule or not isinstance(rule["enabled"], bool):
            errors.append(f"Rule '{rid}' must declare boolean 'enabled'.")
    return errors


def run_doc_check(
    skill_path: str | Path,
    law_dir: str | Path | None = None,
    require_rendered: bool = False,
) -> dict[str, Any]:
    """Run all documentation, owner-decision, and rulebook integrity checks."""
    errors, warnings = check_skill_doc(skill_path, require_rendered=require_rendered)

    if law_dir is not None:
        ldir = Path(law_dir)
        od_path = ldir / "owner_decisions.md"
        if od_path.is_file():
            od_errors = validate_owner_decisions_append_only(od_path.read_text(encoding="utf-8"))
            errors.extend(od_errors)
        else:
            errors.append(f"owner_decisions.md not found at {od_path}")
        errors.extend(check_rulebook_sync(ldir))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify SKILL.md, owner_decisions.md, and rulebook sync.")
    parser.add_argument("--skill", required=True, help="Path to SKILL.md.")
    parser.add_argument("--law-dir", help="Optional Law directory (owner_decisions.md + rulebook.json).")
    parser.add_argument(
        "--require-rendered",
        action="store_true",
        help="Fail if any {{PLACEHOLDER}} tokens remain in SKILL.md.",
    )
    args = parser.parse_args(argv)

    result = run_doc_check(
        skill_path=args.skill,
        law_dir=args.law_dir,
        require_rendered=args.require_rendered,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
