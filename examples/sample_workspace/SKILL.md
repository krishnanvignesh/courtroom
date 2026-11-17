---
name: courtroom
description: >
  Adversarial multi-agent judicial governance process for BOE.
  Enforces plan hearings (Prosecutor vs. Public Defender), deterministic Bailiff
  evidence verification, living case law, blast-radius replay gates, blind evaluation
  trials, and closing hearings across pipeline, software, and architecture modes.
---

# BOE AI Courtroom Process (`.ai-instructions/skills/boe-courtroom/SKILL.md`)

## Purpose
This skill governs every change to **BOE regulatory extraction rules, prompts, pipeline code, and tests** (rules, architecture RFCs, prompts, code, tests, and tooling) through adversarial LLM review and deterministic code verification ("The Bailiff") before and after implementation.

## Audience
AI coding agents, architecture reviewers, and human product owners working on **BOE**.

## Authority
- **Owner (Product Owner)** is the supreme authority. Owner decisions (`owner_decisions.md`) override all other rules.
- **Court Precedents (`CASE_LAW.json`)** decided under owner delegation (`OD-x`) are binding across future plans unless overturned by the Owner.
- **Court Tooling (`scrapers/boe/tools/v2/courtroom`)** enforces evidence verification, schema validation, and budget caps deterministically in code—never by LLM trust alone.

## Non-negotiables
1. **No implementation without an approved plan.** Every plan—including refactors, tests, and tooling—goes to a Plan Hearing first. Code is built only if the verdict is `overall: approved` (or `approved_with_conditions` with all binding conditions satisfied).
2. **Proof, not opinion.** Every claim cites a verbatim quote from the source document, a verified AST/line symbol, or a recorded command/evidence item `E#` verified by code (`evidence.py`). Unverified claims count for nothing.
3. **Model separation.** Production model stays **Haiku 4.5**. The court uses **Opus 5.5 (us.anthropic.claude-opus-5-5) on Bedrock woodmac-ai**, approved for court evaluation only.
4. **Hard budget cap.** Every court model call is cached on disk and recorded in `ledger.json`. Every paid command takes `--budget-usd` as a hard cap. Estimate cost before paid runs; ask the owner before raising the cap.
5. **Law precedence order:**
   - **Part 0:** Owner decisions (`owner_decisions.md`) — append-only, dated, owner's words verbatim. A new decision supersedes an old one without ever editing the old entry.
   - **Part 1:** Domain-expert / researcher decisions & Court Case Law (`CASE_LAW.json`).
   - **Part 2:** `ENABLED` rulebook rules (`rulebook.json`). `DISABLED` rules are proposals only—never law.
   - **Part 3:** Prompt and engineering conventions (`conventions.md`).
6. **Format only the files you change.**

## Jurisdiction Modes
Select the courtroom mode matching the task:
- **`pipeline` mode**: Production extraction/classification rules over a fixed ~200-doc corpus sample, evaluated against an independent Party B oracle.
- **`software` mode**: Blast-Radius file contract (`allowed_files` / `forbidden_files`) + Blind Spec-to-Test Trial where Party B writes tests solely from `PLAN-NNN` and the Law without seeing Party A's implementation.
- **`architecture` mode**: RFC & design review pitting **The Prosecutor** (risk, concurrency, security, migration hazards) against **The Public Defender** (simplicity, YAGNI, dependency minimalism) with `CASE_LAW.json` precedent checks.

## Locations

| Artifact | Location |
|---|---|
| Skill document | `.ai-instructions/skills/boe-courtroom/SKILL.md` |
| Court code & CLI | `scrapers/boe/tools/v2/courtroom/` (`plan_court.py`, `court.py`, `closing.py`, `replay_gate.py`, `run_pipeline.py`, `report.py`, `list_losses.py`, `show_title.py`, `show_trial.py`, `law.py`, `agents.py`, `evidence.py`, `opus_client.py`, `build_sample.py`, `doc_check.py`) |
| Law & Rulebook | `law/owner_decisions.md`, `law/CASE_LAW.json`, `law/rulebook.json`, `law/conventions.md` |
| Plans & Hearings | `plans/PLAN-NNN.json` (or `.md`/`.yaml`), `PLAN-NNN.challenge.json`, `PLAN-NNN.rebuttal.json`, `PLAN-NNN.verdict.json` |
| Progress tracker | `tracker.md` (read first, update after each step) |
| External data (uncommitted) | `.courtroom_data/` — sample `manifest.json`, model caches, `ledger.json`, `ours-rN.json`, `round-N/` |

## Step 1: Plan hearing (before any code)
1. Gather zero/low-cost evidence first (replays, dry runs, AST inspections, benchmarks). Record each finding as `E#` with its source/quote/AST ref/command output.
2. Author `PLAN-NNN.json` (or `PLAN-NNN.md`, compiled automatically) with: `plan_id`, `mode`, `goal`, optional `blast_radius`, `items[]` (`id`, `title`, `change`, `rationale`, `evidence_ids`, `risks`, `verification`), and `evidence[]` (`id`, `source`, `finding`, plus verifiable `quote`/`ast_ref`/`command`).
3. Run the Dual-Advocate Challenge (Prosecutor + Public Defender):
   ```bash
   python scrapers/boe/tools/v2/courtroom/plan_court.py challenge --plan plans/PLAN-NNN.json --law-dir law --budget-usd 2.0
   ```
4. Author `PLAN-NNN.rebuttal.json` answering every `OBJ-#`: either `concede` (with concrete `amendment`) or `defend` (with existing `evidence_ids`). Add new evidence to the plan first if requested.
5. Run the Plan Judge:
   ```bash
   python scrapers/boe/tools/v2/courtroom/plan_court.py judge --plan plans/PLAN-NNN.json --rebuttal plans/PLAN-NNN.rebuttal.json --law-dir law --budget-usd 2.0
   ```
6. Verdict conditions are binding. If any item is `reject` (`overall: rejected`), amend the plan and re-hear it.

## Step 2: Implement exactly the approved plan
- Add/update each rulebook entry (`id`, `owner`, `status`, `enabled`, `stage`, `description` citing ruling/plan, `params`), bump `rulebook.json` version, and append a changelog line.
- Pipeline stages follow strict order: `scope -> fill -> validation -> derive -> route`.
- Every test cites its governing rule ID and source document or court ruling; never pin behavior that the Law does not state.
- Run tests, linter, and formatter on changed files only.

## Step 3: Evaluation court round
1. **Zero-cost Replay Gate & Blast-Radius Check**:
   ```bash
   python scrapers/boe/tools/v2/courtroom/replay_gate.py --baseline ours-r0.json --candidate ours-rN.json --expect ID.field=value --plan plans/PLAN-NNN.json
   ```
   Unpredicted diffs fail the gate immediately; never accept unexpected diffs silently.
2. **Pipeline Run** (using cached production prompts):
   ```bash
   python scrapers/boe/tools/v2/courtroom/run_pipeline.py --manifest .courtroom_data/manifest.json --law-dir law --out .courtroom_data/ours-rN.json
   ```
3. **Adversarial Trial Round** (reusing unchanged trials and Party B from round 1):
   ```bash
   python scrapers/boe/tools/v2/courtroom/court.py --ours .courtroom_data/ours-rN.json --manifest .courtroom_data/manifest.json --law-dir law --out .courtroom_data/round-N --reuse-b .courtroom_data/round-1 --budget-usd 5.0
   ```
   Each contested trial runs strictly in order:
   1. Generator (Party B): independent output / blind assertions.
   2. Code comparison of Party A (`ours`) vs Party B.
   3. Two Advocates (`advocate_a`, `advocate_b`) with openings, rebuttals, and optional concessions.
   4. Code Fact-Checker (`evidence.py`): marks every quote/AST ref `VERIFIED` or `UNVERIFIED`.
   5. Judge (blinded): requires a verified `decisive_quote`. Void rulings are retried once.
4. Inspect losses (`report.py`, `list_losses.py`, `show_title.py`, `show_trial.py`). Appeal wrong rulings with verbatim quotes (`--appeals FILE`); concede when the source disproves Party A.
5. **Standing Success Baseline:** `party_a_fully_correct >= previous_round`, `accepted_but_wrong == 0`, and `rule_tuning_score >= previous_round`.

## Step 4: Closing hearing
Group every remaining loss with your position (`fix_rule`, `fix_code`, `accept_limit`, `escalate_owner`) and facts. Each loss must appear in **exactly one** group.
```bash
python scrapers/boe/tools/v2/courtroom/closing.py --round .courtroom_data/round-N --brief BRIEF.json --law-dir law --tracker tracker.md --budget-usd 2.0
```
- **`continue`**: implement `require_fix` decisions, record in `tracker.md`, and repeat Step 3.
- **`consensus`**: report results to the Owner. Commit only when the Owner asks.
- If a closing brief contained an inaccurate statement, submit a corrected brief (`amends_brief_id` + explicit `correction_statement`) and re-run the closing hearing.

## Standing owner rules
- Record every owner decision verbatim and dated in `owner_decisions.md`. When the owner delegates ("choose the best option"), submit options and proposed choice to the Plan Judge, record numbered precedents `"decided by the court under OD-x"`, and keep holdings narrow.
- Researcher questions: send each question once, completely, with boundary cases and verbatim quoted examples—never follow-up questions. Questions also pass through a Plan Hearing first.
- Never degrade published quality or publish a value the Law calls wrong. Route ambiguous records to `review`; never hold records the source text decides.
- Move replaced code to an `archive/` folder only after testing and a judge ruling; do not delete it directly.
- Update docs whenever behavior or results change and run `doc_check.py`.
- Keep local courtroom state and `.courtroom_data/` uncommitted; never describe the local courtroom harness in repo docs as a required production dependency.

## Related
- Unified CLI: `courtroom --help`
- MCP Server: `courtroom mcp`
- Doc integrity check: `python scrapers/boe/tools/v2/courtroom/doc_check.py --skill .ai-instructions/skills/boe-courtroom/SKILL.md --law-dir law`
