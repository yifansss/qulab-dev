"""Run directory orchestration for storage subscribers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, TextIO

import yaml

from qulab.core import (
    DataPoint,
    DerivedData,
    AnalysisStatus,
    ErrorRaised,
    Event,
    InstrumentSnapshot,
    LogMessage,
    MeasurementCompleted,
    MeasurementStarted,
    SequenceSelected,
)
from qulab.sequence_bundles import SequenceBundle
from qulab.sequence_files import sequence_artifact_snapshots

from .advanced_writer import AdvancedDatasetWriter
from .backends import normalize_storage_backends
from .dataset import DatasetJsonlWriter, PointsJsonlWriter, infer_data_specs
from .events import EventJsonlWriter, to_jsonable
from .index import RunIndex
from .metadata import MetadataWriter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()).strip("._-")
    return normalized or "experiment"


class RunStore:
    """Persist core events into one run directory."""

    def __init__(
        self,
        root: Path | str = "runs",
        experiment_name: str = "experiment",
        config: dict[str, Any] | None = None,
        resolved_config: dict[str, Any] | None = None,
        run_id: str | None = None,
        backends: list[str] | tuple[str, ...] | str | None = None,
        sequence_bundles: dict[str, SequenceBundle] | None = None,
        sequence_preparation: Any | None = None,
        analysis_plan: Any | None = None,
    ) -> None:
        self.root = Path(root)
        self.experiment_name = _safe_name(experiment_name)
        self.config = config
        self.resolved_config = resolved_config
        self.backends = normalize_storage_backends(config, resolved_config, backends)
        self.sequence_bundles = dict(sequence_bundles or {})
        self.sequence_preparation = sequence_preparation
        self.analysis_plan = analysis_plan
        self._explicit_run_id = _safe_name(run_id) if run_id else None
        self.run_id = self._explicit_run_id or ""
        self._run_path: Path | None = None
        self.index = RunIndex(self.root / "run_index.sqlite")
        self.metadata_writer: MetadataWriter | None = None
        self.event_writer: EventJsonlWriter | None = None
        self.dataset_writer: DatasetJsonlWriter | None = None
        self.points_writer: PointsJsonlWriter | None = None
        self.advanced_writer: AdvancedDatasetWriter | None = None
        self._points: dict[str, dict[str, Any]] = {}
        self._sequence_selection_file: TextIO | None = None
        self._sequence_artifacts: dict[tuple[str, str, str], str] = {}
        self._is_open = False
        self._raw_keys: set[str] = set()
        self._derived_keys: set[str] = set()
        self._event_lock = RLock()

    @property
    def run_path(self) -> Path:
        if self._run_path is None:
            raise RuntimeError("RunStore is not open")
        return self._run_path

    def open(self) -> None:
        if self._is_open:
            return

        started_at = _now()
        self._run_path = self._create_run_path(started_at)
        self.run_id = self._run_path.name
        self._run_path.mkdir(parents=True, exist_ok=False)

        if self.config is not None:
            (self._run_path / "config.yaml").write_text(yaml.safe_dump(self.config, sort_keys=True), encoding="utf-8")
        if self.resolved_config is not None:
            (self._run_path / "resolved_config.yaml").write_text(
                yaml.safe_dump(self.resolved_config, sort_keys=True), encoding="utf-8"
            )
        (self._run_path / "logs.txt").touch()

        self.metadata_writer = MetadataWriter(
            self._run_path / "metadata.json", self.run_id, self.experiment_name, started_at
        )
        if self.config is not None:
            self.metadata_writer.metadata["config_sha256"] = _sha256(self._run_path / "config.yaml")
            self.metadata_writer.metadata["resources"] = to_jsonable(self.config.get("resources", {}))
            self.metadata_writer.metadata["sync"] = to_jsonable(self.config.get("sync", {}))
        if self.resolved_config is not None:
            self.metadata_writer.metadata["resolved_config_sha256"] = _sha256(self._run_path / "resolved_config.yaml")
        if self.analysis_plan is not None:
            self.metadata_writer.metadata["analysis_modules"] = [
                module.to_dict() for module in self.analysis_plan.modules
            ]
        if self.config is not None:
            self.metadata_writer.metadata["sequence_snapshots"] = sequence_artifact_snapshots(self.config, self._run_path)
        if self.sequence_bundles:
            self._prepare_sequence_bundles()
            self._sequence_selection_file = (self._run_path / "sequence_selections.jsonl").open(
                "a", encoding="utf-8"
            )
        if self.sequence_preparation is not None and self.sequence_preparation.generation_records:
            self._prepare_sequence_generation()
        self.event_writer = EventJsonlWriter(self._run_path / "events.jsonl")
        self.dataset_writer = DatasetJsonlWriter(self._run_path / "data.jsonl")
        self.points_writer = PointsJsonlWriter(self._run_path / "points.jsonl")
        self.advanced_writer = AdvancedDatasetWriter(self._run_path, self.backends) if self.backends else None

        self.event_writer.open()
        self.dataset_writer.open()
        self.points_writer.open()
        if self.advanced_writer is not None:
            self.advanced_writer.open()
        self.metadata_writer.write()
        self._safe_index(self.index.initialize)
        self._upsert_run()
        self._is_open = True

    def handle_event(self, event: Event) -> None:
        # Analysis can emit derived events from a worker while acquisition is
        # still publishing snapshots.  Serialize the complete append/update/
        # metadata-write transaction so both threads cannot replace the same
        # metadata.json.tmp file or publish metadata out of order.
        with self._event_lock:
            self._handle_event(event)

    def _handle_event(self, event: Event) -> None:
        if not self._is_open:
            raise RuntimeError("RunStore must be opened before handling events")
        assert self.event_writer is not None
        assert self.metadata_writer is not None

        if isinstance(event, DerivedData) and not event.save:
            return
        self.event_writer.append(event)

        if isinstance(event, DataPoint):
            self._handle_data_point(event)
        elif isinstance(event, DerivedData):
            self._handle_derived_data(event)
        elif isinstance(event, AnalysisStatus):
            if event.state in {"warning", "failed"}:
                self.metadata_writer.metadata["analysis_error_count"] += 1
                self.metadata_writer.write()
        elif isinstance(event, SequenceSelected):
            self._handle_sequence_selected(event)
        elif isinstance(event, MeasurementStarted):
            self._handle_measurement_started(event)
        elif isinstance(event, MeasurementCompleted):
            self._handle_measurement_completed(event)
        elif isinstance(event, ErrorRaised):
            self.metadata_writer.metadata["error_count"] += 1
            self.metadata_writer.write()
            self._upsert_run()
        elif isinstance(event, InstrumentSnapshot):
            snapshots = self.metadata_writer.metadata.setdefault("instrument_snapshots", {})
            snapshots[event.resource] = {
                "action": event.action,
                "point_id": event.point_id,
                "coords": to_jsonable(event.coords),
                "timestamp": event.timestamp,
                "snapshot": to_jsonable(event.snapshot),
            }
            self.metadata_writer.write()
        elif isinstance(event, LogMessage):
            self._append_log(event)

    def close(self, status: str = "completed") -> None:
        if not self._is_open:
            return
        assert self.metadata_writer is not None

        final_status = "failed" if status in {"failed", "error"} else status
        ended_at = _now()
        for point_id, record in list(self._points.items()):
            if record.get("status") == "running":
                record["status"] = "partial"
                record["completed_at"] = None
                self._write_point(record)
                if self.advanced_writer is not None:
                    self.advanced_writer.add_point_completed(
                        point_id,
                        "partial",
                        record.get("coords", {}),
                        completed_at="",
                    )
        self.metadata_writer.update_status(final_status, ended_at=ended_at)
        self.metadata_writer.write()
        if self.advanced_writer is not None:
            self.advanced_writer.close()
        self._upsert_run()

        for writer in (self.event_writer, self.dataset_writer, self.points_writer):
            if writer is not None:
                writer.close()
        if self._sequence_selection_file is not None:
            self._sequence_selection_file.close()
            self._sequence_selection_file = None
        self._is_open = False

    def set_analysis_summary(self, summary: dict[str, Any]) -> None:
        with self._event_lock:
            if not self._is_open or self.metadata_writer is None:
                raise RuntimeError("RunStore must be open to record analysis summary")
            self.metadata_writer.metadata["analysis_summary"] = to_jsonable(summary)
            self.metadata_writer.write()

    def _prepare_sequence_bundles(self) -> None:
        assert self.metadata_writer is not None
        summaries: list[dict[str, Any]] = []
        for bundle in self.sequence_bundles.values():
            current_hash = _sha256(bundle.manifest_path)
            if current_hash != bundle.manifest_sha256:
                raise RuntimeError(
                    f"Sequence bundle '{bundle.id}' manifest changed before run open: {bundle.manifest_path}"
                )
            bundle_dir = self.run_path / "artifacts" / "sequences" / _safe_name(bundle.id)
            bundle_dir.mkdir(parents=True, exist_ok=True)
            manifest_target = bundle_dir / "manifest.yaml"
            shutil.copy2(bundle.manifest_path, manifest_target)
            if _sha256(manifest_target) != bundle.manifest_sha256:
                raise RuntimeError(f"Copied manifest hash mismatch for sequence bundle '{bundle.id}'")
            summaries.append(
                {
                    "id": bundle.id,
                    "resource": bundle.resource,
                    "manifest_source": str(bundle.manifest_path),
                    "manifest_artifact": str(manifest_target.relative_to(self.run_path)),
                    "manifest_sha256": bundle.manifest_sha256,
                    "entry_count": len(bundle.entries),
                    "coordinates": list(bundle.entries[0].coordinates),
                }
            )
        self.metadata_writer.metadata["sequence_bundles"] = summaries
        self.metadata_writer.metadata["sequence_selection_count"] = 0
        self.metadata_writer.metadata["sequence_selection_table"] = "sequence_selections.jsonl"

    def _prepare_sequence_generation(self) -> None:
        assert self.metadata_writer is not None
        preparation = self.sequence_preparation
        root = self.run_path / "artifacts" / "sequence_generation"
        for plan_id, plan in preparation.plans.items():
            target = root / _safe_name(plan_id)
            target.mkdir(parents=True, exist_ok=True)
            (target / "sequence_plan.yaml").write_text(yaml.safe_dump(plan.to_dict(), sort_keys=False), encoding="utf-8")
            bundle = preparation.materialized[plan_id]
            (target / "provider_identity.json").write_text(
                json.dumps(bundle.source_identity.to_dict(), sort_keys=True, indent=2), encoding="utf-8"
            )
            record = next(item for item in preparation.generation_records if item.plan_id == plan_id)
            (target / "generation_log.txt").write_text(
                f"status={record.status}\ncache_hit={record.cache_hit}\npoint_count={record.point_count}\nplan_hash={record.plan_hash}\n",
                encoding="utf-8",
            )
        self.metadata_writer.metadata["sequence_generation"] = [item.to_dict() for item in preparation.generation_records]
        self.metadata_writer.metadata["experiment_parameters"] = preparation.experiment_parameters

    def _handle_sequence_selected(self, event: SequenceSelected) -> None:
        assert self.metadata_writer is not None
        if self._sequence_selection_file is None:
            raise RuntimeError("RunStore has no sequence bundle registry for SequenceSelected event")
        source = Path(event.sequence_file)
        actual_hash = _sha256(source)
        if actual_hash != event.sequence_sha256:
            raise RuntimeError(
                f"Sequence bundle '{event.bundle_id}' entry '{event.entry_id}' source changed before artifact copy: "
                f"{source}"
            )
        key = (event.bundle_id, event.entry_id, event.sequence_sha256)
        artifact_path = self._sequence_artifacts.get(key)
        if artifact_path is None:
            bundle_dir = self.run_path / "artifacts" / "sequences" / _safe_name(event.bundle_id)
            bundle_dir.mkdir(parents=True, exist_ok=True)
            suffix = source.suffix or ".json"
            target = bundle_dir / (
                f"{_safe_name(event.entry_id)}__{event.sequence_sha256[:12]}{suffix}"
            )
            if not target.exists():
                shutil.copy2(source, target)
            if _sha256(target) != event.sequence_sha256:
                raise RuntimeError(
                    f"Copied sequence hash mismatch for bundle '{event.bundle_id}' entry '{event.entry_id}'"
                )
            artifact_path = str(target.relative_to(self.run_path))
            self._sequence_artifacts[key] = artifact_path
        record = {
            "point_id": event.point_id,
            "coords": to_jsonable(event.coords),
            "resource": event.resource,
            "bundle_id": event.bundle_id,
            "entry_id": event.entry_id,
            "requested_coordinates": to_jsonable(event.requested_coordinates),
            "entry_coordinates": to_jsonable(event.entry_coordinates),
            "manifest_path": event.manifest_path,
            "manifest_sha256": event.manifest_sha256,
            "source_path": event.sequence_file,
            "artifact_path": artifact_path,
            "sha256": event.sequence_sha256,
            "metadata": to_jsonable(event.metadata),
            "timestamp": event.timestamp,
        }
        self._sequence_selection_file.write(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self._sequence_selection_file.flush()
        self.metadata_writer.metadata["sequence_selection_count"] += 1
        self.metadata_writer.write()

    def _create_run_path(self, started_at: str) -> Path:
        dt = datetime.fromisoformat(started_at)
        day = dt.strftime("%Y-%m-%d")
        if self._explicit_run_id is not None:
            base_name = self._explicit_run_id
        else:
            base_name = f"{dt.strftime('%Y%m%d_%H%M%S')}_{self.experiment_name}"
        parent = self.root / day
        candidate = parent / base_name
        if not candidate.exists():
            return candidate
        index = 1
        while True:
            suffixed = parent / f"{base_name}_{index:02d}"
            if not suffixed.exists():
                return suffixed
            index += 1

    def _handle_data_point(self, event: DataPoint) -> None:
        assert self.dataset_writer is not None
        assert self.metadata_writer is not None

        payload = self.dataset_writer.append_data_point(event)
        overlap = set(payload["data"]) & self._derived_keys
        self._raw_keys.update(payload["data"])
        if self.advanced_writer is not None:
            self.advanced_writer.add_data_point(payload)
        specs = infer_data_specs(payload["data"])
        self.metadata_writer.add_data_specs(specs)
        self.metadata_writer.write()
        for key, spec in specs.items():
            self._safe_index(
                self.index.upsert_data_key,
                run_id=self.run_id,
                key=key,
                kind=spec.get("kind"),
                unit=spec.get("unit"),
                shape=spec.get("shape"),
                uri=f"{self.run_path.name}/data.jsonl",
            )
        if event.point_id and event.point_id in self._points:
            point = self._points[event.point_id]
            point.setdefault("data_keys", set()).update(payload["data"].keys())
        if overlap:
            raise RuntimeError(f"Raw data keys collide with previously stored derived keys: {sorted(overlap)}")

    def _handle_derived_data(self, event: DerivedData) -> None:
        assert self.dataset_writer is not None
        assert self.metadata_writer is not None
        collision = set(event.data) & self._raw_keys
        if collision:
            raise RuntimeError(f"Derived data key collision: {sorted(collision)}")
        payload = self.dataset_writer.append_derived_data(event)
        self._derived_keys.update(payload["data"])
        if self.advanced_writer is not None:
            self.advanced_writer.add_data_point(payload)
        specs = payload["data_specs"]
        self.metadata_writer.add_data_specs(specs)
        self.metadata_writer.write()
        for key, spec in specs.items():
            self._safe_index(self.index.upsert_data_key, run_id=self.run_id, key=key,
                             kind=spec.get("kind"), unit=spec.get("unit"), shape=spec.get("shape"),
                             uri=f"{self.run_path.name}/data.jsonl")
        if event.point_id and event.point_id in self._points:
            point = self._points[event.point_id]
            point.setdefault("data_keys", set()).update(payload["data"].keys())
            if point.get("status") != "running":
                self._write_point(point)

    def _handle_measurement_started(self, event: MeasurementStarted) -> None:
        assert self.metadata_writer is not None
        record = {
            "point_id": event.point_id,
            "status": "running",
            "coords": to_jsonable(event.coords),
            "data_keys": set(),
            "started_at": event.timestamp,
            "completed_at": None,
        }
        self._points[event.point_id] = record
        if self.advanced_writer is not None:
            self.advanced_writer.add_point_started(event.point_id, event.coords, event.timestamp)
        self.metadata_writer.metadata["point_count"] = len(self._points)
        self.metadata_writer.write()
        self._write_point(record)

    def _handle_measurement_completed(self, event: MeasurementCompleted) -> None:
        assert self.metadata_writer is not None
        record = self._points.get(
            event.point_id,
            {
                "point_id": event.point_id,
                "status": "running",
                "coords": to_jsonable(event.coords),
                "data_keys": set(),
                "started_at": None,
                "completed_at": None,
            },
        )
        record["status"] = event.status
        record["coords"] = to_jsonable(event.coords)
        record["completed_at"] = event.timestamp
        self._points[event.point_id] = record
        if self.advanced_writer is not None:
            self.advanced_writer.add_point_completed(event.point_id, event.status, event.coords, event.timestamp)
        if event.status == "ok":
            self.metadata_writer.metadata["completed_point_count"] += 1
        self.metadata_writer.write()
        self._write_point(record)

    def _write_point(self, record: dict[str, Any]) -> None:
        assert self.points_writer is not None
        point_record = dict(record)
        point_record["data_keys"] = sorted(point_record.get("data_keys", []))
        self.points_writer.append(point_record)
        self._safe_index(
            self.index.upsert_point,
            run_id=self.run_id,
            point_id=point_record["point_id"],
            status=point_record["status"],
            coords=point_record.get("coords", {}),
            started_at=point_record.get("started_at"),
            completed_at=point_record.get("completed_at"),
        )

    def _append_log(self, event: LogMessage) -> None:
        with (self.run_path / "logs.txt").open("a", encoding="utf-8") as file:
            file.write(f"{event.timestamp} [{event.level.upper()}] {event.message}\n")

    def _upsert_run(self) -> None:
        assert self.metadata_writer is not None
        metadata = self.metadata_writer.metadata
        self._safe_index(
            self.index.upsert_run,
            run_id=self.run_id,
            experiment_name=self.experiment_name,
            started_at=metadata["started_at"],
            ended_at=metadata["ended_at"],
            status=metadata["status"],
            run_path=self.run_path,
            metadata=metadata,
        )

    def _safe_index(self, func: Any, *args: Any, **kwargs: Any) -> None:
        try:
            func(*args, **kwargs)
        except Exception:
            return


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Sequence provenance source file not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
