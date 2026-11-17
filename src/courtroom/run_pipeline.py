"""Step 3b: Production pipeline runner (scope -> fill -> validation -> derive -> route)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from courtroom.evidence import normalize_whitespace
from courtroom.law import load_rulebook

PIPELINE_STAGES: tuple[str, ...] = ("scope", "fill", "validation", "derive", "route")


def _load_manifest_docs(manifest_path: str | Path) -> list[dict[str, Any]]:
    m_path = Path(manifest_path)
    data = json.loads(m_path.read_text(encoding="utf-8"))
    raw_docs = data.get("documents", data) if isinstance(data, dict) else data
    docs: list[dict[str, Any]] = []
    for item in raw_docs:
        doc = dict(item)
        if "text" not in doc and "source_path" in doc:
            src = Path(doc["source_path"])
            if not src.is_absolute():
                src = (m_path.parent / src).resolve()
            if src.is_file():
                doc["text"] = src.read_text(encoding="utf-8", errors="replace")
        docs.append(doc)
    return docs


def stage_scope(doc: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Stage 1: Determine document scope and normalize source text."""
    norm_text = normalize_whitespace(str(doc.get("text", "")), strip_html=True)
    in_scope = bool(norm_text)
    applied: list[str] = []
    for rule in rules:
        if rule.get("stage") != "scope":
            continue
        params = rule.get("params", {})
        excl = params.get("exclude_if_contains")
        if excl and str(excl).lower() in norm_text.lower():
            in_scope = False
            applied.append(rule["id"])
    return {
        "in_scope": in_scope,
        "normalized_text": norm_text,
        "applied_rules": applied,
    }


def stage_fill(
    doc: dict[str, Any],
    scope_ctx: dict[str, Any],
    rules: list[dict[str, Any]],
    prod_cache: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Stage 2: Populate fields from cached prod output and ENABLED fill rules."""
    doc_id = str(doc["doc_id"])
    fields: dict[str, Any] = dict(prod_cache.get(doc_id, {}))
    if "initial_fields" in doc and isinstance(doc["initial_fields"], dict):
        for k, v in doc["initial_fields"].items():
            fields.setdefault(k, v)

    applied: list[str] = []
    text = scope_ctx["normalized_text"]
    for rule in rules:
        if rule.get("stage") != "fill":
            continue
        params = rule.get("params", {})
        target_field = params.get("field")
        if not target_field:
            continue
        regex = params.get("regex")
        when_contains = params.get("when_contains")
        value = params.get("value")
        if regex:
            m = re.search(str(regex), text, re.IGNORECASE)
            if m:
                fields[target_field] = m.group(1) if m.groups() else value or m.group(0)
                applied.append(rule["id"])
        elif when_contains:
            needle = str(when_contains).lower()
            if needle in text.lower():
                fields[target_field] = value
                applied.append(rule["id"])
    return fields, applied


def stage_validation(
    fields: dict[str, Any],
    scope_ctx: dict[str, Any],
    rules: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Stage 3: Validate extracted fields against enabled validation rules."""
    validated = dict(fields)
    warnings: list[str] = []
    applied: list[str] = []
    for rule in rules:
        if rule.get("stage") != "validation":
            continue
        params = rule.get("params", {})
        required = params.get("required_fields", [])
        for req in required:
            if not validated.get(req):
                warnings.append(f"{rule['id']}: missing required field '{req}'")
                applied.append(rule["id"])
    return validated, warnings, applied


def stage_derive(
    fields: dict[str, Any],
    scope_ctx: dict[str, Any],
    rules: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Stage 4: Apply deterministic derive rules (overrides, mappings, defaults)."""
    derived = dict(fields)
    applied: list[str] = []
    text_lower = scope_ctx["normalized_text"].lower()
    for rule in rules:
        if rule.get("stage") != "derive":
            continue
        params = rule.get("params", {})
        target_field = params.get("field")
        if not target_field:
            continue
        when_contains = params.get("when_contains")
        when_field = params.get("when_field")
        when_equals = params.get("when_equals")
        value = params.get("value")

        matched = True
        if when_contains is not None:
            matched = matched and (str(when_contains).lower() in text_lower)
        if when_field is not None:
            matched = matched and (derived.get(when_field) == when_equals)

        if matched:
            derived[target_field] = value
            applied.append(rule["id"])
    return derived, applied


def stage_route(
    fields: dict[str, Any],
    scope_ctx: dict[str, Any],
    warnings: list[str],
    rules: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Stage 5: Route document to 'publish', 'review', or 'out_of_scope'."""
    if not scope_ctx["in_scope"]:
        return "out_of_scope", []
    if warnings:
        return "review", []
    for rule in rules:
        if rule.get("stage") == "route":
            params = rule.get("params", {})
            if params.get("review_if_field_missing") and not fields.get(params["review_if_field_missing"]):
                return "review", [rule["id"]]
    return "publish", []


def run_pipeline(
    manifest_path: str | Path,
    law_dir: str | Path,
    out_path: str | Path,
    prod_cache_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the 5-stage pipeline across sample documents using ENABLED rules and cached prompts."""
    docs = _load_manifest_docs(manifest_path)
    book = load_rulebook(law_dir)
    enabled_rules = [r for r in book.get("rules", []) if r.get("enabled") is True]

    prod_cache: dict[str, dict[str, Any]] = {}
    if prod_cache_path and Path(prod_cache_path).is_file():
        prod_cache = json.loads(Path(prod_cache_path).read_text(encoding="utf-8"))

    outputs: dict[str, Any] = {}
    for doc in docs:
        doc_id = str(doc["doc_id"])
        scope_ctx = stage_scope(doc, enabled_rules)
        filled, fill_rules = stage_fill(doc, scope_ctx, enabled_rules, prod_cache)
        validated, warnings, val_rules = stage_validation(filled, scope_ctx, enabled_rules)
        derived, drv_rules = stage_derive(validated, scope_ctx, enabled_rules)
        route, route_rules = stage_route(derived, scope_ctx, warnings, enabled_rules)

        record = dict(derived)
        record["_meta"] = {
            "route": route,
            "stages": list(PIPELINE_STAGES),
            "applied_rules": fill_rules + val_rules + drv_rules + route_rules,
            "warnings": warnings,
        }
        outputs[doc_id] = record

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(outputs, indent=2) + "\n", encoding="utf-8")
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Step 3b: Run 5-stage pipeline using ENABLED rulebook rules and cached prompts."
    )
    parser.add_argument("--manifest", required=True, help="Path to sample manifest.json.")
    parser.add_argument("--law-dir", required=True, help="Directory with rulebook.json & law files.")
    parser.add_argument("--out", required=True, help="Output JSON path (ours-rN.json).")
    parser.add_argument("--prod-cache", help="Optional cached production extractions JSON.")
    args = parser.parse_args(argv)

    outputs = run_pipeline(
        manifest_path=args.manifest,
        law_dir=args.law_dir,
        out_path=args.out,
        prod_cache_path=args.prod_cache,
    )
    print(f"Pipeline completed for {len(outputs)} document(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
