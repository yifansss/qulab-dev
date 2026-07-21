from __future__ import annotations

from qulab.storage import DatasetModel, RunReader, SliceController, create_synthetic_advanced_run


def test_viewer_csv_line_heatmap_and_hidden_selectors(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path,
        dims={"mw_freq_hz": 3, "tau_s": 2, "field_v": 2, "time_s": 4},
        backend="csv",
    )
    controller = SliceController(DatasetModel(RunReader(run_path, backend="csv")))

    assert controller.selector_dims("counts_mean", ("mw_freq_hz",)) == ("tau_s", "field_v")
    line = controller.slice_1d("counts_mean", "mw_freq_hz", {"tau_s": 0, "field_v": -1.0})
    heatmap = controller.slice_2d("counts_mean", "mw_freq_hz", "tau_s", {"field_v": -1.0})
    profile = controller.profile("counts_mean", "tau_s", {"mw_freq_hz": 2860000000.0, "field_v": -1.0})

    assert line.x.shape == (3,)
    assert line.y.tolist() == [1000.0, 1001.0, 1002.0]
    assert heatmap.values.shape == (2, 3)
    assert profile.x.shape == (2,)
    assert profile.y.tolist() == [1000.0, 1002.0]
