"""Step 3a: Zero-cost Replay Gate & Software Blast-Radius Contract checker."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any

from courtroom.markdown_compiler import compile_plan_file


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_expectation(spec: str) -> tuple[str, str | None, Any]:
    """Parse 'DOC1.field=val' or 'DOC1=val' into (doc_id, field_or_none, parsed_value)."""
    if "=" not in spec:
        raise ValueError(f"Invalid --expect format '{spec}'. Expected 'ID=value' or 'ID.field=value'.")
    lhs, rhs = spec.split("=", 1)
    value = _parse_value(rhs)
    if "." in lhs:
        doc_id, field = lhs.split(".", 1)
        return doc_id.strip(), field.strip(), value
    return lhs.strip(), None, value


def load_outputs_map(path: str | Path) -> dict[str, Any]:
    """Normalize an outputs JSON file into a {doc_id: record} mapping."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "documents" in data and isinstance(data["documents"], dict):
            return dict(data["documents"])
        return dict(data)
    if isinstance(data, list):
        out: dict[str, Any] = {}
        for entry in data:
            if isinstance(entry, dict) and "doc_id" in entry:
                out[str(entry["doc_id"])] = entry
        return out
    raise ValueError(f"Unsupported outputs format in {path}")


def compute_diffs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    include_meta: bool = False,
) -> list[dict[str, Any]]:
    """Compute sorted document/field-level differences between baseline and candidate."""
    diffs: list[dict[str, Any]] = []
    all_docs = sorted(set(baseline.keys()) | set(candidate.keys()))
    for doc_id in all_docs:
        b_val = baseline.get(doc_id)
        c_val = candidate.get(doc_id)
        if b_val == c_val:
            continue
        if isinstance(b_val, dict) and isinstance(c_val, dict):
            all_fields = sorted(set(b_val.keys()) | set(c_val.keys()))
            for field in all_fields:
                if not include_meta and str(field).startswith("_"):
                    continue
                bf = b_val.get(field)
                cf = c_val.get(field)
                if bf != cf:
                    diffs.append(
                        {
                            "doc_id": doc_id,
                            "field": field,
                            "before": bf,
                            "after": cf,
                        }
                    )
        else:
            diffs.append(
                {
                    "doc_id": doc_id,
                    "field": None,
                    "before": b_val,
                    "after": c_val,
                }
            )
    return diffs


def check_blast_radius(
    plan: dict[str, Any],
    changed_files: list[str],
) -> list[str]:
    """Verify changed files conform to the plan's allowed_files and forbidden_files."""
    br = plan.get("blast_radius")
    if not br:
        return []
    allowed = [str(p).replace("\\", "/") for p in br.get("allowed_files", [])]
    forbidden = [str(p).replace("\\", "/") for p in br.get("forbidden_files", [])]

    violations: list[str] = []
    for raw_file in changed_files:
        norm = raw_file.replace("\\", "/").lstrip("./")
        for fpat in forbidden:
            if fnmatch.fnmatch(norm, fpat):
                violations.append(f"Forbidden file touched: '{norm}' matches '{fpat}'")
        if allowed and not any(fnmatch.fnmatch(norm, apat) for apat in allowed):
            violations.append(
                f"Unapproved file touched: '{norm}' outside allowed_files {allowed}"
            )
    return violations


def run_replay_gate(
    baseline_path: str | Path,
    candidate_path: str | Path,
    expectations: list[str] | None = None,
    plan_path: str | Path | None = None,
    changed_files: list[str] | None = None,
    include_meta: bool = False,
) -> dict[str, Any]:
    """Run zero-cost replay gate and blast-radius contract checks."""
    baseline = load_outputs_map(baseline_path)
    candidate = load_outputs_map(candidate_path)
    diffs = compute_diffs(baseline, candidate, include_meta=include_meta)

    parsed_exps = [parse_expectation(e) for e in (expectations or [])]
    expected_keys: set[tuple[str, str | None]] = {(d, f) for d, f, _ in parsed_exps}

    missing_expectations: list[str] = []
    expected_matched: list[dict[str, Any]] = []

    diff_lookup: dict[tuple[str, str | None], dict[str, Any]] = {
        (d["doc_id"], d["field"]): d for d in diffs
    }
    changed_docs = {d["doc_id"] for d in diffs}

    for doc_id, field, exp_val in parsed_exps:
        if field is not None:
            cand_rec = candidate.get(doc_id)
            actual = cand_rec.get(field) if isinstance(cand_rec, dict) else None
            diff_entry = diff_lookup.get((doc_id, field))
            if diff_entry is None or actual != exp_val:
                missing_expectations.append(
                    f"Expected {doc_id}.{field}={exp_val!r}, observed diff={diff_entry}, actual={actual!r}"
                )
            else:
                expected_matched.append(diff_entry)
        else:
            actual = candidate.get(doc_id)
            if doc_id not in changed_docs:
                missing_expectations.append(
                    f"Expected {doc_id} to change to {exp_val!r}, but it did not change."
                )
            elif actual != exp_val and not (
                isinstance(actual, dict) and actual.get("value") == exp_val
            ):
                missing_expectations.append(
                    f"Expected {doc_id}={exp_val!r}, observed {actual!r}."
                )
            else:
                expected_matched.append(
                    {"doc_id": doc_id, "field": None, "after": actual}
                )

    unpredicted_diffs: list[dict[str, Any]] = []
    for d in diffs:
        key_exact = (d["doc_id"], d["field"])
        key_doc = (d["doc_id"], None)
        if key_exact not in expected_keys and key_doc not in expected_keys:
            unpredicted_diffs.append(d)

    blast_violations: list[str] = []
    if plan_path and changed_files is not None:
        plan = compile_plan_file(plan_path)
        blast_violations = check_blast_radius(plan, changed_files)

    passed = (
        not missing_expectations
        and not unpredicted_diffs
        and not blast_violations
    )
    return {
        "passed": passed,
        "total_diffs": len(diffs),
        "expected_matched": expected_matched,
        "missing_expectations": missing_expectations,
        "unpredicted_diffs": unpredicted_diffs,
        "blast_radius_violations": blast_violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Step 3a: Zero-cost replay gate & blast-radius checker."
    )
    parser.add_argument("--baseline", required=True, help="Baseline outputs JSON.")
    parser.add_argument("--candidate", required=True, help="Candidate outputs JSON (ours-rN.json).")
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        help="Expected change in format ID=value or ID.field=value (repeatable).",
    )
    parser.add_argument("--plan", help="Optional PLAN-NNN file for blast_radius verification.")
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="List of files changed in this implementation.",
    )
    parser.add_argument(
        "--include-meta",
        action="store_true",
        help="Include internal '_'-prefixed metadata keys in diff checking.",
    )
    args = parser.parse_args(argv)

    result = run_replay_gate(
        baseline_path=args.baseline,
        candidate_path=args.candidate,
        expectations=args.expect,
        plan_path=args.plan,
        changed_files=args.changed_files,
        include_meta=args.include_meta,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
