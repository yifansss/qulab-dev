from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import DatasetModel, RunReader, RunStore, SliceController


def test_csv_slice_from_run_store_2d_scalar_grid(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="slice_csv", run_id="slice_csv")
    store.open()
    for freq in [1.0, 2.0]:
        for tau in [0.0, 1.0]:
            point_id = f"p{int(freq)}{int(tau)}"
            coords = {"mw_freq_hz": freq, "tau_s": tau}
            store.handle_event(MeasurementStarted(point_id=point_id, coords=coords))
            store.handle_event(DataPoint(point_id=point_id, coords=coords, data={"counts": freq + tau}))
            store.handle_event(MeasurementCompleted(point_id=point_id, status="ok", coords=coords))
    store.close()

    heatmap = SliceController(DatasetModel(RunReader(store.run_path))).slice_2d("counts", "mw_freq_hz", "tau_s")

    assert heatmap.values.tolist() == [[1.0, 2.0], [2.0, 3.0]]
