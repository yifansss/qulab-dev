import numpy as np
import pytest

from qulab.storage import DatasetModel, RunReader, SliceController, ZarrBackend, create_synthetic_advanced_run


def _controller(run_path, backend="csv") -> SliceController:
    return SliceController(DatasetModel(RunReader(run_path, backend=backend)))


def test_csv_1d_scalar_line_extraction(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 5}, include_trace=False, backend="csv")

    line = _controller(run_path).slice_1d("counts_mean", "mw_freq_hz")

    assert line.x.shape == (5,)
    assert line.y.tolist() == [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]


def test_csv_2d_scalar_heatmap_extraction(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path, dims={"mw_freq_hz": 3, "tau_s": 2}, include_trace=False, backend="csv"
    )

    heatmap = _controller(run_path).slice_2d("counts_mean", "mw_freq_hz", "tau_s")

    assert heatmap.values.shape == (2, 3)
    np.testing.assert_allclose(heatmap.values, [[1000.0, 1001.0, 1002.0], [1002.0, 1003.0, 1004.0]])


def test_csv_3d_scalar_heatmap_with_third_dimension_selector(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path, dims={"mw_freq_hz": 3, "tau_s": 2, "field_v": 2}, include_trace=False, backend="csv"
    )

    heatmap = _controller(run_path).slice_2d("counts_mean", "mw_freq_hz", "tau_s", {"field_v": 1})

    assert heatmap.values.shape == (2, 3)
    np.testing.assert_allclose(heatmap.values, [[1003.0, 1004.0, 1005.0], [1005.0, 1006.0, 1007.0]])


def test_csv_point_trace_lookup(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 4}, backend="csv")

    trace = _controller(run_path).get_point_trace("photon_bins", {"mw_freq_hz": 1, "tau_s": 0})

    assert trace.values.tolist() == [1.0, 2.0, 3.0, 4.0]


def test_csv_trace_defaults_time_axis_when_missing(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 2, "tau_s": 2}, backend="csv")

    trace = _controller(run_path).get_point_trace("photon_bins", {"mw_freq_hz": 1, "tau_s": 0})

    assert trace.values.shape == (20,)


def test_csv_multichannel_trace_lookup(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path,
        dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3, "channel": 2},
        backend="csv",
        multichannel=True,
    )

    trace = _controller(run_path).get_point_trace("photon_bins", {"mw_freq_hz": 0, "tau_s": 1}, channel=1)

    assert trace.values.tolist() == [102.0, 103.0, 104.0]


def test_missing_selector_for_hidden_dimension_is_clear(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path, dims={"mw_freq_hz": 3, "tau_s": 2, "field_v": 2}, include_trace=False, backend="csv"
    )

    with pytest.raises(ValueError, match="selectors required"):
        _controller(run_path).slice_2d("counts_mean", "mw_freq_hz", "tau_s")


@pytest.mark.skipif(not ZarrBackend.available(), reason="zarr is not installed")
def test_zarr_2d_scalar_heatmap_extraction(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path, dims={"mw_freq_hz": 3, "tau_s": 2}, include_trace=True, backend="zarr"
    )

    heatmap = _controller(run_path, backend="zarr").slice_2d("counts_mean", "mw_freq_hz", "tau_s")

    assert heatmap.values.shape == (2, 3)


@pytest.mark.skipif(not ZarrBackend.available(), reason="zarr is not installed")
def test_zarr_multichannel_trace_lookup(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path,
        dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3, "channel": 2},
        backend="zarr",
        multichannel=True,
    )

    trace = _controller(run_path, backend="zarr").get_point_trace("photon_bins", {"mw_freq_hz": 0, "tau_s": 1}, channel=1)

    assert trace.values.tolist() == [102.0, 103.0, 104.0]
