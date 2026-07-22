"""Stable hashes and lineage records for analysis result groups."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .models import json_safe


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def source_run_fingerprint(run_path: Path | str, files: Iterable[str] = ("data.jsonl", "points.jsonl", "dataset_manifest.json")) -> dict[str, Any]:
    root = Path(run_path)
    hashes = {name: sha256_file(root / name) for name in files if (root / name).is_file()}
    return {"files": hashes, "fingerprint": stable_hash(hashes)}


def input_lineage(input_keys: Iterable[str]) -> list[str]:
    return [key if key.startswith(("live:", "analysis:")) else f"raw:{key}" for key in input_keys]
