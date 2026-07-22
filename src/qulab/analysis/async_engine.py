"""Bounded single-worker live compute with explicit backpressure."""

from __future__ import annotations

import queue
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Any, Mapping

from qulab.core import AnalysisStatus, DataPoint, DerivedData, Event, EventBus, MeasurementCompleted, MeasurementStarted

from .engine import LiveComputeEngine, LiveComputeError, _PointState, _equal
from .models import AnalysisExecutionPlan, ComputeModulePlan, json_safe
from .registry import AnalysisModuleRegistry


class AsyncComputeOverflow(LiveComputeError):
    pass


@dataclass(frozen=True)
class ComputeWorkItem:
    sequence_number: int
    point_id: str
    coords: Mapping[str, Any]
    data_snapshot: Mapping[str, Any]
    metadata: Mapping[str, Any]
    timestamp: str
    enqueued_monotonic: float


class AsyncLiveComputeEngine(LiveComputeEngine):
    """Aggregate raw events on the emitter thread and compute completed points on one daemon worker."""

    def __init__(self, plan: AnalysisExecutionPlan, registry: AnalysisModuleRegistry | None, event_bus: EventBus) -> None:
        super().__init__(plan, registry, event_bus)
        self._work: queue.Queue[ComputeWorkItem] = queue.Queue(maxsize=plan.live.queue_size)
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._accepting = True
        self._disabled = False
        self._sequence = 0
        self._worker_error: BaseException | None = None
        self._current_item: ComputeWorkItem | None = None
        self._allow_background_emits = True
        self._last_queue_status = 0.0
        self._engine_metrics: dict[str, Any] = {
            "capacity": plan.live.queue_size, "enqueued": 0, "completed": 0, "skipped": 0,
            "dropped": 0, "failed": 0, "max_queue_depth": 0, "last_queue_wait_s": None,
            "max_queue_wait_s": 0.0, "last_end_to_end_s": None, "max_end_to_end_s": 0.0,
            "worker_state": "created", "current_point": None, "last_point": None,
        }

    def setup(self, run_context: Mapping[str, Any]) -> None:
        super().setup(run_context)
        if self.plan.live.enabled and self._runtimes:
            self._engine_metrics["worker_state"] = "ready"
            self._worker = threading.Thread(target=self._worker_main, name="qulab-analysis", daemon=True)
            self._worker.start()

    def handle_event(self, event: Event) -> None:
        if self._worker_error is not None:
            error = self._worker_error; self._worker_error = None
            raise LiveComputeError("async_worker", getattr(event, "point_id", None), str(error)) from error
        if isinstance(event, (DerivedData, AnalysisStatus)) or not self.plan.live.enabled or self._disabled:
            return
        if isinstance(event, MeasurementStarted):
            self._started_points.add(event.point_id)
            self._points.setdefault(event.point_id, _PointState(event.point_id, deepcopy(event.coords), timestamp=event.timestamp))
        elif isinstance(event, DataPoint):
            self._aggregate(event)
        elif isinstance(event, MeasurementCompleted):
            state = self._points.pop(event.point_id, None)
            self._started_points.discard(event.point_id)
            if state is not None and event.status == "ok" and self._accepting:
                self._enqueue(state)

    def _aggregate(self, event: DataPoint) -> None:
        if not event.point_id: return
        state = self._points.setdefault(event.point_id, _PointState(event.point_id, deepcopy(event.coords), timestamp=event.timestamp))
        if state.coords != event.coords:
            self._point_failure(event.point_id, "coordinates changed while aggregating async point")
        for key, value in deepcopy(event.data).items():
            if key in state.data and not _equal(state.data[key], value):
                self._point_failure(event.point_id, f"raw key collision for '{key}'")
            state.data[key] = value; state.raw_keys.add(key)
        state.metadata.update(deepcopy(event.metadata)); state.timestamp = event.timestamp

    def _enqueue(self, state: _PointState) -> None:
        self._sequence += 1
        item = ComputeWorkItem(self._sequence, state.point_id, json_safe(state.coords), json_safe(state.data),
                               json_safe(state.metadata), state.timestamp, monotonic())
        try:
            self._work.put_nowait(item)
        except queue.Full:
            self._apply_backpressure(item)
            return
        self._engine_metrics["enqueued"] += 1
        self._engine_metrics["max_queue_depth"] = max(self._engine_metrics["max_queue_depth"], self._work.qsize())
        self._queue_status("queued", item.point_id)

    def _apply_backpressure(self, item: ComputeWorkItem) -> None:
        policy = self.plan.live.backpressure
        if policy == "skip_newest":
            self._drop(item, "queue full: skipped newest")
            return
        if policy in {"skip_oldest", "latest"}:
            removed: list[ComputeWorkItem] = []
            count = 1 if policy == "skip_oldest" else self._work.qsize()
            for _ in range(count):
                try: old = self._work.get_nowait()
                except queue.Empty: break
                self._work.task_done(); removed.append(old)
            for old in removed: self._drop(old, f"queue full: removed by {policy}")
            self._work.put_nowait(item); self._engine_metrics["enqueued"] += 1
            self._engine_metrics["max_queue_depth"] = max(self._engine_metrics["max_queue_depth"], self._work.qsize())
            return
        if policy == "disable_module":
            self._disabled = True; self._drop(item, "queue overflow disabled live analysis", state="warning")
            return
        self._engine_metrics["failed"] += 1
        self._queue_status("failed", item.point_id, "queue overflow requested run failure")
        raise AsyncComputeOverflow("async_queue", item.point_id, "bounded analysis queue is full")

    def _drop(self, item: ComputeWorkItem, message: str, state: str = "skipped") -> None:
        self._engine_metrics["dropped"] += 1; self._engine_metrics["skipped"] += 1
        self._queue_status(state, item.point_id, message)

    def _worker_main(self) -> None:
        self._engine_metrics["worker_state"] = "running"
        while not self._stop.is_set() or not self._work.empty():
            try: item = self._work.get(timeout=.05)
            except queue.Empty: continue
            self._current_item = item; self._engine_metrics["current_point"] = item.point_id
            wait = monotonic() - item.enqueued_monotonic
            self._engine_metrics["last_queue_wait_s"] = wait
            self._engine_metrics["max_queue_wait_s"] = max(self._engine_metrics["max_queue_wait_s"], wait)
            try:
                state = _PointState(item.point_id, deepcopy(dict(item.coords)), deepcopy(dict(item.data_snapshot)),
                                    set(item.data_snapshot), set(), deepcopy(dict(item.metadata)), item.timestamp)
                self._run_ready(state)
                self._finish_missing(state)
                self._engine_metrics["completed"] += 1
            except BaseException as exc:
                self._engine_metrics["failed"] += 1; self._worker_error = exc
                self._queue_status("failed", item.point_id, str(exc), error=exc)
                self._stop.set()
            finally:
                elapsed = monotonic() - item.enqueued_monotonic
                self._engine_metrics["last_end_to_end_s"] = elapsed
                self._engine_metrics["max_end_to_end_s"] = max(self._engine_metrics["max_end_to_end_s"], elapsed)
                self._engine_metrics["last_point"] = item.point_id; self._engine_metrics["current_point"] = None
                self._current_item = None; self._work.task_done()
        self._engine_metrics["worker_state"] = "stopped"

    def _finish_missing(self, state: _PointState) -> None:
        for module in self.plan.modules:
            if module.instance_name not in self._runtimes or module.instance_name in state.executed: continue
            missing = [key for key in module.inputs if key not in state.data]
            state.executed.add(module.instance_name); self._metrics[module.instance_name]["skipped"] += 1
            if module.fail_policy == "fail": raise LiveComputeError(module.instance_name, state.point_id, f"missing inputs: {missing}")
            self._emit_status(module, "warning" if module.fail_policy == "warn" else "skipped",
                              point_id=state.point_id, message=f"missing inputs: {', '.join(missing)}")

    def close(self) -> None:
        if self._closed: return
        self._accepting = False
        deadline = monotonic() + self.plan.live.drain_timeout_s
        if not self.plan.live.drain_on_close: self._cancel_pending("drain disabled")
        else:
            self._engine_metrics["worker_state"] = "draining"
            while self._work.unfinished_tasks and monotonic() < deadline:
                time.sleep(.005)
            if self._work.unfinished_tasks: self._cancel_pending("drain timeout")
        self._stop.set()
        worker = self._worker
        if worker is not None:
            worker.join(max(0.0, deadline - monotonic()) if self.plan.live.drain_on_close else .1)
        alive = bool(worker and worker.is_alive())
        if alive:
            self._allow_result_events = False; self._allow_background_emits = False
            self._engine_metrics["worker_state"] = "hung"
        else:
            super().close()
        if self._worker_error is not None:
            error = self._worker_error; self._worker_error = None
            raise LiveComputeError("async_worker", self._engine_metrics.get("last_point"), str(error)) from error

    def _cancel_pending(self, message: str) -> None:
        while True:
            try: item = self._work.get_nowait()
            except queue.Empty: break
            self._work.task_done(); self._drop(item, message)

    def _queue_status(self, state: str, point_id: str | None, message: str | None = None,
                      error: BaseException | None = None) -> None:
        now = monotonic()
        if state == "queued" and self.plan.live.status_interval_s > 0 and now - self._last_queue_status < self.plan.live.status_interval_s:
            return
        self._last_queue_status = now
        for module in self.plan.modules:
            if module.instance_name in self._runtimes:
                self._emit_status(module, state, point_id=point_id, message=message, error=error if isinstance(error, Exception) else None)

    def _emit_status(self, module: ComputeModulePlan, state: str, *, point_id: str | None = None,
                     message: str | None = None, latency: float | None = None, error: Exception | None = None) -> None:
        if not self._allow_background_emits: return
        self.event_bus.emit(AnalysisStatus(module=module.instance_name, state=state, point_id=point_id,
            message=message, latency_s=latency, queue_depth=self._work.qsize(),
            error_type=type(error).__name__ if error else None, fail_policy=module.fail_policy,
            metadata={"queue_capacity": self.plan.live.queue_size, "dropped": self._engine_metrics["dropped"],
                      "skipped": self._engine_metrics["skipped"], "lagging": self._work.full(),
                      "queue_wait_s": self._engine_metrics["last_queue_wait_s"],
                      "worker_state": self._engine_metrics["worker_state"]}))

    def summary(self) -> dict[str, Any]:
        result = super().summary(); result["engine_metrics"] = deepcopy(self._engine_metrics)
        result["queue_depth"] = self._work.qsize(); return result


def create_live_compute_engine(plan: AnalysisExecutionPlan, registry: AnalysisModuleRegistry | None, bus: EventBus):
    return AsyncLiveComputeEngine(plan, registry, bus) if plan.live.execution == "async" else LiveComputeEngine(plan, registry, bus)
