"""Unified CLI entrypoint for Agent Courtroom (`courtroom`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from courtroom import (
    build_sample,
    closing,
    court,
    doc_check,
    law,
    list_losses,
    mcp_server,
    plan_court,
    replay_gate,
    report,
    run_pipeline,
    show_title,
    show_trial,
)


def _find_repo_skills_dir() -> Path:
    # Works both in editable installs and inside repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / "courtroom"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Could not locate skills/courtroom directory.")


def render_skill_text(
    template_text: str,
    values: dict[str, str],
) -> str:
    """Substitute {{PLACEHOLDER}} keys in SKILL.md template."""
    rendered = template_text
    for key, val in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", val)
    return rendered


def init_workspace(target_dir: str | Path, preset: str = "software-default") -> Path:
    """Initialize a workspace with law files, tracker, plans dir, and rendered SKILL.md."""
    root = Path(target_dir)
    skills_dir = _find_repo_skills_dir()
    preset_file = skills_dir / "presets" / f"{preset}.json"
    if not preset_file.is_file():
        raise FileNotFoundError(f"Preset not found: {preset_file}")
    preset_data = json.loads(preset_file.read_text(encoding="utf-8"))

    law_dir = root / "law"
    plans_dir = root / "plans"
    law_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)

    od_file = law_dir / "owner_decisions.md"
    if not od_file.exists():
        od_file.write_text(
            "# Owner Decisions (Part 0 Law)\n\n"
            "## 2026-01-01 | OD-1\n"
            "> Prioritize deterministic verification before trusting model assertions.\n",
            encoding="utf-8",
        )

    case_file = law_dir / "CASE_LAW.json"
    if not case_file.exists():
        case_file.write_text('{"precedents": []}\n', encoding="utf-8")

    rb_file = law_dir / "rulebook.json"
    if not rb_file.exists():
        rb_file.write_text(
            json.dumps(
                {
                    "version": "0.1.0",
                    "changelog": ["0.1.0: Initial workspace rulebook"],
                    "rules": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    conv_file = law_dir / "conventions.md"
    if not conv_file.exists():
        conv_file.write_text(
            "# Part 3 Conventions\n\n- Format only modified files.\n- Cite rule IDs in tests.\n",
            encoding="utf-8",
        )

    tracker = root / "tracker.md"
    if not tracker.exists():
        tracker.write_text("# Courtroom Progress Tracker\n", encoding="utf-8")

    template = (skills_dir / "SKILL.md").read_text(encoding="utf-8")
    rendered = render_skill_text(template, preset_data)
    skill_out = root / "SKILL.md"
    skill_out.write_text(rendered, encoding="utf-8")
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="courtroom", description="Agent Courtroom CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize a courtroom workspace with preset.")
    p_init.add_argument("--dir", default=".", help="Target workspace directory.")
    p_init.add_argument(
        "--preset",
        default="software-default",
        choices=["boe-pipeline", "software-default", "arch-default"],
    )

    p_render = sub.add_parser("render-skill", help="Render SKILL.md template from a preset or args.")
    p_render.add_argument("--preset", choices=["boe-pipeline", "software-default", "arch-default"])
    p_render.add_argument("--project")
    p_render.add_argument("--system")
    p_render.add_argument("--prod-model")
    p_render.add_argument("--court-model")
    p_render.add_argument("--skill-path")
    p_render.add_argument("--court-code-dir")
    p_render.add_argument("--out", required=True, help="Output SKILL.md path.")

    # Subcommands delegating directly to module mains
    passthrough_cmds = (
        "law",
        "plan",
        "replay-gate",
        "run-pipeline",
        "trial",
        "closing",
        "report",
        "losses",
        "show-title",
        "show-trial",
        "build-sample",
        "doc-check",
        "mcp",
    )
    for cmd_name in passthrough_cmds:
        sub.add_parser(cmd_name, add_help=False)

    args, rest = parser.parse_known_args(argv)

    if args.command == "init":
        out = init_workspace(args.dir, preset=args.preset)
        print(f"Initialized Courtroom workspace at {out} (preset={args.preset}).")
        return 0

    if args.command == "render-skill":
        skills_dir = _find_repo_skills_dir()
        values: dict[str, str] = {}
        if args.preset:
            values.update(
                json.loads((skills_dir / "presets" / f"{args.preset}.json").read_text(encoding="utf-8"))
            )
        overrides = {
            "PROJECT": args.project,
            "SYSTEM_UNDER_TEST": args.system,
            "PROD_MODEL": args.prod_model,
            "COURT_MODEL": args.court_model,
            "PATH": args.skill_path,
            "COURT_CODE_DIR": args.court_code_dir,
        }
        for k, v in overrides.items():
            if v is not None:
                values[k] = v
        template = (skills_dir / "SKILL.md").read_text(encoding="utf-8")
        rendered = render_skill_text(template, values)
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(rendered, encoding="utf-8")
        print(f"Rendered SKILL.md -> {out_p}")
        return 0

    dispatch = {
        "law": law.main,
        "plan": plan_court.main,
        "replay-gate": replay_gate.main,
        "run-pipeline": run_pipeline.main,
        "trial": court.main,
        "closing": closing.main,
        "report": report.main,
        "losses": list_losses.main,
        "show-title": show_title.main,
        "show-trial": show_trial.main,
        "build-sample": build_sample.main,
        "doc-check": doc_check.main,
        "mcp": mcp_server.main,
    }
    return dispatch[args.command](rest)


if __name__ == "__main__":
    raise SystemExit(main())
