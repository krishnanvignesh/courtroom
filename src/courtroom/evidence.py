"""The Bailiff: deterministic forensic verification for quotes, AST symbols, and exhibits."""

from __future__ import annotations

import ast
import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINE_RANGE_RE = re.compile(r"^L(\d+)(?:-L?(\d+))?$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def normalize_whitespace(text: str, strip_html: bool = True) -> str:
    """Optionally strip HTML tags, unescape entities, and collapse whitespace."""
    cleaned = text
    if strip_html:
        cleaned = _TAG_RE.sub(" ", cleaned)
        cleaned = html.unescape(cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def verify_quote(quote: str, source_text: str, strip_html: bool = True) -> dict[str, Any]:
    """Verify whether quote appears verbatim in source_text after normalization."""
    norm_quote = normalize_whitespace(quote, strip_html=strip_html)
    if len(norm_quote) < 4:
        return {
            "status": "UNVERIFIED",
            "quote": quote,
            "match_offset": None,
            "reason": "Quote is shorter than the 4-character minimum after normalization.",
        }

    norm_source = normalize_whitespace(source_text, strip_html=strip_html)
    idx = norm_source.find(norm_quote)
    if idx == -1:
        return {
            "status": "UNVERIFIED",
            "quote": quote,
            "match_offset": None,
            "reason": "Normalized quote not found verbatim in source text.",
        }

    return {
        "status": "VERIFIED",
        "quote": quote,
        "match_offset": idx,
        "reason": f"Exact match at normalized offset {idx}.",
    }


def _find_ast_symbol(tree: ast.AST, symbol_path: str) -> ast.AST | None:
    """Locate a dotted symbol path (e.g. 'ClassName.method_name' or 'func_name') in an AST."""
    parts = [p for p in symbol_path.split(".") if p]
    if not parts:
        return None

    current_body: list[ast.stmt] = list(getattr(tree, "body", []))
    matched_node: ast.AST | None = None

    for idx, part in enumerate(parts):
        found: ast.AST | None = None
        for stmt in current_body:
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name == part:
                    found = stmt
                    break
            elif idx == len(parts) - 1:
                if isinstance(stmt, ast.Assign):
                    if any(
                        isinstance(t, ast.Name) and t.id == part
                        for t in stmt.targets
                    ):
                        found = stmt
                        break
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Name) and stmt.target.id == part:
                        found = stmt
                        break
        if found is None:
            return None
        matched_node = found
        current_body = list(getattr(found, "body", []))

    return matched_node


def verify_ast_citation(
    file_path: str | Path,
    symbol_or_lines: str,
    repo_root: str | Path,
) -> dict[str, Any]:
    """Verify a code citation by line range ('L10-L25') or Python AST symbol."""
    root = Path(repo_root).resolve()
    rel = Path(file_path)
    candidate = rel.resolve() if rel.is_absolute() else (root / rel).resolve()
    target = f"{file_path}:{symbol_or_lines}"

    try:
        candidate.relative_to(root)
    except ValueError:
        return {
            "status": "UNVERIFIED",
            "target": target,
            "reason": f"Path '{file_path}' escapes repository root.",
        }

    if not candidate.is_file():
        return {
            "status": "UNVERIFIED",
            "target": target,
            "reason": f"File not found: '{file_path}'.",
        }

    source = candidate.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()

    line_match = _LINE_RANGE_RE.match(symbol_or_lines.strip())
    if line_match:
        start = int(line_match.group(1))
        end = int(line_match.group(2) or start)
        if start < 1 or end < start or end > len(lines):
            return {
                "status": "UNVERIFIED",
                "target": target,
                "reason": f"Line range L{start}-L{end} out of bounds (file has {len(lines)} lines).",
            }
        snippet = "\n".join(lines[start - 1 : end])
        return {
            "status": "VERIFIED",
            "target": target,
            "reason": f"Verified lines L{start}-L{end} ({len(snippet)} chars).",
        }

    if candidate.suffix.lower() != ".py":
        return {
            "status": "UNVERIFIED",
            "target": target,
            "reason": f"AST symbol lookup is only supported for Python files, got '{candidate.suffix}'.",
        }

    try:
        tree = ast.parse(source, filename=str(candidate))
    except SyntaxError as exc:
        return {
            "status": "UNVERIFIED",
            "target": target,
            "reason": f"SyntaxError parsing '{file_path}': {exc}",
        }

    node = _find_ast_symbol(tree, symbol_or_lines.strip())
    if node is None:
        return {
            "status": "UNVERIFIED",
            "target": target,
            "reason": f"Symbol '{symbol_or_lines}' not found in '{file_path}'.",
        }

    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", lineno)
    return {
        "status": "VERIFIED",
        "target": target,
        "reason": f"AST symbol '{symbol_or_lines}' verified at L{lineno}-L{end_lineno}.",
    }


def run_command_exhibit(
    command: str,
    cwd: str | Path,
    timeout: int = 30,
) -> dict[str, Any]:
    """Execute a deterministic command exhibit and capture exit code + output digest."""
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return {
        "command": command,
        "exit_code": proc.returncode,
        "output_sha256": digest,
        "output_preview": combined[:500].strip(),
        "status": "VERIFIED" if proc.returncode == 0 else "UNVERIFIED",
    }


def _split_ast_ref(ast_ref: str) -> tuple[str, str] | None:
    """Split 'path/to/file.py:Symbol' into (file_path, symbol_or_lines)."""
    if ":" not in ast_ref:
        return None
    # Handle Windows drive prefixes only if there is a trailing :symbol
    idx = ast_ref.rfind(":")
    if idx <= 1:
        return None
    return ast_ref[:idx], ast_ref[idx + 1 :]


def verify_exhibit(
    exhibit: dict[str, Any],
    repo_root: Path | None = None,
    source_lookup: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify a plan evidence item or citation via quote, AST ref, or command exhibit."""
    quote = exhibit.get("quote")
    source_key = str(exhibit.get("source", ""))
    ast_ref = exhibit.get("ast_ref")
    command = exhibit.get("command")
    exit_code = exhibit.get("exit_code")
    output_sha256 = exhibit.get("output_sha256")

    if ast_ref:
        parsed = _split_ast_ref(str(ast_ref))
        if parsed is None:
            return {
                "status": "UNVERIFIED",
                "id": exhibit.get("id"),
                "reason": f"Malformed ast_ref '{ast_ref}'. Expected 'file:SymbolOrLines'.",
            }
        file_part, symbol_part = parsed
        root = repo_root or Path.cwd()
        res = verify_ast_citation(file_part, symbol_part, root)
        res["id"] = exhibit.get("id")
        return res

    if quote:
        source_text = None
        if source_lookup and source_key in source_lookup:
            source_text = source_lookup[source_key]
        elif repo_root is not None and source_key:
            candidate = (repo_root / source_key).resolve()
            try:
                candidate.relative_to(repo_root.resolve())
                if candidate.is_file():
                    source_text = candidate.read_text(encoding="utf-8", errors="replace")
            except ValueError:
                source_text = None

        if source_text is None:
            return {
                "status": "UNVERIFIED",
                "id": exhibit.get("id"),
                "quote": quote,
                "reason": f"Source '{source_key}' could not be loaded for quote verification.",
            }
        res = verify_quote(str(quote), source_text)
        res["id"] = exhibit.get("id")
        return res

    if command is not None:
        if exit_code is None:
            return {
                "status": "UNVERIFIED",
                "id": exhibit.get("id"),
                "reason": "Command exhibit missing recorded exit_code.",
            }
        if output_sha256 is not None and not _SHA256_RE.match(str(output_sha256)):
            return {
                "status": "UNVERIFIED",
                "id": exhibit.get("id"),
                "reason": "Command exhibit has invalid output_sha256 format.",
            }
        status = "VERIFIED" if int(exit_code) == 0 else "UNVERIFIED"
        return {
            "status": status,
            "id": exhibit.get("id"),
            "command": command,
            "exit_code": int(exit_code),
            "reason": (
                f"Recorded command exhibit exited with {exit_code}."
                if status == "VERIFIED"
                else f"Command exhibit failed with exit_code={exit_code}."
            ),
        }

    # Check if source itself is an AST ref like path/file.py:Symbol
    if ":" in source_key and not source_key.startswith("http"):
        parsed = _split_ast_ref(source_key)
        if parsed and repo_root is not None:
            res = verify_ast_citation(parsed[0], parsed[1], repo_root)
            res["id"] = exhibit.get("id")
            return res

    return {
        "status": "UNVERIFIED",
        "id": exhibit.get("id"),
        "reason": "Exhibit contains no verifiable quote, ast_ref, or command.",
    }
