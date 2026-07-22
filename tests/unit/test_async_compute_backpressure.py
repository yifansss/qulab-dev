import pytest

from qulab.analysis import AsyncComputeOverflow
from qulab.core import DerivedData
from test_async_compute_queue import GateModule, make_engine, point


@pytest.mark.parametrize("policy,expected", [("skip_newest", ["p1", "p2"]), ("skip_oldest", ["p1", "p3"]),
                                               ("latest", ["p1", "p3"])])
def test_drop_policies_are_deterministic(policy, expected):
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine(policy)
    point(bus, 1); assert GateModule.started.wait(1)
    point(bus, 2); point(bus, 3)
    assert engine.summary()["queue_depth"] <= 1
    GateModule.release.set(); engine.close()
    assert GateModule.order == expected
    assert engine.summary()["engine_metrics"]["dropped"] == 1


def test_disable_module_stops_future_enqueue():
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine("disable_module")
    point(bus, 1); assert GateModule.started.wait(1); point(bus, 2); point(bus, 3); point(bus, 4)
    GateModule.release.set(); engine.close()
    assert GateModule.order == ["p1", "p2"]
    assert engine.summary()["engine_metrics"]["dropped"] == 1


def test_fail_policy_raises_after_current_raw_event_dispatch():
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine("fail")
    point(bus, 1); assert GateModule.started.wait(1); point(bus, 2)
    with pytest.raises(AsyncComputeOverflow): point(bus, 3)
    GateModule.release.set(); engine.close()
