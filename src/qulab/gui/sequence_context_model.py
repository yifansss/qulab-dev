"""Read-only current sequence selection context."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from qulab.core import ErrorRaised, Event, SequenceSelected


@dataclass(frozen=True)
class SequenceContext:
    point_id: str | None = None
    plan_id: str | None = None
    mode: str = "Single File"
    provider: str | None = None
    family: str | None = None
    template: str | None = None
    bundle_id: str | None = None
    entry_id: str | None = None
    requested_coordinates: dict[str, Any] | None = None
    resolved_coordinates: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    sequence_sha256: str | None = None
    status: str = "waiting"
    last_error: str | None = None
    metadata: dict[str, Any] | None = None


class SequenceContextModel:
    def __init__(self, single_file: dict[str, Any] | None = None) -> None:
        self._by_point: dict[str, SequenceContext] = {}
        self._current = SequenceContext(mode="Single File", status="snapshot" if single_file else "waiting",
                                        metadata=deepcopy(single_file or {}))

    def handle_event(self, event: Event) -> None:
        if isinstance(event, SequenceSelected):
            meta = deepcopy(event.metadata)
            mode = meta.get("mode") or ("Curated Family" if meta.get("family") else
                    "Generic Template Sweep" if meta.get("template") else "Existing Bundle")
            context = SequenceContext(event.point_id, meta.get("plan_id"), mode, meta.get("provider"), meta.get("family"),
                meta.get("template"), event.bundle_id, event.entry_id, deepcopy(event.requested_coordinates),
                deepcopy(event.entry_coordinates), event.manifest_sha256, event.sequence_sha256, "selected", None, meta)
            if event.point_id:
                self._by_point[event.point_id] = context
            self._current = context
        elif isinstance(event, ErrorRaised) and ("sequence" in event.error_type.lower() or "sequence" in event.message.lower()):
            self._current = SequenceContext(point_id=self._current.point_id, mode=self._current.mode,
                                            status="error", last_error=event.message)

    def current(self) -> SequenceContext:
        return self._current

    def for_point(self, point_id: str) -> SequenceContext | None:
        return self._by_point.get(point_id)
