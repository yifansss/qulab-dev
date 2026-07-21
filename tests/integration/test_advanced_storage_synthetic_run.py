from qulab.storage import DatasetModel, RunReader, SliceController, create_synthetic_advanced_run


def test_synthetic_csv_run_supports_reader_model_and_slicing(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(
        tmp_path, dims={"mw_freq_hz": 4, "tau_s": 3, "time_s": 5}, backend="csv"
    )

    reader = RunReader(run_path)
    model = DatasetModel(reader)
    controller = SliceController(model)

    assert reader.backend_name == "csv"
    assert model.describe_data_key("photon_bins").dims == ("mw_freq_hz", "tau_s", "time_s")
    assert controller.slice_2d("counts_mean", "mw_freq_hz", "tau_s").values.shape == (3, 4)
    assert controller.get_point_trace("photon_bins", {"mw_freq_hz": 0, "tau_s": 0}).values.shape == (5,)
