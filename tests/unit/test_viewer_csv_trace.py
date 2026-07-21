from __future__ import annotations

from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import DatasetModel, RunReader, RunStore, SliceController, create_synthetic_advanced_run


def test_viewer_csv_point_trace_with_status_from_run_store(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="trace_status", run_id="trace_status")
    coords = {"mw_freq_hz": 2.87e9, "tau_s": 1e-7}
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords=coords))
    store.handle_event(DataPoint(point_id="p000001", coords=coords, data={"photon_bins": [1, 2, 3]}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords=coords))
    store.close()

    trace = SliceController(DatasetModel(RunReader(store.run_path, backend="csv"))).get_point_trace(
        "photon_bins", coords
    )

    assert trace.time.tolist() == [0.0, 1.0, 2.0]
    assert trace.values.tolist() == [1.0, 2.0, 3.0]
    assert trace.point_coords == coords
    assert trace.point_status == "ok"


def test_viewer_csv_multichannel_trace_channel_selection(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path,
        dims={"mw_freq_hz": 2, "tau_s": 1, "channel": 2, "time_s": 3},
        backend="csv",
        multichannel=True,
    )
    controller = SliceController(DatasetModel(RunReader(run_path, backend="csv")))

    trace = controller.get_point_trace("photon_bins", {"mw_freq_hz": 2860000000.0, "tau_s": 0.0}, channel=1)

    assert trace.time.tolist() == [0.0, 5e-07, 1e-06]
    assert trace.values.tolist() == [100.0, 101.0, 102.0]
