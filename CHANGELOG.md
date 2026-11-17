# Changelog

All notable changes to `agent-courtroom` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Docs**: Rewrote `README.md` as a short, setup-first overview. Moved the in-depth material (architecture, roles, law, Bailiff, blinding, cost controls, CLI/MCP reference, walkthrough) to `docs/HOW_IT_WORKS.md`.

### Added

- **Website (`site/`)**: GitHub Pages site with an overview, the 4-step lifecycle, an architecture diagram, and software / web / architecture / pipeline examples. Deployed by `.github/workflows/pages.yml`.

## [0.1.0] - 2026-11-17

### Added

- **Core Package (`src/courtroom/`)**:
  - `schemas.py`: Structured Pydantic schemas and validation helpers for plans, challenges, rebuttals, verdicts, trials, closing briefs, and rulebooks.
  - `evidence.py` (**The Bailiff**): Deterministic verification for verbatim text/HTML quotes (`verify_quote`), Python AST symbols and line ranges (`verify_ast_citation`), and recorded command exhibits (`run_command_exhibit`, `verify_exhibit`).
  - `opus_client.py`: Provider-agnostic `CourtClient` with SHA-256 disk caching, `ledger.json` spend tracking, hard USD budget enforcement (`BudgetExceededError`), JSON retry-on-parse-failure, and provenance blinding (`blind_payload`).
  - `law.py`: Hierarchical Parts 0–3 Law assembler (`assemble_law`), append-only `owner_decisions.md` validator and recorder, `CASE_LAW.json` precedent management, and `rulebook.json` version bumping.
  - `markdown_compiler.py`: Compiles Markdown/YAML plans and rebuttals into structured JSON artifacts.
  - `agents.py`: Role prompts and schemas for Prosecutor, Public Defender, Plan Judge, Trial Advocates, Trial Judge, and Closing Judge across `architecture`, `software`, and `pipeline` jurisdictions.
  - `plan_court.py`: Step 1 Dual-Advocate Plan Hearing (`challenge` and `judge` commands).
  - `replay_gate.py`: Step 3a zero-cost deterministic replay diff gate and `blast_radius` file contract verifier (`allowed_files` / `forbidden_files`).
  - `run_pipeline.py`: Step 3b rule-driven sample pipeline runner.
  - `court.py`: Step 3c adversarial trial round runner with Bailiff fact-checking, void-ruling retry, appeals, and Party B reuse (`--reuse-b`).
  - `closing.py`: Step 4 closing hearing over grouped round losses with amendment/correction brief support.
  - `report.py`, `list_losses.py`, `show_title.py`, `show_trial.py`: Round inspection and loss-reporting utilities.
  - `build_sample.py`: Sample corpus manifest and workspace generator.
  - `doc_check.py`: Validates `SKILL.md` required sections, unresolved placeholder detection (`--require-rendered`), `owner_decisions.md` append-only format, and `rulebook.json` version/changelog sync.
  - `mcp_server.py`: Zero-dependency stdio JSON-RPC 2.0 MCP server exposing `court_verify_evidence`, `court_assemble_law`, `court_challenge`, `court_judge`, `court_replay_gate`, `court_trial_round`, and `court_closing`.
  - `cli.py`: Unified `courtroom` CLI with `init`, `render-skill`, and subcommand dispatch.
- **Standalone Tool Wrappers (`tools/courtroom/`)**: Direct script entrypoints matching the `SKILL.md` specification.
- **Skill Template & Presets (`skills/courtroom/`)**: Parameterized `SKILL.md` and presets (`software-default.json`, `arch-default.json`, `boe-pipeline.json`).
- **Sample Workspace & Offline Tests**: End-to-end sample workspace (`examples/sample_workspace/`) and offline pytest test suite (`tests/`).
- **Release & CI Infrastructure**: GitHub Actions CI matrix across Linux/Windows and Python 3.11–3.13, `CONTRIBUTING.md`, `CHANGELOG.md`, and `SECURITY.md`.
