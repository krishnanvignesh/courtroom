"""Compile Markdown or YAML plans and rebuttals into strict Courtroom JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from courtroom.schemas import validate_schema

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_ITEM_HEADER_RE = re.compile(r"^###\s+([A-Za-z0-9_-]+)\s*:\s*(.+)$")
_REBUTTAL_HEADER_RE = re.compile(
    r"^###\s+([A-Za-z0-9_-]+)\s*(?:\(\s*item\s*:\s*([A-Za-z0-9_-]+)\s*\))?\s*$"
)


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text.lstrip("\ufeff"))
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("Markdown frontmatter must be a YAML mapping.")
    return meta, match.group(2)


def _parse_kv_bullets(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        kv_match = re.match(r"^[-*]\s+([a-zA-Z0-9_]+)\s*:\s*(.*)$", stripped)
        if kv_match:
            current_key = kv_match.group(1).strip().lower()
            fields[current_key] = kv_match.group(2).strip()
        elif current_key is not None:
            fields[current_key] = (fields[current_key] + " " + stripped).strip()
    return fields


def _split_csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def parse_markdown_plan(text: str) -> dict[str, Any]:
    """Parse a Markdown plan (frontmatter + Evidence/Items/Blast Radius sections) to a dict."""
    meta, body = _split_frontmatter(text)
    plan: dict[str, Any] = {
        "plan_id": meta.get("plan_id", ""),
        "mode": meta.get("mode", "pipeline"),
        "goal": meta.get("goal", ""),
        "items": [],
        "evidence": [],
    }
    if "blast_radius" in meta and isinstance(meta["blast_radius"], dict):
        plan["blast_radius"] = meta["blast_radius"]

    sections: dict[str, list[str]] = {}
    current_sec = "_root"
    for line in body.splitlines():
        h2 = re.match(r"^##\s+(.+)$", line.strip())
        if h2:
            current_sec = h2.group(1).strip().lower()
            sections.setdefault(current_sec, [])
        else:
            sections.setdefault(current_sec, []).append(line)

    if not plan["goal"] and "goal" in sections:
        plan["goal"] = " ".join(l.strip() for l in sections["goal"] if l.strip())

    # Parse Evidence section
    ev_lines = sections.get("evidence", [])
    ev_text = "\n".join(ev_lines).strip()
    yaml_block = re.search(r"```ya?ml\s*\n(.*?)\n```", ev_text, re.DOTALL | re.IGNORECASE)
    if yaml_block:
        loaded = yaml.safe_load(yaml_block.group(1))
        if isinstance(loaded, list):
            plan["evidence"] = loaded
    else:
        current_ev: dict[str, Any] | None = None
        for raw in ev_lines:
            stripped = raw.strip()
            if not stripped:
                continue
            pipe_match = re.match(r"^[-*]\s+(E\d+)\s*\|\s*(.+)$", stripped)
            if pipe_match:
                if current_ev:
                    plan["evidence"].append(current_ev)
                current_ev = {"id": pipe_match.group(1)}
                for seg in pipe_match.group(2).split("|"):
                    if ":" in seg:
                        k, v = seg.split(":", 1)
                        key = k.strip().lower()
                        val: Any = v.strip().strip('"')
                        if key == "exit_code":
                            val = int(val)
                        current_ev[key] = val
                continue
            header_match = re.match(r"^###\s+(E\d+)\b", stripped)
            if header_match:
                if current_ev:
                    plan["evidence"].append(current_ev)
                current_ev = {"id": header_match.group(1)}
                continue
            kv_match = re.match(r"^[-*]\s+([a-zA-Z0-9_]+)\s*:\s*(.*)$", stripped)
            if kv_match and current_ev is not None:
                key = kv_match.group(1).strip().lower()
                val = kv_match.group(2).strip().strip('"')
                if key == "exit_code":
                    val = int(val)
                current_ev[key] = val
        if current_ev:
            plan["evidence"].append(current_ev)

    # Parse Items section
    item_lines = sections.get("items", [])
    current_id: str | None = None
    current_title: str = ""
    buf: list[str] = []

    def _flush_item() -> None:
        if current_id is None:
            return
        kv = _parse_kv_bullets(buf)
        plan["items"].append(
            {
                "id": current_id,
                "title": current_title,
                "change": kv.get("change", ""),
                "rationale": kv.get("rationale", ""),
                "evidence_ids": _split_csv(kv.get("evidence_ids", "")),
                "risks": _split_csv(kv.get("risks", "")),
                "verification": kv.get("verification", ""),
            }
        )

    for raw in item_lines:
        m = _ITEM_HEADER_RE.match(raw.strip())
        if m:
            _flush_item()
            current_id = m.group(1).strip()
            current_title = m.group(2).strip()
            buf = []
        elif current_id is not None:
            buf.append(raw)
    _flush_item()

    # Optional Blast Radius section
    if "blast radius" in sections and "blast_radius" not in plan:
        kv = _parse_kv_bullets(sections["blast radius"])
        plan["blast_radius"] = {
            "allowed_files": _split_csv(kv.get("allowed_files", "")),
            "forbidden_files": _split_csv(kv.get("forbidden_files", "")),
            "expected_deltas": {},
        }

    return plan


def parse_markdown_rebuttal(text: str) -> dict[str, Any]:
    """Parse a Markdown rebuttal into a rebuttal dict."""
    meta, body = _split_frontmatter(text)
    rebuttal: dict[str, Any] = {
        "plan_id": meta.get("plan_id", ""),
        "responses": [],
    }
    current_obj: str | None = None
    current_item: str = ""
    buf: list[str] = []

    def _flush() -> None:
        if current_obj is None:
            return
        kv = _parse_kv_bullets(buf)
        entry: dict[str, Any] = {
            "objection_id": current_obj,
            "item_id": kv.get("item_id", current_item),
            "stance": kv.get("stance", "defend").lower(),
            "argument": kv.get("argument", ""),
            "evidence_ids": _split_csv(kv.get("evidence_ids", "")),
        }
        if kv.get("amendment"):
            entry["amendment"] = kv["amendment"]
        rebuttal["responses"].append(entry)

    for raw in body.splitlines():
        m = _REBUTTAL_HEADER_RE.match(raw.strip())
        if m:
            _flush()
            current_obj = m.group(1).strip()
            current_item = (m.group(2) or "").strip()
            buf = []
        elif current_obj is not None:
            buf.append(raw)
    _flush()
    return rebuttal


def compile_plan_file(path: str | Path) -> dict[str, Any]:
    """Load and schema-validate a plan from .json, .yaml/.yml, or .md."""
    p = Path(path)
    raw_text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw_text)
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(raw_text)
    elif suffix == ".md":
        data = parse_markdown_plan(raw_text)
    else:
        raise ValueError(f"Unsupported plan file format '{suffix}': {p}")
    return validate_schema(data, "plan")


def compile_rebuttal_file(path: str | Path) -> dict[str, Any]:
    """Load and schema-validate a rebuttal from .json, .yaml/.yml, or .md."""
    p = Path(path)
    raw_text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw_text)
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(raw_text)
    elif suffix == ".md":
        data = parse_markdown_rebuttal(raw_text)
    else:
        raise ValueError(f"Unsupported rebuttal file format '{suffix}': {p}")
    return validate_schema(data, "rebuttal")
