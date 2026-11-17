"""Role prompts, schema bindings, and offline deterministic responders for Courtroom agents."""

from __future__ import annotations

import json
import re
from typing import Any

from courtroom.evidence import normalize_whitespace
from courtroom.schemas import SCHEMAS

ROLE_SCHEMA_MAP: dict[str, str] = {
    "prosecutor": "challenge",
    "public_defender": "challenge",
    "plan_challenger": "challenge",
    "plan_judge": "verdict",
    "generator": "generator",
    "advocate_a": "advocate",
    "advocate_b": "advocate",
    "trial_judge": "trial_judge",
    "closing_judge": "closing_verdict",
}

ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "prosecutor": (
        "You are THE PROSECUTOR in an adversarial Plan Hearing. "
        "Attack failure modes, concurrency races, security hazards, migration risks, "
        "unverified assumptions, and unpredicted blast radius under the governing Law. "
        "Return strict JSON matching the 'challenge' schema with role='prosecutor'."
    ),
    "public_defender": (
        "You are THE PUBLIC DEFENDER (YAGNI & Simplicity Counsel) in an adversarial Plan Hearing. "
        "Attack unnecessary abstractions, premature optimizations, redundant dependencies, "
        "over-engineering, and scope creep beyond the minimum needed to satisfy the Law. "
        "Return strict JSON matching the 'challenge' schema with role='public_defender'."
    ),
    "plan_challenger": (
        "You are the Adversarial Plan Challenger representing both Risk/Correctness and YAGNI. "
        "Identify blocking, major, or minor flaws and specify required evidence for every objection. "
        "Return strict JSON matching the 'challenge' schema."
    ),
    "plan_judge": (
        "You are THE PLAN JUDGE. Weigh the plan, verified evidence, Prosecutor & Public Defender "
        "objections, and the author's rebuttals strictly against the Parts 0-3 Law. "
        "Rule on each item ('approve', 'approve_with_conditions', 'reject'). "
        "If any item is 'reject', overall MUST be 'rejected'. "
        "When owner delegation (OD-x) applies, record narrow precedents in 'new_precedents'. "
        "Return strict JSON matching the 'verdict' schema."
    ),
    "generator": (
        "You are PARTY B (Independent Generator / Blind Examiner). "
        "Given ONLY the Law and input artifact (never Party A's implementation or output), "
        "produce an independent target extraction (pipeline mode), blind spec-to-test assertions "
        "(software mode), or independent architecture critique (architecture mode). "
        "Return strict JSON matching the 'generator' schema."
    ),
    "advocate_a": (
        "You are ADVOCATE A defending Submission A in an Evaluation Trial. "
        "Present an opening argument and rebuttal citing ONLY verbatim quotes from the source "
        "or verified AST/code references and active rule IDs. Concede fields where the Law and source "
        "contradict Submission A. Return strict JSON matching the 'advocate' schema."
    ),
    "advocate_b": (
        "You are ADVOCATE B defending Submission B in an Evaluation Trial. "
        "Present an opening argument and rebuttal citing ONLY verbatim quotes from the source "
        "or verified AST/code references and active rule IDs. Concede fields where evidence favors A. "
        "Return strict JSON matching the 'advocate' schema."
    ),
    "trial_judge": (
        "You are THE TRIAL JUDGE. Submission provenance is blinded. "
        "You MUST disregard every UNVERIFIED citation from the Bailiff's fact-check report. "
        "Your ruling MUST include a 'decisive_quote' that appears verbatim in the source text "
        "(verified by code), unless both advocates conceded. If a verified quote decides the case, "
        "do not rule 'accepted_but_wrong'. Return strict JSON matching the 'trial_judge' schema."
    ),
    "closing_judge": (
        "You are THE CLOSING JUDGE reviewing all remaining losses from an evaluation round. "
        "Verify whether each loss group's root cause and proposed action comply with Parts 0-3 Law. "
        "Issue 'continue' with concrete 'require_fix' directives if actionable law/code gaps remain, "
        "or 'consensus' when baseline criteria and law compliance are satisfied. "
        "Return strict JSON matching the 'closing_verdict' schema."
    ),
}


def get_role_spec(role: str) -> dict[str, Any]:
    """Return system prompt and JSON schema for a given courtroom role."""
    if role not in ROLE_SCHEMA_MAP:
        raise ValueError(f"Unknown courtroom role: '{role}'")
    schema_name = ROLE_SCHEMA_MAP[role]
    return {
        "role": role,
        "schema_name": schema_name,
        "system_prompt": ROLE_SYSTEM_PROMPTS[role],
        "schema": SCHEMAS[schema_name],
    }


def build_prompt(role: str, mode: str = "pipeline", **context: Any) -> tuple[str, str, str]:
    """Build (system_prompt, user_prompt, schema_name) for a role and jurisdiction mode."""
    spec = get_role_spec(role)
    mode_guidance = {
        "pipeline": "Jurisdiction Mode: PIPELINE (rule-based extraction & classification across corpus docs).",
        "software": "Jurisdiction Mode: SOFTWARE (blast-radius contract + blind spec-to-test verification).",
        "architecture": "Jurisdiction Mode: ARCHITECTURE (RFC trade-off evaluation & Stare Decisis compliance).",
    }.get(mode, f"Jurisdiction Mode: {mode}")

    lines = [mode_guidance, f"Expected JSON Schema: {spec['schema_name']}", ""]
    for key, val in context.items():
        if val is None:
            continue
        rendered = json.dumps(val, indent=2) if isinstance(val, (dict, list)) else str(val)
        lines.append(f"### {key}\n{rendered}\n")
    return spec["system_prompt"], "\n".join(lines), spec["schema_name"]


def _extract_json_block(user_prompt: str, header: str) -> Any:
    pattern = re.compile(rf"### {re.escape(header)}\n(.*?)(?=\n### |\Z)", re.DOTALL)
    match = pattern.search(user_prompt)
    if not match:
        return None
    raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def default_mock_factory(role: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Deterministic offline responder for mock/demo runs when no external LLM is configured."""
    if role in ("prosecutor", "public_defender", "plan_challenger"):
        plan = _extract_json_block(user_prompt, "plan") or {}
        items = plan.get("items", [])
        first_item = items[0]["id"] if items else "ITEM-1"
        plan_id = plan.get("plan_id", "PLAN-001")
        role_tag = "public_defender" if role == "public_defender" else "prosecutor"
        if role_tag == "prosecutor":
            return {
                "plan_id": plan_id,
                "objections": [
                    {
                        "id": "OBJ-1",
                        "item_id": first_item,
                        "role": "prosecutor",
                        "severity": "major",
                        "attack": f"Verify edge-case boundary and blast-radius isolation for {first_item}.",
                        "required_evidence": "Cite verified evidence ID proving exact scope and test coverage.",
                    }
                ],
            }
        return {
            "plan_id": plan_id,
            "objections": [
                {
                    "id": "OBJ-2",
                    "item_id": first_item,
                    "role": "public_defender",
                    "severity": "minor",
                    "attack": f"Confirm {first_item} introduces no speculative abstraction beyond immediate Law requirements.",
                    "required_evidence": "Show direct mapping to an active Law rule or owner requirement.",
                }
            ],
        }

    if role == "plan_judge":
        plan = _extract_json_block(user_prompt, "plan") or {}
        items = plan.get("items", [])
        plan_id = plan.get("plan_id", "PLAN-001")
        rulings = [
            {
                "item_id": it["id"],
                "verdict": "approve",
                "conditions": [],
                "rationale": f"Evidence {it.get('evidence_ids', [])} sufficiently supports {it['id']} under the Law.",
            }
            for it in items
        ]
        return {
            "plan_id": plan_id,
            "overall": "approved",
            "item_rulings": rulings,
            "binding_conditions": [],
            "new_precedents": [],
        }

    if role == "generator":
        doc = _extract_json_block(user_prompt, "source_doc") or {}
        doc_id = str(doc.get("doc_id", "DOC-1")) if isinstance(doc, dict) else "DOC-1"
        expected = doc.get("oracle_hint", {}) if isinstance(doc, dict) else {}
        return {
            "doc_id": doc_id,
            "extraction": dict(expected) if isinstance(expected, dict) else {},
            "blind_assertions": doc.get("blind_assertions", []) if isinstance(doc, dict) else [],
            "notes": "Offline deterministic Party B generation.",
        }

    if role in ("advocate_a", "advocate_b"):
        raw_text = str(_extract_json_block(user_prompt, "source_text") or "")
        doc_text = normalize_whitespace(raw_text, strip_html=True)
        disputed = _extract_json_block(user_prompt, "disputed_fields") or []
        own_sub = _extract_json_block(user_prompt, "own_submission") or {}
        field_name = str(disputed[0]) if isinstance(disputed, list) and disputed else "status"
        own_val = str(own_sub.get(field_name, "")) if isinstance(own_sub, dict) else ""
        snippet = ""
        if own_val and len(own_val) >= 4 and own_val.lower() in doc_text.lower():
            idx = doc_text.lower().find(own_val.lower())
            snippet = doc_text[idx : min(len(doc_text), idx + 32)].strip()
        if not snippet:
            words = doc_text.strip().split()
            snippet = " ".join(words[:6]) if len(words) >= 2 else "verified source quote"
        party_label = "Submission A" if role == "advocate_a" else "Submission B"
        return {
            "opening": f"{party_label} complies with active rulebook constraints based on the source.",
            "rebuttal": "Opposing submission omits a governing boundary condition.",
            "conceded_fields": [],
            "citations": [{"field": field_name, "quote": snippet}],
        }

    if role == "trial_judge":
        verified_quotes = _extract_json_block(user_prompt, "verified_quotes") or []
        sub_a = _extract_json_block(user_prompt, "submission_a") or {}
        sub_b = _extract_json_block(user_prompt, "submission_b") or {}
        source_text = str(_extract_json_block(user_prompt, "source_text") or "")
        decisive = (
            verified_quotes[0]["quote_or_ref"]
            if isinstance(verified_quotes, list) and verified_quotes
            else ""
        )
        winner = "A"
        if isinstance(sub_a, dict) and isinstance(sub_b, dict):
            for k, b_val in sub_b.items():
                a_val = sub_a.get(k)
                if b_val != a_val and isinstance(b_val, str) and len(b_val) >= 4:
                    b_in = b_val.lower() in source_text.lower()
                    a_in = isinstance(a_val, str) and a_val.lower() in source_text.lower()
                    if b_in and not a_in:
                        winner = "B"
                        b_quotes = [
                            vq["quote_or_ref"]
                            for vq in verified_quotes
                            if isinstance(vq, dict)
                            and vq.get("party") == "B"
                            and b_val.lower() in str(vq.get("quote_or_ref", "")).lower()
                        ]
                        if b_quotes:
                            decisive = b_quotes[0]
                        break
        return {
            "winner": winner,
            "field_rulings": {},
            "decisive_quote": decisive,
            "accepted_but_wrong": False,
            "rationale": "Verified citation resolves the disputed field under active Law.",
            "cited_rules": [],
        }

    if role == "closing_judge":
        brief = _extract_json_block(user_prompt, "brief") or {}
        round_id = brief.get("round_id", "round-1") if isinstance(brief, dict) else "round-1"
        groups = brief.get("groups", []) if isinstance(brief, dict) else []
        fixes = [
            {
                "group_id": g["group_id"],
                "action": g.get("proposed_change", "Implement rule update"),
                "rule_or_file": g.get("root_cause", "rulebook"),
            }
            for g in groups
            if g.get("position") in ("fix_rule", "fix_code")
        ]
        decision = "continue" if fixes else "consensus"
        return {
            "round_id": round_id,
            "decision": decision,
            "require_fix": fixes,
            "summary": f"Closing review complete: decision={decision} across {len(groups)} loss group(s).",
        }

    raise ValueError(f"No mock factory behavior defined for role '{role}'")
