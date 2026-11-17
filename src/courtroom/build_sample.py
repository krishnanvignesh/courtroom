"""Build deterministic stratified sample manifests (`manifest.json`)."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


def build_sample_manifest(
    source_dir: str | Path,
    out_manifest: str | Path,
    limit: int = 200,
    seed: int = 42,
    extensions: tuple[str, ...] = (".txt", ".html", ".htm", ".md", ".py"),
) -> dict[str, Any]:
    """Scan source_dir (or JSONL files) and emit a deterministic sample manifest.json."""
    src = Path(source_dir)
    candidates: list[dict[str, Any]] = []

    if src.is_file() and src.suffix.lower() == ".jsonl":
        for idx, line in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            doc_id = str(item.get("doc_id") or f"DOC-{idx:03d}")
            text = str(item.get("text", ""))
            candidates.append(
                {
                    "doc_id": doc_id,
                    "title": item.get("title", doc_id),
                    "stratum": item.get("stratum", "default"),
                    "text": text,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
    else:
        files = sorted(
            p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in extensions
        )
        for p in files:
            rel = p.relative_to(src).as_posix()
            text = p.read_text(encoding="utf-8", errors="replace")
            stratum = p.parent.name if p.parent != src else "root"
            candidates.append(
                {
                    "doc_id": p.stem,
                    "title": rel,
                    "stratum": stratum,
                    "source_path": str(p.resolve()),
                    "text": text,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )

    # Deterministic stratified sampling
    rng = random.Random(seed)
    by_stratum: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_stratum.setdefault(str(c["stratum"]), []).append(c)

    for bucket in by_stratum.values():
        rng.shuffle(bucket)

    selected: list[dict[str, Any]] = []
    strata_keys = sorted(by_stratum.keys())
    while len(selected) < limit and any(by_stratum[k] for k in strata_keys):
        for k in strata_keys:
            if by_stratum[k] and len(selected) < limit:
                selected.append(by_stratum[k].pop(0))

    manifest = {
        "seed": seed,
        "total_candidates": len(candidates),
        "sample_size": len(selected),
        "documents": selected,
    }
    out = Path(out_manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic stratified sample manifest.")
    parser.add_argument("--source", required=True, help="Directory of files or .jsonl corpus.")
    parser.add_argument("--out", required=True, help="Output manifest.json path.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    manifest = build_sample_manifest(
        source_dir=args.source,
        out_manifest=args.out,
        limit=args.limit,
        seed=args.seed,
    )
    print(f"Built manifest with {manifest['sample_size']} document(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
