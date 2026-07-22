import threading

from qulab.analysis import (AnalysisExecutionPlan, AnalysisLiveConfig, AnalysisModuleRegistry, AnalysisSourceIdentity,
                            AsyncLiveComputeEngine, ComputeModulePlan)
from qulab.core import DataPoint, DerivedData, EventBus, MeasurementCompleted, MeasurementStarted


class GateModule:
    name = "gate"; version = "1"; input_keys = ("x",); output_keys = ("y",)
    started = threading.Event(); release = threading.Event(); order = []
    def setup(self, config, run_context): pass
    def process_point(self, point):
        type(self).started.set(); type(self).release.wait(2); type(self).order.append(point.point_id)
        return {"y": point.data["x"] * 2}
    def close(self): pass


def make_engine(policy="skip_newest", size=1, drain=True, timeout=2):
    live = AnalysisLiveConfig(enabled=True, execution="async", queue_size=size, backpressure=policy,
                              drain_on_close=drain, drain_timeout_s=timeout)
    module = ComputeModulePlan("gate", "fake", "GateModule", "class", True, True, False, False, True, "warn",
        ("x",), ("y",), ("y",), {}, AnalysisSourceIdentity("fake", None, None, "1"))
    plan = AnalysisExecutionPlan(live, (module,), ("x",), ("y",))
    registry = AnalysisModuleRegistry(); registry.register("fake:GateModule", GateModule)
    bus = EventBus(); engine = AsyncLiveComputeEngine(plan, registry, bus); engine.setup({}); bus.subscribe(engine.handle_event)
    return engine, bus


def point(bus, number):
    pid = f"p{number}"; bus.emit(MeasurementStarted(point_id=pid, coords={"i": number}))
    bus.emit(DataPoint(point_id=pid, coords={"i": number}, data={"x": number}))
    bus.emit(MeasurementCompleted(point_id=pid, coords={"i": number}))


def test_async_raw_emit_does_not_wait_for_slow_compute_and_drains():
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine()
    point(bus, 1)
    assert GateModule.started.wait(1)
    # The completed raw point returned while process_point remains gated.
    assert not [event for event in bus.events if isinstance(event, DerivedData)]
    GateModule.release.set(); engine.close()
    assert GateModule.order == ["p1"]
    assert next(event for event in bus.events if isinstance(event, DerivedData)).point_id == "p1"
    assert engine.summary()["engine_metrics"]["completed"] == 1


def test_multi_raw_events_are_snapshotted_once():
    GateModule.started.clear(); GateModule.release.set(); GateModule.order = []
    engine, bus = make_engine()
    bus.emit(MeasurementStarted(point_id="p1")); bus.emit(DataPoint(point_id="p1", data={"x": 2}))
    bus.emit(DataPoint(point_id="p1", data={"extra": 3})); bus.emit(MeasurementCompleted(point_id="p1"))
    engine.close()
    assert GateModule.order == ["p1"]
