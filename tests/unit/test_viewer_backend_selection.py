from __future__ import annotations

import pytest

from qulab.core import DataPoint, MeasurementCompleted, MeasurementStarted
from qulab.storage import OptionalDependencyError, RunReader, RunStore, ZarrBackend, create_synthetic_advanced_run


def test_viewer_backend_selector_auto_uses_csv_for_csv_only_run(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    reader = RunReader(run_path, backend="auto")

    assert reader.backend_name == "csv"
    assert reader.list_data_keys() == ["counts_mean", "photon_bins"]


def test_viewer_backend_selector_zarr_unavailable_or_selected(tmp_path) -> None:
    if not ZarrBackend.available():
        run_path = create_synthetic_advanced_run(tmp_path, backend="csv")
        with pytest.raises(OptionalDependencyError, match="Zarr|zarr"):
            RunReader(run_path, backend="zarr")
        return

    run_path = create_synthetic_advanced_run(tmp_path, backend="both")
    assert RunReader(run_path, backend="auto").backend_name == "zarr"
    assert RunReader(run_path, backend="csv").backend_name == "csv"
    assert RunReader(run_path, backend="zarr").backend_name == "zarr"


def test_run_store_defaults_to_mandatory_csv_backend(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="mandatory_csv", run_id="mandatory_csv")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 1.0}))
    store.handle_event(DataPoint(point_id="p000001", coords={"mw_freq_hz": 1.0}, data={"counts": 2.0}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 1.0}))
    store.close()

    assert (store.run_path / "data.jsonl").exists()
    assert (store.run_path / "tables" / "summaries" / "counts.csv").exists()
    assert (store.run_path / "dataset_manifest.json").exists()
    assert RunReader(store.run_path, backend="csv").backend_name == "csv"
