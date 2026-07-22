"""Synchronous per-point live compute engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Mapping

from qulab.core import AnalysisStatus, DataPoint, DerivedData, Event, EventBus, MeasurementCompleted, MeasurementStarted

from .errors import AnalysisError
from .models import AnalysisExecutionPlan, ComputeModulePlan, ComputePoint, ComputeResult, json_safe
from .registry import AnalysisModuleRegistry, DEFAULT_ANALYSIS_REGISTRY


class LiveComputeError(RuntimeError):
    def __init__(self, module: str, point_id: str | None, message: str) -> None:
        super().__init__(f"analysis module '{module}' failed: {message}")
        self.module = module
        self.point_id = point_id


@dataclass
class _PointState:
    point_id: str
    coords: dict[str, Any]
    data: dict[str, Any] = field(default_factory=dict)
    raw_keys: set[str] = field(default_factory=set)
    executed: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class LiveComputeEngine:
    def __init__(self, plan: AnalysisExecutionPlan, registry: AnalysisModuleRegistry | None, event_bus: EventBus) -> None:
        self.plan = plan
        self.registry = registry or DEFAULT_ANALYSIS_REGISTRY
        self.event_bus = event_bus
        self._runtimes: dict[str, Any] = {}
        self._setup_order: list[str] = []
        self._points: dict[str, _PointState] = {}
        self._closed = False
        self._metrics: dict[str, dict[str, Any]] = {}
        self._started_points: set[str] = set()
        self._allow_result_events = True

    @property
    def active_point_count(self) -> int:
        return len(self._points)

    def setup(self, run_context: Mapping[str, Any]) -> None:
        context = json_safe(run_context)
        if not self.plan.live.enabled:
            return
        for module in self.plan.modules:
            if not module.enabled or not module.run_live:
                continue
            self._emit_status(module, "setup")
            try:
                runtime = self.registry.instantiate(module)
                runtime.setup(deepcopy(dict(module.args)), deepcopy(context))
            except Exception as exc:
                self._handle_failure(module, None, exc, phase="setup")
                continue
            self._runtimes[module.instance_name] = runtime
            self._setup_order.append(module.instance_name)
            self._metrics[module.instance_name] = {"processed": 0, "failed": 0, "skipped": 0, "last_latency_s": None}
            self._emit_status(module, "ready")

    def handle_event(self, event: Event) -> None:
        if isinstance(event, (DerivedData, AnalysisStatus)) or not self.plan.live.enabled:
            return
        if isinstance(event, MeasurementStarted):
            self._started_points.add(event.point_id)
            self._points.setdefault(event.point_id, _PointState(event.point_id, deepcopy(event.coords), timestamp=event.timestamp))
        elif isinstance(event, DataPoint):
            self._handle_data_point(event)
        elif isinstance(event, MeasurementCompleted):
            self._handle_completed(event)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for name in reversed(self._setup_order):
            module = self._plan(name)
            try:
                self._runtimes[name].close()
            except Exception as exc:
                self._emit_status(module, "warning", message=f"close failed: {exc}", error=exc)
            else:
                self._emit_status(module, "closed")
        self._runtimes.clear()
        self._points.clear()

    def summary(self) -> dict[str, Any]:
        return {"plan": self.plan.to_dict(), "metrics": deepcopy(self._metrics), "active_points": len(self._points)}

    def _handle_data_point(self, event: DataPoint) -> None:
        if not event.point_id:
            return
        state = self._points.setdefault(event.point_id, _PointState(event.point_id, deepcopy(event.coords), timestamp=event.timestamp))
        if state.coords != event.coords:
            self._point_failure(event.point_id, f"coordinates changed from {state.coords!r} to {event.coords!r}")
            return
        for key, value in deepcopy(event.data).items():
            if key in state.data and not _equal(state.data[key], value):
                self._point_failure(event.point_id, f"raw key collision for '{key}'")
                return
            state.data[key] = value
            state.raw_keys.add(key)
        state.metadata.update(deepcopy(event.metadata))
        state.timestamp = event.timestamp
        self._run_ready(state)

    def _run_ready(self, state: _PointState) -> None:
        progress = True
        while progress:
            progress = False
            for module in self.plan.modules:
                name = module.instance_name
                if name not in self._runtimes or name in state.executed:
                    continue
                if not all(key in state.data for key in module.inputs):
                    continue
                state.executed.add(name)
                progress = True
                self._execute(module, state)

    def _execute(self, module: ComputeModulePlan, state: _PointState) -> None:
        self._emit_status(module, "running", point_id=state.point_id)
        point = ComputePoint(state.point_id, deepcopy(state.coords),
                             {key: deepcopy(state.data[key]) for key in module.inputs},
                             deepcopy(state.metadata), state.timestamp)
        started = monotonic()
        try:
            raw_result = self._runtimes[module.instance_name].process_point(point)
            latency = monotonic() - started
            result = _normalize_result(raw_result)
            if result is None or not result.data:
                self._metrics[module.instance_name]["skipped"] += 1
                self._emit_status(module, "skipped", point_id=state.point_id, latency=latency, message="no output")
                return
            data, units = self._validate_result(module, result, state)
            state.data.update(deepcopy(data))
            metrics = self._metrics[module.instance_name]
            metrics["processed"] += 1
            metrics["last_latency_s"] = latency
            if self._allow_result_events and (self.plan.live.emit_events or module.save or module.show):
                self.event_bus.emit(DerivedData(
                    point_id=state.point_id, coords=deepcopy(state.coords), data=deepcopy(data),
                    source_module=module.instance_name, module_version=module.source_identity.version,
                    input_keys=list(module.inputs), output_keys=list(data), units=units,
                    metadata=json_safe(result.metadata), quality=json_safe(result.quality), save=module.save,
                    show=module.show, latency_s=latency,
                ))
            self._emit_status(module, "success", point_id=state.point_id, latency=latency)
        except Exception as exc:
            self._handle_failure(module, state.point_id, exc, phase="process")

    def _validate_result(self, module: ComputeModulePlan, result: ComputeResult, state: _PointState):
        declared = set(module.declared_outputs)
        effective = set(module.effective_outputs)
        returned = set(result.data)
        if returned <= declared:
            mapped = {effective_key: result.data[declared_key]
                      for declared_key, effective_key in zip(module.declared_outputs, module.effective_outputs)
                      if declared_key in result.data}
            unit_map = {effective_key: result.units[declared_key]
                        for declared_key, effective_key in zip(module.declared_outputs, module.effective_outputs)
                        if declared_key in result.units}
        elif returned <= effective:
            mapped = dict(result.data)
            unit_map = dict(result.units)
        else:
            extra = sorted(returned - declared - effective)
            raise AnalysisError("analysis_outputs_invalid", f"undeclared outputs: {extra}")
        if not set(result.units) <= returned:
            raise AnalysisError("analysis_outputs_invalid", "units keys must be returned output keys")
        collisions = set(mapped) & set(state.data)
        if collisions:
            raise AnalysisError("analysis_output_collision", f"output collision: {sorted(collisions)}")
        return json_safe(mapped), json_safe(unit_map)

    def _handle_completed(self, event: MeasurementCompleted) -> None:
        state = self._points.get(event.point_id)
        if state is None:
            return
        self._run_ready(state)
        for module in self.plan.modules:
            if module.instance_name not in self._runtimes or module.instance_name in state.executed:
                continue
            missing = [key for key in module.inputs if key not in state.data]
            state.executed.add(module.instance_name)
            message = f"missing inputs: {', '.join(missing)}"
            if module.fail_policy == "fail" and event.status == "ok":
                self._points.pop(event.point_id, None)
                raise LiveComputeError(module.instance_name, event.point_id, message)
            status = "warning" if module.fail_policy == "warn" else "skipped"
            self._metrics[module.instance_name]["skipped"] += 1
            self._emit_status(module, status, point_id=event.point_id, message=message)
        self._points.pop(event.point_id, None)
        self._started_points.discard(event.point_id)

    def _handle_failure(self, module: ComputeModulePlan, point_id: str | None, exc: Exception, *, phase: str) -> None:
        if module.instance_name in self._metrics:
            self._metrics[module.instance_name]["failed"] += 1
        state = "failed" if module.fail_policy == "fail" else ("warning" if module.fail_policy == "warn" else "skipped")
        self._emit_status(module, state, point_id=point_id, message=f"{phase}: {exc}", error=exc)
        if module.fail_policy == "fail":
            raise LiveComputeError(module.instance_name, point_id, str(exc)) from exc

    def _point_failure(self, point_id: str, message: str) -> None:
        self._points.pop(point_id, None)
        raise LiveComputeError("engine", point_id, message)

    def _emit_status(self, module: ComputeModulePlan, state: str, *, point_id: str | None = None,
                     message: str | None = None, latency: float | None = None, error: Exception | None = None) -> None:
        self.event_bus.emit(AnalysisStatus(module=module.instance_name, state=state, point_id=point_id,
                                          message=message, latency_s=latency,
                                          error_type=type(error).__name__ if error else None,
                                          fail_policy=module.fail_policy))

    def _plan(self, name: str) -> ComputeModulePlan:
        return next(module for module in self.plan.modules if module.instance_name == name)


def _normalize_result(value: Any) -> ComputeResult | None:
    if value is None:
        return None
    if isinstance(value, ComputeResult):
        return ComputeResult(json_safe(value.data), json_safe(value.units), json_safe(value.metadata), json_safe(value.quality))
    if isinstance(value, Mapping):
        if "data" in value and isinstance(value["data"], Mapping):
            return ComputeResult(json_safe(value["data"]), json_safe(value.get("units", {})),
                                 json_safe(value.get("metadata", {})), json_safe(value.get("quality", {})))
        return ComputeResult(json_safe(value))
    raise AnalysisError("analysis_contract_invalid", f"process_point returned {type(value).__name__}")


def _equal(left: Any, right: Any) -> bool:
    try:
        result = left == right
        return bool(result) if isinstance(result, bool) else bool(result.all())
    except Exception:
        return False
