from qulab.storage import create_synthetic_advanced_run
from qulab.viewer.models import ViewerState
from qulab.viewer.plot_data import heatmap_from_run, line_from_run, trace_from_run
from qulab.viewer.pyqt_viewer_app import _axis_options_for, _plot_modes_for, _reduced_heatmap, _reduced_line
from qulab.storage import DatasetModel, RunReader


def test_viewer_state_opens_dataset_model(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    model = ViewerState(run_path, backend="csv").open_model()

    assert model.list_data_keys() == ["counts_mean", "photon_bins"]


def test_viewer_plot_helpers_use_shared_slice_controller(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3}, backend="csv")

    line = line_from_run(run_path, "counts_mean", "mw_freq_hz", {"tau_s": 0}, backend="csv")
    heatmap = heatmap_from_run(run_path, "counts_mean", "mw_freq_hz", "tau_s", backend="csv")
    trace = trace_from_run(run_path, "photon_bins", {"mw_freq_hz": 0, "tau_s": 0}, backend="csv")

    assert line.y.tolist() == [1000.0, 1001.0]
    assert heatmap.values.shape == (2, 2)
    assert trace.values.tolist() == [0.0, 1.0, 2.0]


def test_viewer_plot_modes_are_kind_driven_for_trace_grid(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3}, backend="csv")
    model = DatasetModel(RunReader(run_path, backend="csv"))

    scalar = model.get_data_var_metadata("counts_mean")
    trace = model.get_data_var_metadata("photon_bins")

    assert _plot_modes_for(scalar) == ("Heatmap", "Line Slice")
    assert _plot_modes_for(trace) == ("Trace", "Trace Mean Heatmap", "Trace Mean Line")
    assert _axis_options_for(trace, "Trace Mean Heatmap")[0] == ("mw_freq_hz", "tau_s")


def test_viewer_trace_mean_views_reduce_time_dimension(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, dims={"mw_freq_hz": 2, "tau_s": 2, "time_s": 3}, backend="csv")
    model = DatasetModel(RunReader(run_path, backend="csv"))

    x, line = _reduced_line(model, "photon_bins", "mw_freq_hz", {"tau_s": 0})
    hx, hy, heatmap = _reduced_heatmap(model, "photon_bins", "mw_freq_hz", "tau_s", {})

    assert x.tolist() == [2860000000.0, 2880000000.0]
    assert line.tolist() == [1.0, 2.0]
    assert heatmap.shape == (2, 2)
