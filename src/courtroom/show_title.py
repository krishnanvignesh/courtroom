"""Display a source document or code artifact and its metadata from manifest.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def get_title_record(manifest_path: str | Path, doc_id: str) -> dict[str, Any]:
    """Load metadata and source text for doc_id from manifest.json."""
    m_path = Path(manifest_path)
    data = json.loads(m_path.read_text(encoding="utf-8"))
    docs = data.get("documents", data) if isinstance(data, dict) else data
    for entry in docs:
        if str(entry.get("doc_id")) == doc_id:
            rec = dict(entry)
            if "text" not in rec and "source_path" in rec:
                src = Path(rec["source_path"])
                if not src.is_absolute():
                    src = (m_path.parent / src).resolve()
                if src.is_file():
                    rec["text"] = src.read_text(encoding="utf-8", errors="replace")
            return rec
    raise KeyError(f"Document '{doc_id}' not found in manifest {manifest_path}")


def format_title(rec: dict[str, Any]) -> str:
    lines = [
        f"=== Document: {rec.get('doc_id')} ===",
        f"Title: {rec.get('title', '(untitled)')}",
    ]
    if rec.get("source_path"):
        lines.append(f"Source Path: {rec['source_path']}")
    if rec.get("metadata"):
        lines.append(f"Metadata: {json.dumps(rec['metadata'], sort_keys=True)}")
    lines.append("--- Source Text ---")
    lines.append(str(rec.get("text", "")))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show source document / code artifact by doc_id.")
    parser.add_argument("--manifest", required=True, help="Path to sample manifest.json.")
    parser.add_argument("--id", required=True, dest="doc_id", help="Document ID to inspect.")
    args = parser.parse_args(argv)

    rec = get_title_record(args.manifest, args.doc_id)
    print(format_title(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
