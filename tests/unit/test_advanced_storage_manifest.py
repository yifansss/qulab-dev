import json

from qulab.storage import RunReader, create_synthetic_advanced_run


def test_synthetic_csv_manifest_declares_csv_backend(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    manifest = json.loads((run_path / "dataset_manifest.json").read_text(encoding="utf-8"))
    reader = RunReader(run_path)

    assert manifest["backends"] == {"csv": "tables"}
    assert reader.backend_name == "csv"
    assert reader.list_data_keys() == ["counts_mean", "photon_bins"]


def test_forced_csv_backend_works_with_manifest(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    reader = RunReader(run_path, backend="csv")

    assert reader.backend_name == "csv"
    assert reader.get_data_var("counts_mean").dims == ("mw_freq_hz", "tau_s")
