import json

import pytest

from qulab.storage import OptionalDependencyError, RunReader, ZarrBackend, create_synthetic_advanced_run


def test_run_reader_reads_existing_jsonl_only_run(tmp_path) -> None:
    run_path = tmp_path / "jsonl_run"
    run_path.mkdir()
    (run_path / "metadata.json").write_text(
        json.dumps({"data_keys": [{"key": "counts", "kind": "scalar", "unit": None}]}), encoding="utf-8"
    )
    (run_path / "data.jsonl").write_text(
        json.dumps({"coords": {"mw_freq_hz": 1.0}, "data": {"counts": 2.0}}) + "\n"
        + json.dumps({"coords": {"mw_freq_hz": 2.0}, "data": {"counts": 3.0}}) + "\n",
        encoding="utf-8",
    )

    reader = RunReader(run_path)
    data = reader.get_data_var("counts")

    assert reader.backend_name is None
    assert reader.list_data_keys() == ["counts"]
    assert data.dims == ("mw_freq_hz",)
    assert data.values.tolist() == [2.0, 3.0]


def test_backend_auto_falls_back_to_csv(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    reader = RunReader(run_path, backend="auto")

    assert reader.backend_name == "csv"


def test_forced_zarr_gives_clear_error_when_unavailable(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="csv")

    with pytest.raises(OptionalDependencyError, match="Zarr|zarr"):
        RunReader(run_path, backend="zarr")


@pytest.mark.skipif(not ZarrBackend.available(), reason="zarr is not installed")
def test_backend_auto_prefers_zarr_when_available(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="both")

    reader = RunReader(run_path, backend="auto")

    assert reader.backend_name == "zarr"


@pytest.mark.skipif(not ZarrBackend.available(), reason="zarr is not installed")
def test_forced_csv_works_even_when_zarr_exists(tmp_path) -> None:
    run_path = create_synthetic_advanced_run(tmp_path, backend="both")

    reader = RunReader(run_path, backend="csv")

    assert reader.backend_name == "csv"
