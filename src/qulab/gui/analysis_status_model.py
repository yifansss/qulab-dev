"""Headless module status reducer."""

from __future__ import annotations

from dataclasses import dataclass, replace

from qulab.analysis import AnalysisExecutionPlan
from qulab.core import AnalysisStatus, Event


@dataclass(frozen=True)
class ModuleStatus:
    module: str
    enabled: bool
    state: str = "idle"
    last_point: str | None = None
    last_success_time: str | None = None
    last_latency_s: float | None = None
    message: str | None = None
    error_type: str | None = None
    fail_policy: str = "warn"
    queue_depth: int = 0
    queue_capacity: int = 0
    dropped: int = 0
    skipped: int = 0
    queue_wait_s: float | None = None
    worker_state: str = "sync"
    lagging: bool = False
    outputs_summary: str = ""


class AnalysisStatusModel:
    def __init__(self, plan: AnalysisExecutionPlan | None = None) -> None:
        self._statuses: dict[str, ModuleStatus] = {}
        if plan:
            for module in plan.modules:
                suffix = "saved" if module.save else "live-only"
                self._statuses[module.instance_name] = ModuleStatus(module.instance_name, module.enabled,
                    state="idle" if module.enabled else "disabled", fail_policy=module.fail_policy,
                    outputs_summary=f"{', '.join(module.effective_outputs)} ({suffix})")

    def handle_event(self, event: Event) -> None:
        if not isinstance(event, AnalysisStatus):
            return
        current = self._statuses.get(event.module, ModuleStatus(event.module, True, fail_policy=event.fail_policy or "warn"))
        self._statuses[event.module] = replace(current, state=event.state, last_point=event.point_id or current.last_point,
            last_success_time=event.timestamp if event.state == "success" else current.last_success_time,
            last_latency_s=event.latency_s if event.latency_s is not None else current.last_latency_s,
            message=event.message, error_type=event.error_type, queue_depth=event.queue_depth,
            queue_capacity=int(event.metadata.get("queue_capacity", current.queue_capacity)),
            dropped=int(event.metadata.get("dropped", current.dropped)),
            skipped=int(event.metadata.get("skipped", current.skipped)),
            queue_wait_s=event.metadata.get("queue_wait_s", current.queue_wait_s),
            worker_state=str(event.metadata.get("worker_state", current.worker_state)),
            lagging=bool(event.metadata.get("lagging", False)))

    def list(self) -> tuple[ModuleStatus, ...]:
        return tuple(self._statuses.values())
