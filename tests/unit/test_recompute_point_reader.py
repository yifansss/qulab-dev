from qulab.core import DataPoint, DerivedData, MeasurementCompleted, MeasurementStarted
from qulab.storage import RunReader, RunStore


def test_iter_compute_points_merges_raw_events_and_excludes_live(tmp_path):
    store = RunStore(tmp_path, "source", run_id="source")
    store.open(); store.handle_event(MeasurementStarted(point_id="p1", coords={"x": 1}))
    store.handle_event(DataPoint(point_id="p1", coords={"x": 1}, data={"a": 1}))
    store.handle_event(DataPoint(point_id="p1", coords={"x": 1}, data={"b": 2}))
    store.handle_event(DerivedData(point_id="p1", coords={"x": 1}, data={"d": 3}, source_module="m"))
    store.handle_event(MeasurementCompleted(point_id="p1", coords={"x": 1}, status="ok")); store.close()
    point = list(RunReader(store.run_path).iter_compute_points(["a", "b"]))[0]
    assert point.data == {"a": 1, "b": 2}
    live = list(RunReader(store.run_path).iter_compute_points(["live:d"]))[0]
    assert live.data == {"live:d": 3}
