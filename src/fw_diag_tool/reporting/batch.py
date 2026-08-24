from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_batch_manifest(entries: list[dict[str, Any]]) -> str:
    """Build a batch manifest JSON for CI pipelines.

    Each entry must contain at minimum: file, protocol, and status.
    Optional: findings_count, output_path.
    """
    manifest = {
        "schema_version": "1.0",
        "entries": entries,
        "total": len(entries),
        "passed": sum(1 for e in entries if e.get("status") == "success"),
        "failed": sum(1 for e in entries if e.get("status") not in ("success", "warning")),
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def write_batch_manifest(entries: list[dict[str, Any]], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_batch_manifest(entries), encoding="utf-8")
    return output_path


__all__ = ["build_batch_manifest", "write_batch_manifest"]
