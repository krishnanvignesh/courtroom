"""Tests for evidence.py (The Bailiff): quotes, AST symbols, and command exhibits."""

from __future__ import annotations

import hashlib
from pathlib import Path

from courtroom.evidence import (
    normalize_whitespace,
    run_command_exhibit,
    verify_ast_citation,
    verify_exhibit,
    verify_quote,
)


def test_normalize_and_verify_html_quote() -> None:
    html_src = "<div class='notice'>Permit #A-100  is\n  <b>GRANTED</b>  for   Block 4.</div>"
    assert normalize_whitespace(html_src) == "Permit #A-100 is GRANTED for Block 4."

    ok = verify_quote("Permit #A-100 is GRANTED for Block 4", html_src)
    assert ok["status"] == "VERIFIED"
    assert ok["match_offset"] == 0

    bad = verify_quote("Permit #A-100 is DENIED", html_src)
    assert bad["status"] == "UNVERIFIED"

    short = verify_quote("is", html_src)
    assert short["status"] == "UNVERIFIED"


def test_verify_ast_citation_symbols_lines_and_traversal(tmp_path: Path) -> None:
    src_file = tmp_path / "app" / "service.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text(
        "\n".join(
            [
                "MAX_RETRIES = 3",
                "",
                "def helper():",
                "    return 42",
                "",
                "class Processor:",
                "    def run(self, x):",
                "        return x + 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert verify_ast_citation("app/service.py", "helper", tmp_path)["status"] == "VERIFIED"
    assert verify_ast_citation("app/service.py", "Processor.run", tmp_path)["status"] == "VERIFIED"
    assert verify_ast_citation("app/service.py", "MAX_RETRIES", tmp_path)["status"] == "VERIFIED"
    assert verify_ast_citation("app/service.py", "L3-L4", tmp_path)["status"] == "VERIFIED"

    assert verify_ast_citation("app/service.py", "Processor.missing", tmp_path)["status"] == "UNVERIFIED"
    assert verify_ast_citation("app/service.py", "L1-L999", tmp_path)["status"] == "UNVERIFIED"
    assert verify_ast_citation("../outside.py", "L1", tmp_path)["status"] == "UNVERIFIED"


def test_run_and_verify_command_exhibit(tmp_path: Path) -> None:
    res = run_command_exhibit('python -c "print(123)"', cwd=tmp_path)
    assert res["status"] == "VERIFIED"
    assert res["exit_code"] == 0
    assert len(res["output_sha256"]) == 64

    exhibit_ok = verify_exhibit(
        {
            "id": "E1",
            "source": "shell",
            "finding": "Outputs 123",
            "command": res["command"],
            "exit_code": 0,
            "output_sha256": hashlib.sha256(b"123\n").hexdigest(),
        }
    )
    assert exhibit_ok["status"] == "VERIFIED"

    exhibit_fail = verify_exhibit(
        {
            "id": "E2",
            "source": "shell",
            "finding": "Failing command",
            "command": "false",
            "exit_code": 1,
        }
    )
    assert exhibit_fail["status"] == "UNVERIFIED"
