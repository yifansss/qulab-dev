from qulab.storage import DatasetManifest, normalize_storage_backends


def test_storage_backends_default_to_csv() -> None:
    assert normalize_storage_backends() == ["csv"]


def test_zarr_selection_keeps_csv_baseline() -> None:
    assert normalize_storage_backends(config={"storage": {"backend": "zarr"}}) == ["csv", "zarr"]
    assert normalize_storage_backends(config={"storage": {"backends": ["zarr"]}}) == ["csv", "zarr"]


def test_dataset_manifest_round_trip(tmp_path) -> None:
    manifest = DatasetManifest(
        preferred_backend="csv",
        available_backends=["csv"],
        coords={"mw_freq_hz": {"unit": "Hz"}},
        data_vars={"counts": {"kind": "scalar_grid", "dims": ["mw_freq_hz"], "unit": "count", "backends": {"csv": "tables/summaries/counts.csv"}}},
    )

    path = tmp_path / "dataset_manifest.json"
    manifest.write(path)

    loaded = DatasetManifest.read(path)
    assert loaded.preferred_backend == "csv"
    assert loaded.available_backends == ["csv"]
    assert loaded.data_vars["counts"]["dims"] == ["mw_freq_hz"]
