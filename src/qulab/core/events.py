"""Structured executor events and an in-memory event bus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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

    def emit(self, event: Event) -> None:
        self.events.append(event)
        for callback in list(self._subscribers):
            callback(event)

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        self._subscribers.append(callback)
