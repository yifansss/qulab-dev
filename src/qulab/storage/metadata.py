"""Run metadata creation and updates."""

from __future__ import annotations

import json
import platform
from copy import deepcopy
from pathlib import Path
from typing import Any

from qulab import __version__

from .events import to_jsonable


class MetadataWriter:
    """Maintain metadata.json for a run."""

    def __init__(self, path: Path, run_id: str, experiment_name: str, started_at: str) -> None:
        self.path = path
        self.metadata: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "experiment_name": experiment_name,
            "started_at": started_at,
            "ended_at": None,
            "status": "running",
            "user": "unknown",
            "machine": platform.node(),
            "qulab_version": __version__,
            "git_commit": None,
            "resources": {},
            "sync": {},
            "data_keys": [],
            "point_count": 0,
            "completed_point_count": 0,
            "error_count": 0,
            "analysis_error_count": 0,
            "analysis_modules": [],
        }

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(to_jsonable(self.metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def add_data_specs(self, specs: dict[str, dict[str, Any]]) -> None:
        by_key = {item["key"]: deepcopy(item) for item in self.metadata["data_keys"]}
        for key, spec in specs.items():
            by_key[key] = {
                "key": key,
                "kind": spec.get("kind"),
                "unit": spec.get("unit"),
                "shape": spec.get("shape"),
                **{name: spec.get(name) for name in ("source_kind", "analysis_mode", "source_module", "module_version")
                   if spec.get(name) is not None},
            }
        self.metadata["data_keys"] = [by_key[key] for key in sorted(by_key)]

    def update_status(self, status: str, ended_at: str | None = None) -> None:
        self.metadata["status"] = status
        if ended_at is not None:
            self.metadata["ended_at"] = ended_at
