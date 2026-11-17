# Contributing to Agent Courtroom

Thank you for contributing to `agent-courtroom`! We welcome bug reports, documentation improvements, new jurisdiction presets, and pull requests.

## Prerequisites

- Python `3.11+`
- [`uv`](https://docs.astral.sh/uv/) for environment and dependency management

## Development Setup

```bash
git clone https://github.com/krishnanvignesh/agent-courtroom.git
cd agent-courtroom
uv sync --dev
```

## Running Tests & Integrity Checks

Run the full offline pytest suite and documentation integrity checks before opening a pull request:

```bash
uv run pytest -v
uv run courtroom doc-check --skill skills/courtroom/SKILL.md
uv run python tools/courtroom/doc_check.py --skill examples/sample_workspace/SKILL.md --law-dir examples/sample_workspace/law --require-rendered
```

All tests in `tests/` run offline using the `mock` provider by default so CI and local checks never incur model API costs.

## Courtroom Governance Conventions

When developing changes in a Courtroom-governed workspace (including dogfooding `agent-courtroom` itself):

1. **Plan Hearing First**: Author a plan (`.json`, `.md`, or `.yaml`) with verifiable evidence items (`E#`) and run `plan_court.py challenge` and `plan_court.py judge` before implementing changes.
2. **Respect Law Precedence (Parts 0–3)**:
   - `owner_decisions.md` is strictly **append-only** (`## YYYY-MM-DD | OD-N`). Never edit or delete prior decisions; supersede them with a new dated entry.
   - Only `ENABLED` rules in `rulebook.json` are binding law (`DISABLED` rules are proposals only). Whenever adding or modifying enabled rules, bump `rulebook.json`'s `version` and add a matching `changelog` entry.
3. **Cite Rules in Tests**: Every test covering governed behavior should cite its governing rule ID, owner decision (`OD-N`), or court precedent.
4. **Scoped Changes**: Format only the files you change, keep local `.courtroom_data/` caches and `ledger.json` uncommitted, and honor any `blast_radius` (`allowed_files` / `forbidden_files`) declared in the approved plan.
