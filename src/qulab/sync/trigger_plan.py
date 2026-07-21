"""Sync plan data model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TriggerEdge:
    source: str
    target: str
    edge: str = "rising"
    purpose: str | None = None


@dataclass(frozen=True)
class ExecutionOrder:
    configure: list[str] = field(default_factory=list)
    arm: list[str] = field(default_factory=list)
    start: list[str] = field(default_factory=list)
    read: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncPlan:
    master: str | None = None
    triggers: list[TriggerEdge] = field(default_factory=list)
    order: ExecutionOrder | None = None
