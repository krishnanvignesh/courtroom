"""Zero-dependency stdio JSON-RPC MCP server exposing Courtroom tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from courtroom.closing import run_closing_hearing
from courtroom.court import run_court_round
from courtroom.evidence import verify_exhibit
from courtroom.law import assemble_law
from courtroom.opus_client import DEFAULT_COURT_MODEL, CourtClient
from courtroom.plan_court import challenge, judge
from courtroom.replay_gate import run_replay_gate

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "court_verify_evidence",
        "description": "Bailiff deterministic verification for verbatim quotes, AST citations, or command exhibits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "exhibit": {"type": "object"},
                "repo_root": {"type": "string"},
                "source_lookup": {"type": "object"},
            },
            "required": ["exhibit"],
        },
    },
    {
        "name": "court_assemble_law",
        "description": "Assemble hierarchical Parts 0-3 Law (Owner Decisions, Case Law, ENABLED Rules, Conventions).",
        "inputSchema": {
            "type": "object",
            "properties": {"law_dir": {"type": "string"}},
            "required": ["law_dir"],
        },
    },
    {
        "name": "court_challenge",
        "description": "Step 1: Challenge a plan (.json/.md/.yaml) with Prosecutor and Public Defender.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_path": {"type": "string"},
                "law_dir": {"type": "string"},
                "out_path": {"type": "string"},
                "budget_usd": {"type": "number"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "ledger_path": {"type": "string"},
                "cache_dir": {"type": "string"},
            },
            "required": ["plan_path", "law_dir"],
        },
    },
    {
        "name": "court_judge",
        "description": "Step 1: Judge a plan against challenges and rebuttals, recording verdict and precedents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_path": {"type": "string"},
                "rebuttal_path": {"type": "string"},
                "challenge_path": {"type": "string"},
                "law_dir": {"type": "string"},
                "out_path": {"type": "string"},
                "budget_usd": {"type": "number"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "ledger_path": {"type": "string"},
                "cache_dir": {"type": "string"},
            },
            "required": ["plan_path", "rebuttal_path", "challenge_path", "law_dir"],
        },
    },
    {
        "name": "court_replay_gate",
        "description": "Step 3a: Zero-cost replay gate and blast-radius boundary verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "baseline_path": {"type": "string"},
                "candidate_path": {"type": "string"},
                "expectations": {"type": "array", "items": {"type": "string"}},
                "plan_path": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["baseline_path", "candidate_path"],
        },
    },
    {
        "name": "court_trial_round",
        "description": "Step 3c: Run evaluation trials across sample artifacts with Bailiff fact-checking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ours_path": {"type": "string"},
                "manifest_path": {"type": "string"},
                "law_dir": {"type": "string"},
                "out_dir": {"type": "string"},
                "reuse_b_dir": {"type": "string"},
                "previous_round_dir": {"type": "string"},
                "appeals_path": {"type": "string"},
                "mode": {"type": "string"},
                "budget_usd": {"type": "number"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "ledger_path": {"type": "string"},
                "cache_dir": {"type": "string"},
            },
            "required": ["ours_path", "manifest_path", "law_dir", "out_dir"],
        },
    },
    {
        "name": "court_closing",
        "description": "Step 4: Run closing hearing over grouped round losses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "round_dir": {"type": "string"},
                "brief_path": {"type": "string"},
                "law_dir": {"type": "string"},
                "tracker_path": {"type": "string"},
                "budget_usd": {"type": "number"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "ledger_path": {"type": "string"},
                "cache_dir": {"type": "string"},
            },
            "required": ["round_dir", "brief_path", "law_dir"],
        },
    },
]


def _make_client(args: dict[str, Any]) -> CourtClient:
    return CourtClient(
        ledger_path=args.get("ledger_path", ".courtroom_data/ledger.json"),
        cache_dir=args.get("cache_dir", ".courtroom_data/cache"),
        budget_usd=float(args.get("budget_usd", 5.0)),
        model=str(args.get("model", DEFAULT_COURT_MODEL)),
        provider=str(args.get("provider", "mock")),
    )


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    """Execute a registered MCP courtroom tool by name."""
    if name == "court_verify_evidence":
        repo_root = Path(args["repo_root"]) if args.get("repo_root") else None
        return verify_exhibit(
            args["exhibit"],
            repo_root=repo_root,
            source_lookup=args.get("source_lookup"),
        )
    if name == "court_assemble_law":
        return {"law": assemble_law(args["law_dir"])}
    if name == "court_challenge":
        return challenge(
            plan_path=args["plan_path"],
            law_dir=args["law_dir"],
            client=_make_client(args),
            out_path=args.get("out_path"),
        )
    if name == "court_judge":
        return judge(
            plan_path=args["plan_path"],
            rebuttal_path=args["rebuttal_path"],
            challenge_path=args["challenge_path"],
            law_dir=args["law_dir"],
            client=_make_client(args),
            out_path=args.get("out_path"),
        )
    if name == "court_replay_gate":
        return run_replay_gate(
            baseline_path=args["baseline_path"],
            candidate_path=args["candidate_path"],
            expectations=args.get("expectations"),
            plan_path=args.get("plan_path"),
            changed_files=args.get("changed_files"),
        )
    if name == "court_trial_round":
        return run_court_round(
            ours_path=args["ours_path"],
            manifest_path=args["manifest_path"],
            law_dir=args["law_dir"],
            out_dir=args["out_dir"],
            client=_make_client(args),
            reuse_b_dir=args.get("reuse_b_dir"),
            previous_round_dir=args.get("previous_round_dir"),
            appeals_path=args.get("appeals_path"),
            mode=args.get("mode", "pipeline"),
        )
    if name == "court_closing":
        return run_closing_hearing(
            round_dir=args["round_dir"],
            brief_path=args["brief_path"],
            law_dir=args["law_dir"],
            client=_make_client(args),
            tracker_path=args.get("tracker_path"),
        )
    raise KeyError(f"Unknown MCP tool: '{name}'")


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP message and return response dict (or None for notifications)."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-courtroom", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        try:
            output = dispatch_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(output, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio() -> int:
    """Run line-delimited JSON-RPC MCP server on stdin/stdout."""
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        req = json.loads(stripped)
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
