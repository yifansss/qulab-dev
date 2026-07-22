import pytest

from qulab.analysis import (AnalysisExecutionPlan, AnalysisLiveConfig, AnalysisModuleRegistry,
                            AnalysisSourceIdentity, ComputeModulePlan, LiveComputeEngine, LiveComputeError)
from qulab.core import DataPoint, DerivedData, EventBus, MeasurementCompleted, MeasurementStarted


class Scale:
    name = "scale"; version = "1"; input_keys = ("x",); output_keys = ("y",)
    calls = 0
    def setup(self, config, run_context): self.factor = config.get("factor", 2)
    def process_point(self, point):
        self.calls += 1
        return {"y": point.data["x"] * self.factor}
    def close(self): self.closed = True


def make_plan(*, policy="warn", save=True, show=False, inputs=("x",), outputs=("y",), namespace=None):
    effective = tuple(f"{namespace}.{key}" if namespace else key for key in outputs)
    item = ComputeModulePlan("scale", "fake", "Scale", "class", True, True, False, show, save, policy,
                             inputs, outputs, effective, {"factor": 3}, AnalysisSourceIdentity("fake", None, None, "1"), namespace)
    return AnalysisExecutionPlan(AnalysisLiveConfig(enabled=True), (item,), inputs, effective)


def engine(plan=None):
    bus = EventBus(); registry = AnalysisModuleRegistry(); registry.register("fake:Scale", Scale)
    value = LiveComputeEngine(plan or make_plan(), registry, bus); value.setup({"run_id": "r"}); bus.subscribe(value.handle_event)
    return value, bus


def test_lifecycle_merge_and_exactly_once():
    Scale.calls = 0
    value, bus = engine()
    bus.emit(MeasurementStarted(point_id="p1", coords={"i": 1}))
    bus.emit(DataPoint(point_id="p1", coords={"i": 1}, data={"other": 0}))
    assert not [event for event in bus.events if isinstance(event, DerivedData)]
    bus.emit(DataPoint(point_id="p1", coords={"i": 1}, data={"x": 2}))
    bus.emit(DataPoint(point_id="p1", coords={"i": 1}, data={"x": 2}))
    derived = [event for event in bus.events if isinstance(event, DerivedData)]
    assert len(derived) == 1 and derived[0].data == {"y": 6}
    assert value._runtimes["scale"].calls == 1
    bus.emit(MeasurementCompleted(point_id="p1", coords={"i": 1}))
    assert value.active_point_count == 0
    runtime = value._runtimes["scale"]
    value.close(); value.close()
    assert runtime.closed


def test_namespace_and_raw_collision_fail_closed():
    value, bus = engine(make_plan(namespace="preview"))
    bus.emit(DataPoint(point_id="p1", data={"x": 2}))
    assert next(e for e in bus.events if isinstance(e, DerivedData)).data == {"preview.y": 6}
    value2, bus2 = engine()
    bus2.emit(DataPoint(point_id="p1", data={"x": 1}))
    with pytest.raises(LiveComputeError):
        bus2.emit(DataPoint(point_id="p1", data={"x": 2}))


def test_missing_input_fail_policy():
    value, bus = engine(make_plan(policy="fail"))
    bus.emit(MeasurementStarted(point_id="p1"))
    with pytest.raises(LiveComputeError):
        bus.emit(MeasurementCompleted(point_id="p1"))
