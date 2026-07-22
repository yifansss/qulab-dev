"""Read-only historical run reconstruction and deterministic event replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

import yaml

from qulab.core import (
    AnalysisStatus, DataPoint, DerivedData, ErrorRaised, Event, LogMessage,
    MeasurementCompleted, MeasurementStarted, ParameterChanged, RunCompleted,
    RunStarted, SequenceSelected, StepCompleted, StepStarted,
)

if TYPE_CHECKING:
    from qulab.config import ConfigLoadResult


class Fidelity(str, Enum):
    RECORDED = "recorded"
    RECONSTRUCTED = "reconstructed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class HistoricalSectionStatus:
    section: str
    fidelity: Fidelity
    message: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalEventRecord:
    index: int
    event: Event | None
    raw: dict[str, Any] | None
    error: str | None = None
    line: int | None = None


@dataclass
class HistoricalReplay:
    workspace: "HistoricalRunWorkspace"
    consumers: tuple[Callable[[Event], None], ...] = ()
    index: int = 0
    playing: bool = False
    speed: float | str = 1.0
    final_event: Event | None = None

    def reset(self) -> None:
        self.index = 0
        self.playing = False
        self.final_event = None

    def seek(self, event_index: int) -> None:
        if event_index < 0:
            raise ValueError("event index must be non-negative")
        self.reset()
        while self.index < event_index and self.step() is not None:
            pass

    def step(self) -> Event | None:
        for record in self.workspace.iter_event_records(start=self.index):
            self.index = record.index + 1
            if record.event is None:
                continue
            self.final_event = record.event
            for consumer in self.consumers:
                consumer(record.event)
            return record.event
        self.playing = False
        return None

    def play(self, speed: float | str = 1.0, *, max_events: int | None = None) -> int:
        if speed != "max" and float(speed) not in {0.25, 1.0, 4.0}:
            raise ValueError("speed must be 0.25, 1, 4, or 'max'")
        self.speed = speed
        self.playing = True
        consumed = 0
        while self.playing and (max_events is None or consumed < max_events):
            if self.step() is None:
                break
            consumed += 1
        return consumed

    def pause(self) -> None:
        self.playing = False


@dataclass
class HistoricalRunWorkspace:
    run_path: Path
    metadata: dict[str, Any]
    config: dict[str, Any] | None
    resolved_config: dict[str, Any] | None
    sections: tuple[HistoricalSectionStatus, ...]
    diagnostics: list[str] = field(default_factory=list)

    @classmethod
    def open(cls, run_path: str | Path) -> "HistoricalRunWorkspace":
        root = Path(run_path).resolve()
        if not root.is_dir():
            raise ValueError(f"Historical run is not a directory: {root}")
        metadata = _read_json(root / "metadata.json")
        if not isinstance(metadata, dict) or not metadata.get("run_id"):
            raise ValueError(f"Directory is not a Qulab run: {root}")
        config = _read_yaml_mapping(root / "config.yaml")
        resolved = _read_yaml_mapping(root / "resolved_config.yaml")
        workspace = cls(root, metadata, config, resolved, tuple(_section_statuses(root, metadata, config, resolved)))
        workspace._validate_artifact_paths()
        return workspace

    @property
    def run_id(self) -> str:
        return str(self.metadata.get("run_id"))

    def status(self, section: str) -> HistoricalSectionStatus:
        return next(item for item in self.sections if item.section == section)

    def iter_event_records(self, *, start: int = 0) -> Iterator[HistoricalEventRecord]:
        path = self.run_path / "events.jsonl"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < start:
                    continue
                try:
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError("event must be a JSON object")
                    yield HistoricalEventRecord(index, _event_from_dict(payload), payload, line=index + 1)
                except Exception as exc:
                    yield HistoricalEventRecord(index, None, None, str(exc), index + 1)

    def iter_events(self, *, start: int = 0) -> Iterator[Event]:
        for record in self.iter_event_records(start=start):
            if record.event is not None:
                yield record.event

    def timeline_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.iter_event_records():
            name = record.event.type if record.event is not None else "malformed"
            counts[name] = counts.get(name, 0) + 1
        return counts

    def replay(self, *consumers: Callable[[Event], None]) -> HistoricalReplay:
        return HistoricalReplay(self, tuple(consumers))

    def clone_as_draft(self, destination: str | Path, *, use_resolved: bool = False) -> ConfigLoadResult:
        from qulab.config import validate_config_candidate

        source = self.resolved_config if use_resolved else self.config
        if source is None:
            raise ValueError("Selected historical configuration snapshot is unavailable")
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(yaml.safe_dump(_safe_clone(source, self.run_id), sort_keys=False), encoding="utf-8")
        return validate_config_candidate(destination_path)

    def resolve_artifact(self, relative_path: str) -> Path:
        candidate = (self.run_path / relative_path).resolve()
        if candidate != self.run_path and self.run_path not in candidate.parents:
            raise ValueError(f"Historical artifact escapes run directory: {relative_path}")
        return candidate

    def _validate_artifact_paths(self) -> None:
        for section in ("sequence_bundles", "sequence_generation", "sequence_snapshots"):
            rows = self.metadata.get(section, [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in ("artifact_path", "manifest_artifact"):
                    value = row.get(key)
                    if isinstance(value, str) and not Path(value).is_absolute():
                        self.resolve_artifact(value)


_EVENT_TYPES = {item.__name__: item for item in (
    Event, RunStarted, RunCompleted, StepStarted, StepCompleted, ParameterChanged,
    MeasurementStarted, MeasurementCompleted, DataPoint, DerivedData, AnalysisStatus,
    SequenceSelected, ErrorRaised, LogMessage,
)}


def _event_from_dict(payload: dict[str, Any]) -> Event:
    cls = _EVENT_TYPES.get(str(payload.get("type")))
    if cls is None:
        raise ValueError(f"unsupported event type: {payload.get('type')!r}")
    allowed = {item.name for item in fields(cls) if item.init}
    return cls(**{key: value for key, value in payload.items() if key in allowed})


def _section_statuses(root: Path, metadata: dict[str, Any], config: dict[str, Any] | None, resolved: dict[str, Any] | None) -> list[HistoricalSectionStatus]:
    statuses = [
        _file_status("config", root / "config.yaml", config),
        _file_status("resolved_config", root / "resolved_config.yaml", resolved),
        HistoricalSectionStatus("resources", Fidelity.RECORDED if metadata.get("resources") else Fidelity.UNAVAILABLE,
                                "Recorded resource snapshot." if metadata.get("resources") else "No actual resource snapshot was recorded."),
        HistoricalSectionStatus("sync", Fidelity.RECORDED if metadata.get("sync") else Fidelity.RECONSTRUCTED if config and config.get("sync") else Fidelity.UNAVAILABLE,
                                "Sync state is recorded or reconstructable from configuration." if metadata.get("sync") or (config and config.get("sync")) else "No sync information is available."),
        HistoricalSectionStatus("sequence", *_sequence_fidelity(root, metadata)),
        HistoricalSectionStatus("analysis", Fidelity.RECORDED if metadata.get("analysis_modules") else Fidelity.UNAVAILABLE,
                                "Analysis declarations are recorded." if metadata.get("analysis_modules") else "No analysis declarations were recorded."),
    ]
    for section, filename in (("events", "events.jsonl"), ("points", "points.jsonl"), ("data", "data.jsonl"), ("logs", "logs.txt")):
        path = root / filename
        statuses.append(HistoricalSectionStatus(section, Fidelity.RECORDED if path.exists() else Fidelity.UNAVAILABLE,
                                                f"Recorded in {filename}." if path.exists() else f"{filename} is unavailable.",
                                                (filename,) if path.exists() else ()))
    return statuses


def _file_status(section: str, path: Path, value: Any) -> HistoricalSectionStatus:
    if not path.exists():
        return HistoricalSectionStatus(section, Fidelity.UNAVAILABLE, f"{path.name} is unavailable.")
    if value is None:
        return HistoricalSectionStatus(section, Fidelity.PARTIAL, f"{path.name} could not be interpreted.", (path.name,))
    return HistoricalSectionStatus(section, Fidelity.RECORDED, f"Recorded in {path.name}.", (path.name,))


def _sequence_fidelity(root: Path, metadata: dict[str, Any]) -> tuple[Fidelity, str, tuple[str, ...]]:
    rows = metadata.get("sequence_bundles", [])
    if not rows and not metadata.get("sequence_generation") and not metadata.get("sequence_snapshots"):
        return Fidelity.UNAVAILABLE, "No sequence provenance was recorded.", ()
    artifacts: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        relative, expected = row.get("manifest_artifact"), row.get("manifest_sha256")
        if isinstance(relative, str):
            path = (root / relative).resolve()
            artifacts.append(relative)
            if not path.exists():
                return Fidelity.PARTIAL, f"Sequence artifact is missing: {relative}", tuple(artifacts)
            if expected and _sha256(path) != expected:
                return Fidelity.MISMATCH, f"Sequence artifact hash mismatch: {relative}", tuple(artifacts)
    return Fidelity.RECORDED, "Recorded sequence provenance and available artifacts.", tuple(artifacts)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_yaml_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def _safe_clone(source: dict[str, Any], run_id: str) -> dict[str, Any]:
    clone = json.loads(json.dumps(source))
    clone["name"] = f"{clone.get('name', 'experiment')}_clone"
    clone.setdefault("provenance", {})["source_run_id"] = run_id
    clone.setdefault("safety", {}).update({"allow_output": False, "physical_verification": False})
    for value in _walk_mappings(clone):
        for key in ("allow_output", "output_enabled", "physical_verification", "verified"):
            if key in value:
                value[key] = False
    return clone


def _walk_mappings(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_mappings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_mappings(item)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
