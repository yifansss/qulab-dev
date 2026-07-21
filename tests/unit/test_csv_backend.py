import json

from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import DatasetModel, RunReader, RunStore, SliceController


def test_run_store_writes_csv_backend_by_default(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="csv_default", run_id="csv_default")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 1.0, "tau_s": 0.0}))
    store.handle_event(DataPoint(point_id="p000001", coords={"mw_freq_hz": 1.0, "tau_s": 0.0}, data={"counts_mean": 10.0}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 1.0, "tau_s": 0.0}))
    store.handle_event(MeasurementStarted(point_id="p000002", coords={"mw_freq_hz": 2.0, "tau_s": 0.0}))
    store.handle_event(DataPoint(point_id="p000002", coords={"mw_freq_hz": 2.0, "tau_s": 0.0}, data={"counts_mean": 20.0}))
    store.handle_event(MeasurementCompleted(point_id="p000002", status="ok", coords={"mw_freq_hz": 2.0, "tau_s": 0.0}))
    store.close()

    manifest = json.loads((store.run_path / "dataset_manifest.json").read_text(encoding="utf-8"))
    reader = RunReader(store.run_path, backend="auto")
    line = SliceController(DatasetModel(reader)).slice_1d("counts_mean", "mw_freq_hz", {"tau_s": 0.0})

    assert manifest["preferred_backend"] == "csv"
    assert manifest["available_backends"] == ["csv"]
    assert manifest["data_vars"]["counts_mean"]["backends"]["csv"] == "tables/summaries/counts_mean.csv"
    assert (store.run_path / "tables" / "summaries" / "counts_mean.csv").exists()
    assert reader.backend_name == "csv"
    assert line.y.tolist() == [10.0, 20.0]


def test_run_store_csv_backend_supports_vector_and_multichannel_trace(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="csv_traces", run_id="csv_traces")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 1.0}))
    store.handle_event(
        DataPoint(
            point_id="p000001",
            coords={"mw_freq_hz": 1.0},
            data={"photon_bins": [1, 2, 3], "analog_trace": [[0.1, 0.2], [0.3, 0.4]]},
        )
    )
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 1.0}))
    store.close()

    controller = SliceController(DatasetModel(RunReader(store.run_path, backend="csv")))
    photon = controller.get_point_trace("photon_bins", {"mw_freq_hz": 1.0})
    analog = controller.get_point_trace("analog_trace", {"mw_freq_hz": 1.0}, channel=1.0)

    assert photon.values.tolist() == [1.0, 2.0, 3.0]
    assert analog.values.tolist() == [0.3, 0.4]
