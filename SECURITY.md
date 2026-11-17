# Security Policy

## Built-in Governance & Security Controls

`agent-courtroom` includes deterministic code-level guardrails designed to constrain AI agent actions and verification steps:

- **Repository Root Confinement (`evidence.verify_ast_citation`, `evidence.verify_exhibit`)**: All file paths cited for AST symbol lookup, line ranges, or verbatim source quote verification are resolved and checked via `candidate.relative_to(root)` so citations cannot traverse outside the repository root.
- **Bounded Command Exhibit Execution (`evidence.run_command_exhibit`)**: Command exhibits enforce a subprocess timeout (default `30` seconds) and record a SHA-256 digest (`output_sha256`) of combined stdout/stderr. Note: `run_command_exhibit` executes commands via `subprocess.run(..., shell=True)` and should only be invoked with trusted local commands in controlled environments.
- **Judge Provenance Blinding (`opus_client.blind_payload`)**: Judge calls (`plan_judge`, `trial_judge`, `closing_judge`) neutralize provenance strings such as `"Party A (production)"`, `"ours"`, and `"production output"` into neutral submission identifiers before model invocation.
- **Append-Only Owner Decision Integrity (`law.validate_owner_decisions_append_only`)**: Enforces monotonic ISO dates, unique `OD-N` IDs, and strict prefix preservation when comparing against prior `owner_decisions.md` snapshots so historical Part 0 rulings cannot be silently altered.
- **Hard USD Budget Enforcement (`opus_client.CourtClient`)**: Tracks cumulative spend in `ledger.json` and raises `BudgetExceededError` before issuing any uncached model call that would exceed `--budget-usd`.

## Supported Versions

| Version | Supported |
|---|---|
| `0.1.x` | Yes |

## Reporting a Vulnerability

If you discover a security vulnerability in `agent-courtroom`:

1. **Do not** open a public GitHub issue with exploit details before triage.
2. Report the issue privately via [GitHub Security Advisories](https://github.com/krishnanvignesh/agent-courtroom/security/advisories/new) (or contact the maintainer privately through GitHub).
3. Include steps to reproduce, affected module/function names, and potential impact.

We will acknowledge reports promptly and coordinate a fix and release advisory.
