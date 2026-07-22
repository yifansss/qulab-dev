"""Atomic append-only storage for post-run analysis results."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from qulab.core import DerivedData
from qulab.storage.advanced_writer import AdvancedDatasetWriter
from qulab.storage.dataset import DatasetJsonlWriter
from qulab.storage.events import to_jsonable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisResultStore:
    def __init__(self, source_run: Path | str, result_id: str, *, backends: list[str] | None = None,
                 analysis_config: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", result_id):
            raise ValueError("result_id must contain only letters, digits, dot, underscore, or dash")
        self.source_run = Path(source_run)
        self.analysis_root = self.source_run / "analysis"
        self.result_id = result_id
        self.final_path = self.analysis_root / result_id
        self.temp_path = self.analysis_root / f".tmp_{uuid.uuid4().hex}"
        self.backends = backends or ["csv"]
        self.analysis_config = analysis_config or {}
        self.metadata = {"schema_version": 1, "result_id": result_id, "analysis_mode": "post",
                         "source_run": str(self.source_run), "status": "running", "started_at": _now(),
                         "ended_at": None, "point_count": 0, "skipped_point_count": 0, "error_count": 0,
                         **(metadata or {})}
        self.dataset_writer: DatasetJsonlWriter | None = None
        self.advanced_writer: AdvancedDatasetWriter | None = None
        self._opened = False

    def open(self) -> None:
        if self.final_path.exists():
            raise FileExistsError(f"analysis result already exists: {self.final_path}")
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        self.temp_path.mkdir(parents=False, exist_ok=False)
        (self.temp_path / "analysis_config.yaml").write_text(yaml.safe_dump(self.analysis_config, sort_keys=True), encoding="utf-8")
        self.dataset_writer = DatasetJsonlWriter(self.temp_path / "data.jsonl"); self.dataset_writer.open()
        self.advanced_writer = AdvancedDatasetWriter(self.temp_path, self.backends); self.advanced_writer.open()
        self._write_metadata()
        self._history("started")
        self._opened = True

    def append(self, event: DerivedData, *, point_status: str = "ok") -> None:
        if not self._opened or self.dataset_writer is None or self.advanced_writer is None:
            raise RuntimeError("analysis result store is not open")
        payload = self.dataset_writer.append_derived_data(event)
        payload["result_id"] = self.result_id
        for spec in payload["data_specs"].values():
            spec["result_id"] = self.result_id
            spec["input_lineage"] = list(self.metadata.get("input_lineage", []))
        self.advanced_writer.add_point_started(event.point_id, event.coords, event.timestamp)
        self.advanced_writer.add_data_point(payload)
        self.advanced_writer.add_point_completed(event.point_id, point_status, event.coords, event.timestamp)
        self.metadata["point_count"] += 1

    def commit(self) -> Path:
        if not self._opened:
            raise RuntimeError("analysis result store is not open")
        assert self.dataset_writer is not None and self.advanced_writer is not None
        self.dataset_writer.close(); self.advanced_writer.close()
        self.metadata.update(status="completed", ended_at=_now())
        self._write_metadata()
        if self.final_path.exists():
            raise FileExistsError(f"analysis result already exists: {self.final_path}")
        self.temp_path.replace(self.final_path)
        self._history("completed", path=str(self.final_path.relative_to(self.source_run)))
        self._opened = False
        return self.final_path

    def fail(self, error: BaseException) -> None:
        if self.dataset_writer is not None: self.dataset_writer.close()
        self.metadata.update(status="failed", ended_at=_now(), error_count=self.metadata.get("error_count", 0) + 1,
                             error_type=type(error).__name__, error_message=str(error))
        if self.temp_path.exists(): self._write_metadata()
        self._history("failed", error_type=type(error).__name__, message=str(error))
        self._opened = False

    def _write_metadata(self) -> None:
        path = self.temp_path / "metadata.json"
        path.write_text(json.dumps(to_jsonable(self.metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _history(self, event: str, **extra: Any) -> None:
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": _now(), "event": event, "result_id": self.result_id, **extra}
        with (self.analysis_root / "history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(to_jsonable(record), sort_keys=True, separators=(",", ":")) + "\n")


def cleanup_stale_temps(run_path: Path | str) -> list[Path]:
    root = Path(run_path) / "analysis"
    removed: list[Path] = []
    if not root.exists(): return removed
    import shutil
    for path in root.iterdir():
        if path.is_dir() and path.name.startswith(".tmp_"):
            shutil.rmtree(path); removed.append(path)
    return removed
