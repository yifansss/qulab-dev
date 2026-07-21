import json

import pytest

from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import OptionalDependencyError, RunReader, RunStore, ZarrBackend


def test_run_reader_auto_uses_default_csv_run_store_backend(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="reader", run_id="reader")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 1.0}))
    store.handle_event(DataPoint(point_id="p000001", coords={"mw_freq_hz": 1.0}, data={"counts": 2.0}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 1.0}))
    store.close()

    reader = RunReader(store.run_path)

    assert reader.backend_name == "csv"
    assert reader.get_data_var("counts").values.tolist() == [2.0]


def test_zarr_config_declares_csv_and_zarr_when_available_or_errors_cleanly(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="zarr_requested", run_id="zarr_requested", config={"storage": {"backend": "zarr"}})
    if not ZarrBackend.available():
        with pytest.raises(OptionalDependencyError, match="Zarr|zarr"):
            store.open()
        return

    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 1.0}))
    store.handle_event(DataPoint(point_id="p000001", coords={"mw_freq_hz": 1.0}, data={"counts": 2.0}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 1.0}))
    store.close()

    manifest = json.loads((store.run_path / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["available_backends"] == ["csv", "zarr"]
    assert RunReader(store.run_path, backend="csv").backend_name == "csv"
