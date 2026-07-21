"""Procedure step model for hardware-free experiment orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .parameter import ScanValues


def _step_id(name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    return normalized or "step"


@dataclass
class Step:
    name: str
    id: str | None = None
    enabled: bool = True
    kind: str = field(init=False, default="step")

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = _step_id(self.name)


@dataclass
class ActionStep(Step):
    action: Callable[..., Any] | str | None = None
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    save_as: str | None = None
    kind: str = field(init=False, default="action")


@dataclass
class ScanStep(Step):
    values: ScanValues = field(default_factory=lambda: ScanValues.explicit(()))
    body: list[Step] = field(default_factory=list)
    kind: str = field(init=False, default="scan")


@dataclass
class AverageStep(Step):
    count: int = 1
    body: list[Step] = field(default_factory=list)
    kind: str = field(init=False, default="average")


@dataclass
class MeasurementStep(Step):
    body: list[Step] = field(default_factory=list)
    kind: str = field(init=False, default="measurement")


@dataclass
class RunStep(Step):
    body: list[Step] = field(default_factory=list)
    timeout_s: float | None = None
    kind: str = field(init=False, default="run")


@dataclass
class WaitStep(Step):
    duration_s: float = 0.0
    reason: str | None = None
    kind: str = field(init=False, default="wait")


@dataclass
class CleanupStep(Step):
    body: list[Step] = field(default_factory=list)
    kind: str = field(init=False, default="cleanup")


@dataclass
class Procedure:
    name: str
    body: list[Step] = field(default_factory=list)
    setup: list[Step] = field(default_factory=list)
    cleanup: list[Step] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
