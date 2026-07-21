import pytest

from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import DatasetModel, RunReader, RunStore, SliceController


pytest.importorskip("zarr")


def test_zarr_slice_from_run_store_when_optional_dependency_exists(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="slice_zarr", run_id="slice_zarr", config={"storage": {"backend": "zarr"}})
    store.open()
    for freq in [1.0, 2.0]:
        coords = {"mw_freq_hz": freq}
        store.handle_event(MeasurementStarted(point_id=f"p{int(freq)}", coords=coords))
        store.handle_event(DataPoint(point_id=f"p{int(freq)}", coords=coords, data={"counts": freq}))
        store.handle_event(MeasurementCompleted(point_id=f"p{int(freq)}", status="ok", coords=coords))
    store.close()

    line = SliceController(DatasetModel(RunReader(store.run_path, backend="zarr"))).slice_1d("counts", "mw_freq_hz")

    assert line.y.tolist() == [1.0, 2.0]
