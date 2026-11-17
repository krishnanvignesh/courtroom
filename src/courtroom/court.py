"""Step 3c: Evaluation Trial Court (pipeline, software, and architecture modes)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from courtroom.agents import build_prompt, default_mock_factory
from courtroom.evidence import verify_ast_citation, verify_quote
from courtroom.law import assemble_law
from courtroom.opus_client import DEFAULT_COURT_MODEL, CourtClient
from courtroom.replay_gate import load_outputs_map
from courtroom.schemas import validate_schema


def _strip_internal_meta(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"value": record}
    return {k: v for k, v in record.items() if not str(k).startswith("_")}


def _load_manifest_by_id(manifest_path: str | Path) -> dict[str, dict[str, Any]]:
    m_path = Path(manifest_path)
    data = json.loads(m_path.read_text(encoding="utf-8"))
    raw_docs = data.get("documents", data) if isinstance(data, dict) else data
    by_id: dict[str, dict[str, Any]] = {}
    for entry in raw_docs:
        doc = dict(entry)
        doc_id = str(doc["doc_id"])
        if "text" not in doc and "source_path" in doc:
            src = Path(doc["source_path"])
            if not src.is_absolute():
                src = (m_path.parent / src).resolve()
            if src.is_file():
                doc["text"] = src.read_text(encoding="utf-8", errors="replace")
        by_id[doc_id] = doc
    return by_id


def _load_appeals(appeals_path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not appeals_path:
        return {}
    data = json.loads(Path(appeals_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "appeals" in data and isinstance(data["appeals"], list):
            return {str(a["doc_id"]): a for a in data["appeals"]}
        return {str(k): v for k, v in data.items()}
    if isinstance(data, list):
        return {str(a["doc_id"]): a for a in data}
    raise ValueError(f"Invalid appeals format in {appeals_path}")


def _verify_citation_item(
    citation: dict[str, Any],
    source_text: str,
    repo_root: Path | None,
) -> tuple[str, str]:
    ast_ref = citation.get("ast_ref")
    quote = str(citation.get("quote", ""))
    if ast_ref and repo_root is not None and ":" in str(ast_ref):
        idx = str(ast_ref).rfind(":")
        res = verify_ast_citation(str(ast_ref)[:idx], str(ast_ref)[idx + 1 :], repo_root)
        return res["status"], res["reason"]
    res = verify_quote(quote, source_text)
    return res["status"], res["reason"]


def _verify_decisive_quote(
    decisive_quote: str,
    source_text: str,
    repo_root: Path | None,
) -> bool:
    q = decisive_quote.strip()
    if not q:
        return False
    if ":" in q and repo_root is not None and not q.startswith("http"):
        idx = q.rfind(":")
        file_part, sym_part = q[:idx], q[idx + 1 :]
        if (repo_root / file_part).is_file():
            ast_res = verify_ast_citation(file_part, sym_part, repo_root)
            if ast_res["status"] == "VERIFIED":
                return True
    return verify_quote(q, source_text)["status"] == "VERIFIED"


def _load_reused_party_b(reuse_b_dir: Path | None, doc_id: str) -> dict[str, Any] | None:
    if reuse_b_dir is None:
        return None
    party_b_file = reuse_b_dir / "party_b" / f"{doc_id}.json"
    if party_b_file.is_file():
        return json.loads(party_b_file.read_text(encoding="utf-8"))
    trial_file = reuse_b_dir / "trials" / f"{doc_id}.json"
    if trial_file.is_file():
        trial = json.loads(trial_file.read_text(encoding="utf-8"))
        return trial.get("independent_b")
    return None


def _run_judge_with_void_retry(
    client: CourtClient,
    mode: str,
    law_text: str,
    doc_id: str,
    ours_clean: dict[str, Any],
    b_clean: dict[str, Any],
    disputed_fields: list[str],
    adv_a: dict[str, Any],
    adv_b: dict[str, Any],
    fact_check: list[dict[str, Any]],
    source_text: str,
    repo_root: Path | None,
    factory: Callable[..., Any] | None,
) -> dict[str, Any]:
    verified_quotes = [fc for fc in fact_check if fc["status"] == "VERIFIED"]
    all_conceded = (
        set(disputed_fields).issubset(set(adv_a.get("conceded_fields", [])))
        or set(disputed_fields).issubset(set(adv_b.get("conceded_fields", [])))
    )

    sys_prompt, usr_prompt, schema_name = build_prompt(
        "trial_judge",
        mode=mode,
        law=law_text,
        doc_id=doc_id,
        submission_a=ours_clean,
        submission_b=b_clean,
        disputed_fields=disputed_fields,
        advocate_a=adv_a,
        advocate_b=adv_b,
        fact_check=fact_check,
        verified_quotes=verified_quotes,
        source_text=source_text,
    )
    raw_ruling = client.call(
        role="trial_judge",
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        schema_name=schema_name,
        response_factory=factory,
        should_cache=lambda r: (
            _verify_decisive_quote(str(r.get("decisive_quote", "")), source_text, repo_root)
            or all_conceded
        ),
    )
    decisive = str(raw_ruling.get("decisive_quote", ""))
    is_verified = _verify_decisive_quote(decisive, source_text, repo_root)
    retried = False

    if not is_verified and not all_conceded:
        retried = True
        retry_sys, retry_usr, _ = build_prompt(
            "trial_judge",
            mode=mode,
            law=law_text,
            doc_id=doc_id,
            void_notice=(
                "VOID RULING RETRY: Your previous decisive_quote failed deterministic Bailiff "
                f"verification ('{decisive}'). You MUST cite an exact VERIFIED quote from verified_quotes."
            ),
            submission_a=ours_clean,
            submission_b=b_clean,
            disputed_fields=disputed_fields,
            advocate_a=adv_a,
            advocate_b=adv_b,
            fact_check=fact_check,
            verified_quotes=verified_quotes,
            source_text=source_text,
        )
        raw_ruling = client.call(
            role="trial_judge",
            system_prompt=retry_sys,
            user_prompt=retry_usr,
            schema_name=schema_name,
            response_factory=factory,
            force_uncached=True,
        )
        decisive = str(raw_ruling.get("decisive_quote", ""))
        is_verified = _verify_decisive_quote(decisive, source_text, repo_root)

    return {
        "winner": raw_ruling["winner"],
        "field_rulings": raw_ruling.get("field_rulings", {}),
        "decisive_quote": decisive,
        "decisive_quote_verified": is_verified,
        "retried": retried,
        "accepted_but_wrong": bool(raw_ruling.get("accepted_but_wrong", False)),
        "rationale": raw_ruling["rationale"],
        "cited_rules": list(raw_ruling.get("cited_rules", [])),
    }


def _apply_appeal(
    client: CourtClient,
    mode: str,
    law_text: str,
    doc_id: str,
    appeal_req: dict[str, Any],
    ours_clean: dict[str, Any],
    b_clean: dict[str, Any],
    disputed_fields: list[str],
    fact_check: list[dict[str, Any]],
    ruling: dict[str, Any],
    source_text: str,
    repo_root: Path | None,
    factory: Callable[..., Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify appeal quote via Bailiff and re-run Trial Judge with the appeal brief."""
    app_quote = str(appeal_req.get("appeal_quote") or appeal_req.get("quote") or "")
    app_verified = _verify_decisive_quote(app_quote, source_text, repo_root)
    default_field = disputed_fields[0] if disputed_fields else "status"
    app_fact_check = list(fact_check) + [
        {
            "party": "A",
            "field": str(appeal_req.get("field", default_field)),
            "quote_or_ref": app_quote,
            "status": "VERIFIED" if app_verified else "UNVERIFIED",
            "details": "Appeal submission verified by Bailiff.",
        }
    ]
    app_sys, app_usr, app_schema = build_prompt(
        "trial_judge",
        mode=mode,
        law=law_text,
        doc_id=doc_id,
        appeal_brief=appeal_req,
        appeal_verified=app_verified,
        previous_ruling=ruling,
        submission_a=ours_clean,
        submission_b=b_clean,
        disputed_fields=disputed_fields,
        fact_check=app_fact_check,
        verified_quotes=[fc for fc in app_fact_check if fc["status"] == "VERIFIED"],
        source_text=source_text,
    )
    post_appeal = client.call(
        role="trial_judge",
        system_prompt=app_sys,
        user_prompt=app_usr,
        schema_name=app_schema,
        response_factory=factory,
        force_uncached=True,
    )
    post_quote = str(post_appeal.get("decisive_quote", ""))
    post_verified = _verify_decisive_quote(post_quote, source_text, repo_root)
    overturned = post_appeal["winner"] != ruling["winner"]
    after_ruling = {
        "winner": post_appeal["winner"],
        "field_rulings": post_appeal.get("field_rulings", {}),
        "decisive_quote": post_quote,
        "decisive_quote_verified": post_verified,
        "retried": False,
        "accepted_but_wrong": bool(post_appeal.get("accepted_but_wrong", False)),
        "rationale": post_appeal["rationale"],
        "cited_rules": list(post_appeal.get("cited_rules", [])),
    }
    appeal_record = {
        "appeal_quote": app_quote,
        "appeal_verified": app_verified,
        "outcome": "overturned" if overturned else "upheld",
        "ruling_after_appeal": after_ruling,
    }
    effective_ruling = after_ruling if overturned else ruling
    return effective_ruling, appeal_record


def run_court_round(
    ours_path: str | Path,
    manifest_path: str | Path,
    law_dir: str | Path,
    out_dir: str | Path,
    client: CourtClient,
    reuse_b_dir: str | Path | None = None,
    previous_round_dir: str | Path | None = None,
    appeals_path: str | Path | None = None,
    mode: str = "pipeline",
    repo_root: str | Path | None = None,
    response_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute an Evaluation Court round across all documents in ours_path."""
    ours_map = load_outputs_map(ours_path)
    manifest_map = _load_manifest_by_id(manifest_path)
    appeals_map = _load_appeals(appeals_path)
    law_text = assemble_law(law_dir)

    out_path = Path(out_dir)
    trials_dir = out_path / "trials"
    party_b_dir = out_path / "party_b"
    trials_dir.mkdir(parents=True, exist_ok=True)
    party_b_dir.mkdir(parents=True, exist_ok=True)

    reuse_b_path = Path(reuse_b_dir) if reuse_b_dir else None
    prev_path = Path(previous_round_dir) if previous_round_dir else None
    root_path = Path(repo_root) if repo_root else None
    round_id = out_path.name
    factory = response_factory or (default_mock_factory if client.provider == "mock" else None)

    spend_before = client.current_spend()
    trials: list[dict[str, Any]] = []

    for doc_id in sorted(ours_map.keys()):
        ours_clean = _strip_internal_meta(ours_map[doc_id])
        doc_meta = manifest_map.get(doc_id, {"doc_id": doc_id, "text": ""})
        source_text = str(doc_meta.get("text", ""))
        appeal_req = appeals_map.get(doc_id)

        # Reuse previous trial if Party A output is unchanged (and apply appeal if filed)
        if prev_path is not None:
            prev_trial_file = prev_path / "trials" / f"{doc_id}.json"
            if prev_trial_file.is_file():
                prev_trial = json.loads(prev_trial_file.read_text(encoding="utf-8"))
                if prev_trial.get("ours_a") == ours_clean:
                    reused = dict(prev_trial)
                    reused["round_id"] = round_id
                    reused["reused_from"] = prev_path.name
                    if appeal_req is not None:
                        eff_ruling, appeal_record = _apply_appeal(
                            client=client,
                            mode=mode,
                            law_text=law_text,
                            doc_id=doc_id,
                            appeal_req=appeal_req,
                            ours_clean=ours_clean,
                            b_clean=reused["independent_b"],
                            disputed_fields=reused["disputed_fields"],
                            fact_check=reused["fact_check"],
                            ruling=reused["ruling"],
                            source_text=source_text,
                            repo_root=root_path,
                            factory=factory,
                        )
                        reused["ruling"] = eff_ruling
                        reused["appeal"] = appeal_record
                    validated_reused = validate_schema(reused, "trial")
                    (trials_dir / f"{doc_id}.json").write_text(
                        json.dumps(validated_reused, indent=2) + "\n", encoding="utf-8"
                    )
                    (party_b_dir / f"{doc_id}.json").write_text(
                        json.dumps(validated_reused["independent_b"], indent=2) + "\n",
                        encoding="utf-8",
                    )
                    trials.append(validated_reused)
                    continue

        # Step 1: Generator (Party B)
        reused_b = _load_reused_party_b(reuse_b_path, doc_id)
        if reused_b is not None:
            b_clean = _strip_internal_meta(reused_b)
        else:
            gen_sys, gen_usr, gen_schema = build_prompt(
                "generator",
                mode=mode,
                law=law_text,
                source_doc=doc_meta,
            )
            gen_out = client.call(
                role="generator",
                system_prompt=gen_sys,
                user_prompt=gen_usr,
                schema_name=gen_schema,
                response_factory=factory,
            )
            b_clean = _strip_internal_meta(gen_out.get("extraction", {}))

        (party_b_dir / f"{doc_id}.json").write_text(
            json.dumps(b_clean, indent=2) + "\n", encoding="utf-8"
        )

        # Step 2: Code comparison of A (ours) vs B
        all_fields = sorted(set(ours_clean.keys()) | set(b_clean.keys()))
        disputed_fields = [f for f in all_fields if ours_clean.get(f) != b_clean.get(f)]

        if not disputed_fields:
            empty_adv = {
                "opening": "No dispute; submissions are identical.",
                "rebuttal": "",
                "conceded_fields": [],
                "citations": [],
            }
            trial_data = validate_schema(
                {
                    "doc_id": doc_id,
                    "round_id": round_id,
                    "mode": mode,
                    "reused_from": None,
                    "ours_a": ours_clean,
                    "independent_b": b_clean,
                    "disputed_fields": [],
                    "advocate_a": empty_adv,
                    "advocate_b": empty_adv,
                    "fact_check": [],
                    "ruling": {
                        "winner": "agreement",
                        "field_rulings": {},
                        "decisive_quote": "",
                        "decisive_quote_verified": True,
                        "retried": False,
                        "accepted_but_wrong": False,
                        "rationale": "Submission A and Submission B agree on all fields.",
                        "cited_rules": [],
                    },
                },
                "trial",
            )
            (trials_dir / f"{doc_id}.json").write_text(
                json.dumps(trial_data, indent=2) + "\n", encoding="utf-8"
            )
            trials.append(trial_data)
            continue

        # Step 3: Two Advocates (A and B)
        adv_a_sys, adv_a_usr, adv_schema = build_prompt(
            "advocate_a",
            mode=mode,
            law=law_text,
            doc_id=doc_id,
            own_submission=ours_clean,
            opponent_submission=b_clean,
            disputed_fields=disputed_fields,
            source_text=source_text,
        )
        adv_a = client.call(
            role="advocate_a",
            system_prompt=adv_a_sys,
            user_prompt=adv_a_usr,
            schema_name=adv_schema,
            response_factory=factory,
        )

        adv_b_sys, adv_b_usr, _ = build_prompt(
            "advocate_b",
            mode=mode,
            law=law_text,
            doc_id=doc_id,
            own_submission=b_clean,
            opponent_submission=ours_clean,
            disputed_fields=disputed_fields,
            source_text=source_text,
        )
        adv_b = client.call(
            role="advocate_b",
            system_prompt=adv_b_sys,
            user_prompt=adv_b_usr,
            schema_name=adv_schema,
            response_factory=factory,
        )

        # Step 4: Code Fact-Checker (The Bailiff)
        fact_check: list[dict[str, Any]] = []
        for party, adv in (("A", adv_a), ("B", adv_b)):
            for cit in adv.get("citations", []):
                status, details = _verify_citation_item(cit, source_text, root_path)
                fact_check.append(
                    {
                        "party": party,
                        "field": cit["field"],
                        "quote_or_ref": cit.get("ast_ref") or cit["quote"],
                        "status": status,
                        "details": details,
                    }
                )

        # Step 5: Trial Judge (with void retry)
        ruling = _run_judge_with_void_retry(
            client=client,
            mode=mode,
            law_text=law_text,
            doc_id=doc_id,
            ours_clean=ours_clean,
            b_clean=b_clean,
            disputed_fields=disputed_fields,
            adv_a=adv_a,
            adv_b=adv_b,
            fact_check=fact_check,
            source_text=source_text,
            repo_root=root_path,
            factory=factory,
        )

        # Step 6: Optional Appeal
        appeal_record = None
        if appeal_req is not None:
            ruling, appeal_record = _apply_appeal(
                client=client,
                mode=mode,
                law_text=law_text,
                doc_id=doc_id,
                appeal_req=appeal_req,
                ours_clean=ours_clean,
                b_clean=b_clean,
                disputed_fields=disputed_fields,
                fact_check=fact_check,
                ruling=ruling,
                source_text=source_text,
                repo_root=root_path,
                factory=factory,
            )

        trial_payload: dict[str, Any] = {
            "doc_id": doc_id,
            "round_id": round_id,
            "mode": mode,
            "reused_from": None,
            "ours_a": ours_clean,
            "independent_b": b_clean,
            "disputed_fields": disputed_fields,
            "advocate_a": adv_a,
            "advocate_b": adv_b,
            "fact_check": fact_check,
            "ruling": ruling,
        }
        if appeal_record is not None:
            trial_payload["appeal"] = appeal_record

        trial_data = validate_schema(trial_payload, "trial")
        (trials_dir / f"{doc_id}.json").write_text(
            json.dumps(trial_data, indent=2) + "\n", encoding="utf-8"
        )
        trials.append(trial_data)

    total = len(trials)
    agreements = sum(1 for t in trials if t["ruling"]["winner"] == "agreement")
    a_wins = sum(1 for t in trials if t["ruling"]["winner"] == "A")
    b_wins = sum(1 for t in trials if t["ruling"]["winner"] == "B")
    splits = sum(1 for t in trials if t["ruling"]["winner"] == "split")
    losses = [t["doc_id"] for t in trials if t["ruling"]["winner"] in ("B", "split")]
    fully_correct = agreements + a_wins
    accepted_but_wrong = sum(1 for t in trials if t["ruling"].get("accepted_but_wrong"))
    retried_count = sum(1 for t in trials if t["ruling"].get("retried"))
    score = round((fully_correct / total) * 100.0, 2) if total else 100.0
    round_cost = round(client.current_spend() - spend_before, 6)

    baseline_check: dict[str, Any] = {
        "accepted_but_wrong_zero": accepted_but_wrong == 0,
        "passed": accepted_but_wrong == 0,
    }
    if prev_path is not None and (prev_path / "summary.json").is_file():
        prev_sum = json.loads((prev_path / "summary.json").read_text(encoding="utf-8"))
        prev_correct = int(prev_sum.get("party_a_fully_correct", 0))
        prev_score = float(prev_sum.get("rule_tuning_score", 0.0))
        baseline_check.update(
            {
                "previous_round": prev_path.name,
                "fully_correct_non_regressing": fully_correct >= prev_correct,
                "score_non_regressing": score >= prev_score,
                "passed": (
                    accepted_but_wrong == 0
                    and fully_correct >= prev_correct
                    and score >= prev_score
                ),
            }
        )

    summary = {
        "round_id": round_id,
        "mode": mode,
        "total_docs": total,
        "agreements": agreements,
        "contested": total - agreements,
        "party_a_wins": a_wins,
        "party_b_wins": b_wins,
        "splits": splits,
        "party_a_losses": losses,
        "party_a_fully_correct": fully_correct,
        "accepted_but_wrong": accepted_but_wrong,
        "void_rulings_retried": retried_count,
        "rule_tuning_score": score,
        "round_cost_usd": round_cost,
        "baseline_check": baseline_check,
    }
    (out_path / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step 3c: Run Courtroom evaluation round.")
    parser.add_argument("--ours", required=True, help="Party A output JSON (ours-rN.json).")
    parser.add_argument("--out", required=True, help="Output round directory (e.g. round-1).")
    parser.add_argument("--manifest", required=True, help="Sample manifest.json with source docs.")
    parser.add_argument("--law-dir", required=True, help="Law directory with Parts 0-3 files.")
    parser.add_argument("--reuse-b", help="Previous round directory to reuse Party B from.")
    parser.add_argument("--previous-round", help="Previous round directory to reuse unchanged trials & compare baseline.")
    parser.add_argument("--appeals", help="Optional appeals JSON file.")
    parser.add_argument("--mode", default="pipeline", choices=["pipeline", "software", "architecture"])
    parser.add_argument("--repo-root", help="Repository root for AST verification.")
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
    summary = run_court_round(
        ours_path=args.ours,
        manifest_path=args.manifest,
        law_dir=args.law_dir,
        out_dir=args.out,
        client=client,
        reuse_b_dir=args.reuse_b,
        previous_round_dir=args.previous_round,
        appeals_path=args.appeals,
        mode=args.mode,
        repo_root=args.repo_root,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["baseline_check"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
