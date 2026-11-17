"""Tests for doc_check.py, skill template rendering, init, and MCP JSON-RPC server."""

from __future__ import annotations

import json
from pathlib import Path

from courtroom.cli import init_workspace, render_skill_text
from courtroom.doc_check import run_doc_check
from courtroom.law import bump_rulebook_version, record_owner_decision
from courtroom.mcp_server import handle_request


def test_doc_check_template_vs_rendered_and_rulebook_sync(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template_skill = repo_root / "skills" / "courtroom" / "SKILL.md"

    # Template has unresolved placeholders -> passes non-strict with warnings, fails require_rendered
    res_tmpl = run_doc_check(template_skill, require_rendered=False)
    assert res_tmpl["passed"] is True
    assert res_tmpl["warnings"]

    res_strict = run_doc_check(template_skill, require_rendered=True)
    assert res_strict["passed"] is False

    # Init workspace + doc_check strict pass
    ws = init_workspace(tmp_path / "ws", preset="boe-pipeline")
    law_dir = ws / "law"
    record_owner_decision(law_dir, "OD-2", "2026-02-01", "Never regress baseline.")
    bump_rulebook_version(law_dir, "0.2.0", "Add second rulebook version")

    res_ws = run_doc_check(ws / "SKILL.md", law_dir=law_dir, require_rendered=True)
    assert res_ws["passed"] is True
    assert "Haiku 4.5" in (ws / "SKILL.md").read_text(encoding="utf-8")

    # Render custom skill text check
    rendered = render_skill_text("Project={{PROJECT}}", {"PROJECT": "DemoX"})
    assert rendered == "Project=DemoX"


def test_mcp_server_jsonrpc_handlers(tmp_path: Path) -> None:
    init_resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "agent-courtroom"

    list_resp = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert list_resp is not None
    names = {t["name"] for t in list_resp["result"]["tools"]}
    assert {"court_verify_evidence", "court_assemble_law", "court_challenge", "court_judge"} <= names

    call_resp = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "court_verify_evidence",
                "arguments": {
                    "exhibit": {
                        "id": "E1",
                        "source": "doc1",
                        "quote": "exact clause here",
                    },
                    "source_lookup": {"doc1": "<p>Here is the exact clause here inside html.</p>"},
                },
            },
        }
    )
    assert call_resp is not None
    assert call_resp["result"]["isError"] is False
    payload = json.loads(call_resp["result"]["content"][0]["text"])
    assert payload["status"] == "VERIFIED"


def test_release_files_and_sample_workspace_integrity() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sample_ws = repo_root / "examples" / "sample_workspace"
    res = run_doc_check(
        sample_ws / "SKILL.md",
        law_dir=sample_ws / "law",
        require_rendered=True,
    )
    assert res["passed"] is True
    assert res["errors"] == []

    required_files = [
        repo_root / "README.md",
        repo_root / "CONTRIBUTING.md",
        repo_root / "CHANGELOG.md",
        repo_root / "SECURITY.md",
        repo_root / "LICENSE",
        repo_root / ".github" / "workflows" / "ci.yml",
    ]
    for path in required_files:
        assert path.is_file(), f"Missing release file: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"Release file is empty: {path}"
