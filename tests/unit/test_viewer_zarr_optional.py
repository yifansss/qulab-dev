from __future__ import annotations

import pytest

pytest.importorskip("zarr")

from qulab.storage import DatasetModel, RunReader, SliceController, create_synthetic_advanced_run


def test_viewer_zarr_line_heatmap_and_trace_when_installed(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path,
        dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3},
        backend="both",
    )
    reader = RunReader(run_path, backend="zarr")
    controller = SliceController(DatasetModel(reader))

    line = controller.slice_1d("counts_mean", "mw_freq_hz", {"tau_s": 0.0})
    heatmap = controller.slice_2d("counts_mean", "mw_freq_hz", "tau_s")
    trace = controller.get_point_trace("photon_bins", {"mw_freq_hz": 2860000000.0, "tau_s": 0.0})

    assert reader.backend_name == "zarr"
    assert line.y.tolist() == [1000.0, 1001.0]
    assert heatmap.values.shape == (2, 2)
    assert trace.values.tolist() == [0.0, 1.0, 2.0]
