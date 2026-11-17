"""Step 1: Plan Hearing (`challenge` with dual advocates and `judge` with Case Law)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from courtroom.agents import build_prompt, default_mock_factory
from courtroom.evidence import verify_exhibit
from courtroom.law import assemble_law, record_court_precedent
from courtroom.markdown_compiler import compile_plan_file, compile_rebuttal_file
from courtroom.opus_client import DEFAULT_COURT_MODEL, CourtClient
from courtroom.schemas import validate_schema


class RebuttalValidationError(ValueError):
    """Raised when a rebuttal misses objections or cites non-existent evidence."""


def _verify_plan_evidence(
    plan: dict[str, Any],
    repo_root: Path | None = None,
    source_lookup: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    results = []
    for ev in plan.get("evidence", []):
        res = verify_exhibit(ev, repo_root=repo_root, source_lookup=source_lookup)
        results.append(res)
    return results


def challenge(
    plan_path: str | Path,
    law_dir: str | Path,
    client: CourtClient,
    out_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    source_lookup: dict[str, str] | None = None,
    response_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run Prosecutor (Risk) and Public Defender (YAGNI) against a plan."""
    p_path = Path(plan_path)
    plan = compile_plan_file(p_path)
    mode = plan.get("mode", "pipeline")
    law_text = assemble_law(law_dir)
    root = Path(repo_root) if repo_root else p_path.parent
    evidence_audit = _verify_plan_evidence(plan, repo_root=root, source_lookup=source_lookup)

    factory = response_factory or (default_mock_factory if client.provider == "mock" else None)

    combined_objections: list[dict[str, Any]] = []
    counter = 1
    for role in ("prosecutor", "public_defender"):
        sys_prompt, usr_prompt, schema_name = build_prompt(
            role,
            mode=mode,
            law=law_text,
            plan=plan,
            bailiff_evidence_audit=evidence_audit,
        )
        res = client.call(
            role=role,
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
            schema_name=schema_name,
            response_factory=factory,
        )
        for obj in res.get("objections", []):
            item_obj = dict(obj)
            item_obj["role"] = role
            item_obj["id"] = f"OBJ-{counter}"
            counter += 1
            combined_objections.append(item_obj)

    merged = validate_schema(
        {"plan_id": plan["plan_id"], "objections": combined_objections},
        "challenge",
    )

    if out_path is None:
        stem = p_path.stem.split(".")[0]
        target = p_path.with_name(f"{stem}.challenge.json")
    else:
        target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


def _validate_rebuttal_against_challenge(
    plan: dict[str, Any],
    challenge_data: dict[str, Any],
    rebuttal: dict[str, Any],
) -> None:
    if rebuttal.get("plan_id") != plan.get("plan_id"):
        raise RebuttalValidationError(
            f"Rebuttal plan_id '{rebuttal.get('plan_id')}' does not match '{plan.get('plan_id')}'."
        )

    known_evidence = {ev["id"] for ev in plan.get("evidence", [])}
    responses_by_obj = {resp["objection_id"]: resp for resp in rebuttal.get("responses", [])}

    for obj in challenge_data.get("objections", []):
        oid = obj["id"]
        if oid not in responses_by_obj:
            raise RebuttalValidationError(
                f"Rebuttal is missing response for challenge objection '{oid}'."
            )
        resp = responses_by_obj[oid]
        if resp["stance"] == "defend":
            unknown = [eid for eid in resp.get("evidence_ids", []) if eid not in known_evidence]
            if unknown:
                raise RebuttalValidationError(
                    f"Rebuttal to '{oid}' cites unknown evidence_ids: {unknown}"
                )


def judge(
    plan_path: str | Path,
    rebuttal_path: str | Path,
    challenge_path: str | Path,
    law_dir: str | Path,
    client: CourtClient,
    out_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    source_lookup: dict[str, str] | None = None,
    response_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the Plan Judge over a plan, its challenges, and rebuttals."""
    p_path = Path(plan_path)
    plan = compile_plan_file(p_path)
    rebuttal = compile_rebuttal_file(rebuttal_path)
    challenge_data = validate_schema(
        json.loads(Path(challenge_path).read_text(encoding="utf-8")),
        "challenge",
    )

    _validate_rebuttal_against_challenge(plan, challenge_data, rebuttal)

    mode = plan.get("mode", "pipeline")
    law_text = assemble_law(law_dir)
    root = Path(repo_root) if repo_root else p_path.parent
    evidence_audit = _verify_plan_evidence(plan, repo_root=root, source_lookup=source_lookup)

    factory = response_factory or (default_mock_factory if client.provider == "mock" else None)
    sys_prompt, usr_prompt, schema_name = build_prompt(
        "plan_judge",
        mode=mode,
        law=law_text,
        plan=plan,
        bailiff_evidence_audit=evidence_audit,
        challenge=challenge_data,
        rebuttal=rebuttal,
    )
    verdict = client.call(
        role="plan_judge",
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        schema_name=schema_name,
        response_factory=factory,
    )

    # Persist any precedents decided under owner delegation (Stare Decisis)
    for prec in verdict.get("new_precedents", []):
        record_court_precedent(
            law_dir=law_dir,
            precedent_id=prec["id"],
            delegation_ref=prec["delegation_ref"],
            holding=prec["holding"],
            scope=prec["scope"],
        )

    if out_path is None:
        stem = p_path.stem.split(".")[0]
        target = p_path.with_name(f"{stem}.verdict.json")
    else:
        target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Courtroom Step 1: Plan Hearing CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chal = sub.add_parser("challenge", help="Challenge a plan with Prosecutor & Public Defender.")
    p_chal.add_argument("--plan", required=True, help="Path to PLAN-NNN (.json, .md, .yaml)")
    p_chal.add_argument("--law-dir", required=True, help="Directory with Parts 0-3 law files")
    p_chal.add_argument("--out", help="Output path for PLAN-NNN.challenge.json")
    p_chal.add_argument("--repo-root", help="Repository root for AST/quote verification")
    p_chal.add_argument("--ledger", default=".courtroom_data/ledger.json")
    p_chal.add_argument("--cache-dir", default=".courtroom_data/cache")
    p_chal.add_argument("--budget-usd", type=float, default=5.0)
    p_chal.add_argument("--provider", default="mock")
    p_chal.add_argument("--model", default=DEFAULT_COURT_MODEL)

    p_judge = sub.add_parser("judge", help="Judge a plan after rebuttal.")
    p_judge.add_argument("--plan", required=True)
    p_judge.add_argument("--rebuttal", required=True)
    p_judge.add_argument("--challenge", help="Path to .challenge.json (auto-inferred if omitted)")
    p_judge.add_argument("--law-dir", required=True)
    p_judge.add_argument("--out", help="Output path for PLAN-NNN.verdict.json")
    p_judge.add_argument("--repo-root", help="Repository root for AST/quote verification")
    p_judge.add_argument("--ledger", default=".courtroom_data/ledger.json")
    p_judge.add_argument("--cache-dir", default=".courtroom_data/cache")
    p_judge.add_argument("--budget-usd", type=float, default=5.0)
    p_judge.add_argument("--provider", default="mock")
    p_judge.add_argument("--model", default=DEFAULT_COURT_MODEL)

    args = parser.parse_args(argv)
    client = CourtClient(
        ledger_path=args.ledger,
        cache_dir=args.cache_dir,
        budget_usd=args.budget_usd,
        model=args.model,
        provider=args.provider,
    )

    if args.cmd == "challenge":
        res = challenge(
            plan_path=args.plan,
            law_dir=args.law_dir,
            client=client,
            out_path=args.out,
            repo_root=args.repo_root,
        )
        print(f"Challenge recorded: {len(res['objections'])} objection(s) for {res['plan_id']}.")
        return 0

    plan_p = Path(args.plan)
    chal_path = args.challenge or str(plan_p.with_name(f"{plan_p.stem.split('.')[0]}.challenge.json"))
    res = judge(
        plan_path=args.plan,
        rebuttal_path=args.rebuttal,
        challenge_path=chal_path,
        law_dir=args.law_dir,
        client=client,
        out_path=args.out,
        repo_root=args.repo_root,
    )
    print(f"Plan verdict for {res['plan_id']}: overall={res['overall']}")
    return 0 if res["overall"] != "rejected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
