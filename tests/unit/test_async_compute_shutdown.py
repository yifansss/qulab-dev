from qulab.core import DerivedData
from test_async_compute_queue import GateModule, make_engine, point


def test_no_drain_cancels_pending_and_suppresses_late_hung_result():
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine(drain=False)
    point(bus, 1); assert GateModule.started.wait(1); point(bus, 2)
    engine.close()
    summary = engine.summary()["engine_metrics"]
    assert summary["dropped"] == 1 and summary["worker_state"] == "hung"
    before = len([event for event in bus.events if isinstance(event, DerivedData)])
    GateModule.release.set(); engine._worker.join(1)
    assert before == 0 and not [event for event in bus.events if isinstance(event, DerivedData)]


def test_drain_timeout_marks_pending_and_hung_without_claiming_thread_kill():
    GateModule.started.clear(); GateModule.release.clear(); GateModule.order = []
    engine, bus = make_engine(drain=True, timeout=.02)
    point(bus, 1); assert GateModule.started.wait(1); point(bus, 2)
    engine.close()
    metrics = engine.summary()["engine_metrics"]
    assert metrics["dropped"] == 1 and metrics["worker_state"] == "hung"
    GateModule.release.set(); engine._worker.join(1)
