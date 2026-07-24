"""Structured executor events and an in-memory event bus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from collections import deque
from threading import RLock
from typing import Any, Callable


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    type: str = field(init=False, default="Event")
    timestamp: str = field(default_factory=_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunStarted(Event):
    type: str = field(init=False, default="RunStarted")
    run_id: str = ""
    procedure_name: str = ""


@dataclass
class RunCompleted(Event):
    type: str = field(init=False, default="RunCompleted")
    run_id: str = ""
    status: str = "completed"


@dataclass
class StepStarted(Event):
    type: str = field(init=False, default="StepStarted")
    step_id: str = ""
    step_name: str = ""
    step_kind: str = ""
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepCompleted(Event):
    type: str = field(init=False, default="StepCompleted")
    step_id: str = ""
    step_name: str = ""
    step_kind: str = ""
    status: str = "ok"
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterChanged(Event):
    type: str = field(init=False, default="ParameterChanged")
    name: str = ""
    value: Any = None
    coords: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeasurementStarted(Event):
    type: str = field(init=False, default="MeasurementStarted")
    point_id: str = ""
    coords: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeasurementCompleted(Event):
    type: str = field(init=False, default="MeasurementCompleted")
    point_id: str = ""
    status: str = "ok"
    coords: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataPoint(Event):
    type: str = field(init=False, default="DataPoint")
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DerivedData(Event):
    type: str = field(init=False, default="DerivedData")
    point_id: str = ""
    coords: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    source_module: str = ""
    module_version: str = ""
    input_keys: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    units: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    save: bool = True
    show: bool = False
    run_mode: str = "live"
    latency_s: float | None = None


@dataclass
class AnalysisStatus(Event):
    type: str = field(init=False, default="AnalysisStatus")
    module: str = ""
    state: str = "idle"
    point_id: str | None = None
    message: str | None = None
    latency_s: float | None = None
    queue_depth: int = 0
    error_type: str | None = None
    fail_policy: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SequenceSelected(Event):
    type: str = field(init=False, default="SequenceSelected")
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    resource: str = ""
    bundle_id: str = ""
    entry_id: str = ""
    requested_coordinates: dict[str, Any] = field(default_factory=dict)
    entry_coordinates: dict[str, Any] = field(default_factory=dict)
    manifest_path: str = ""
    manifest_sha256: str = ""
    sequence_file: str = ""
    sequence_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRaised(Event):
    type: str = field(init=False, default="ErrorRaised")
    error_type: str = ""
    message: str = ""
    step_id: str | None = None


@dataclass
class InstrumentSnapshot(Event):
    type: str = field(init=False, default="InstrumentSnapshot")
    resource: str = ""
    action: str = ""
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogMessage(Event):
    type: str = field(init=False, default="LogMessage")
    level: str = "info"
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Synchronous in-memory event bus for tests and dry-run execution."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self._subscribers: list[Callable[[Event], None]] = []
        self._queue: deque[Event] = deque()
        self._dispatching = False
        self._lock = RLock()

    def emit(self, event: Event) -> None:
        with self._lock:
            self.events.append(event)
            self._queue.append(event)
            if self._dispatching:
                return
            self._dispatching = True
            try:
                while self._queue:
                    current = self._queue.popleft()
                    for callback in list(self._subscribers):
                        callback(current)
            except BaseException:
                self._queue.clear()
                raise
            finally:
                self._dispatching = False

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)
