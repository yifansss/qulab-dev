"""Generate larger advanced storage runs for viewer stability testing."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from qulab.storage import ZarrBackend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="runs/advanced_test_data/large_stability_validation")
    parser.add_argument("--force", action="store_true", help="Allow writing into an existing directory")
    parser.add_argument("--include-zarr", action="store_true", help="Also generate same-size Zarr runs when zarr is installed")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if root.exists() and not args.force:
        raise SystemExit(f"{root} already exists; pass --force or choose another --root")
    root.mkdir(parents=True, exist_ok=True)

    runs = [
        _write_scalar_run(root / "large_csv_2d_scalar_600x500", {"mw_freq_hz": 600, "tau_s": 500}),
        _write_scalar_run(root / "large_csv_3d_scalar_260x200x24", {"mw_freq_hz": 260, "tau_s": 200, "field_v": 24}),
        _write_trace_run(root / "large_csv_trace_90x70x600", {"mw_freq_hz": 90, "tau_s": 70, "time_s": 600}),
        _write_trace_run(
            root / "large_csv_multichannel_trace_70x50x2x450",
            {"mw_freq_hz": 70, "tau_s": 50, "channel": 2, "time_s": 450},
            multichannel=True,
        ),
    ]
    zarr_status = "not requested"
    if args.include_zarr:
        if ZarrBackend.available():
            zarr_status = "generated"
            runs.extend(
                [
                    _write_zarr_scalar_run(root / "large_zarr_2d_scalar_600x500", {"mw_freq_hz": 600, "tau_s": 500}),
                    _write_zarr_scalar_run(
                        root / "large_zarr_3d_scalar_260x200x24", {"mw_freq_hz": 260, "tau_s": 200, "field_v": 24}
                    ),
                    _write_zarr_trace_run(root / "large_zarr_trace_90x70x600", {"mw_freq_hz": 90, "tau_s": 70, "time_s": 600}),
                    _write_zarr_trace_run(
                        root / "large_zarr_multichannel_trace_70x50x2x450",
                        {"mw_freq_hz": 70, "tau_s": 50, "channel": 2, "time_s": 450},
                        multichannel=True,
                    ),
                ]
            )
        else:
            zarr_status = "skipped because optional package 'zarr' is unavailable"
    _write_readme(root, runs, zarr_status)
    print(root)
    for path in runs:
        print(path)
    if args.include_zarr and zarr_status.startswith("skipped"):
        print(zarr_status)
    return 0


def _write_scalar_run(run_path: Path, dims: dict[str, int]) -> Path:
    run_path.mkdir(parents=True, exist_ok=True)
    coords = _coords(dims)
    slow_dims = tuple(coords)
    _write_common_run_files(run_path, run_path.name)
    _write_coords(run_path, coords)
    _write_summary_csv(run_path / "tables" / "summaries" / "counts_mean.csv", coords, slow_dims)
    _write_manifest(run_path, coords, {"counts_mean": {"dims": list(slow_dims), "kind": "scalar_grid", "unit": "count", "backends": {"csv": "tables/summaries/counts_mean.csv"}}})
    _write_data_keys(run_path, [("counts_mean", "scalar_grid")])
    return run_path


def _write_trace_run(run_path: Path, dims: dict[str, int], multichannel: bool = False) -> Path:
    run_path.mkdir(parents=True, exist_ok=True)
    coords = _coords(dims)
    slow_dims = tuple(dim for dim in ("mw_freq_hz", "tau_s", "field_v") if dim in coords)
    trace_dims = list(slow_dims)
    if multichannel:
        trace_dims.append("channel")
    trace_dims.append("time_s")
    _write_common_run_files(run_path, run_path.name)
    _write_coords(run_path, coords)
    _write_summary_csv(run_path / "tables" / "summaries" / "counts_mean.csv", coords, slow_dims)
    _write_trace_csv(run_path / "tables" / "traces" / "photon_bins.csv", coords, tuple(trace_dims), len(slow_dims), multichannel)
    _write_manifest(
        run_path,
        coords,
        {
            "counts_mean": {
                "dims": list(slow_dims),
                "kind": "scalar_grid",
                "unit": "count",
                "backends": {"csv": "tables/summaries/counts_mean.csv"},
            },
            "photon_bins": {
                "dims": trace_dims,
                "kind": "trace_grid",
                "unit": "count",
                "backends": {"csv": "tables/traces/photon_bins.csv"},
            },
        },
    )
    _write_data_keys(run_path, [("counts_mean", "scalar_grid"), ("photon_bins", "trace_grid")])
    return run_path


def _write_zarr_scalar_run(run_path: Path, dims: dict[str, int]) -> Path:
    import zarr  # type: ignore

    run_path.mkdir(parents=True, exist_ok=True)
    coords = _coords(dims)
    slow_dims = tuple(coords)
    _write_common_run_files(run_path, run_path.name)
    root = zarr.open_group(str(run_path / "arrays.zarr"), mode="w")
    for dim, values in coords.items():
        _zarr_write(root, f"coords/{dim}", values)
    shape = tuple(len(coords[dim]) for dim in slow_dims)
    chunks = tuple(min(size, chunk) for size, chunk in zip(shape, (128, 128, 8)))
    summary = _zarr_create(root, "summaries/counts_mean", shape, chunks)
    _fill_summary_zarr(summary, shape)
    _write_manifest(
        run_path,
        coords,
        {"counts_mean": {"dims": list(slow_dims), "kind": "scalar_grid", "unit": "count", "backends": {"zarr": "arrays.zarr:/summaries/counts_mean"}}},
        backends={"zarr": "arrays.zarr"},
    )
    _write_data_keys(run_path, [("counts_mean", "scalar_grid")])
    return run_path


def _write_zarr_trace_run(run_path: Path, dims: dict[str, int], multichannel: bool = False) -> Path:
    import zarr  # type: ignore

    run_path.mkdir(parents=True, exist_ok=True)
    coords = _coords(dims)
    slow_dims = tuple(dim for dim in ("mw_freq_hz", "tau_s", "field_v") if dim in coords)
    trace_dims = list(slow_dims)
    if multichannel:
        trace_dims.append("channel")
    trace_dims.append("time_s")
    _write_common_run_files(run_path, run_path.name)
    root = zarr.open_group(str(run_path / "arrays.zarr"), mode="w")
    for dim, values in coords.items():
        _zarr_write(root, f"coords/{dim}", values)
    summary_shape = tuple(len(coords[dim]) for dim in slow_dims)
    summary = _zarr_create(root, "summaries/counts_mean", summary_shape, tuple(min(size, chunk) for size, chunk in zip(summary_shape, (128, 128, 8))))
    _fill_summary_zarr(summary, summary_shape)
    trace_shape = tuple(len(coords[dim]) for dim in trace_dims)
    trace_chunks = tuple(min(size, chunk) for size, chunk in zip(trace_shape, (16, 16, 1, 256) if multichannel else (16, 16, 256)))
    trace = _zarr_create(root, "traces/photon_bins", trace_shape, trace_chunks)
    _fill_trace_zarr(trace, trace_shape, len(slow_dims), multichannel)
    _write_manifest(
        run_path,
        coords,
        {
            "counts_mean": {
                "dims": list(slow_dims),
                "kind": "scalar_grid",
                "unit": "count",
                "backends": {"zarr": "arrays.zarr:/summaries/counts_mean"},
            },
            "photon_bins": {
                "dims": trace_dims,
                "kind": "trace_grid",
                "unit": "count",
                "backends": {"zarr": "arrays.zarr:/traces/photon_bins"},
            },
        },
        backends={"zarr": "arrays.zarr"},
    )
    _write_data_keys(run_path, [("counts_mean", "scalar_grid"), ("photon_bins", "trace_grid")])
    return run_path


def _coords(dims: dict[str, int]) -> dict[str, np.ndarray]:
    coords: dict[str, np.ndarray] = {}
    if "mw_freq_hz" in dims:
        coords["mw_freq_hz"] = np.linspace(2.84e9, 2.90e9, dims["mw_freq_hz"])
    if "tau_s" in dims:
        coords["tau_s"] = np.linspace(0.0, 5e-6, dims["tau_s"])
    if "field_v" in dims:
        coords["field_v"] = np.linspace(-2.0, 2.0, dims["field_v"])
    if "channel" in dims:
        coords["channel"] = np.arange(dims["channel"])
    if "time_s" in dims:
        coords["time_s"] = np.linspace(0.0, 3e-6, dims["time_s"])
    return coords


def _write_common_run_files(run_path: Path, run_id: str) -> None:
    _write_json(run_path / "metadata.json", {"schema_version": 1, "run_id": run_id, "experiment_name": run_id, "data_keys": []})
    for name in ("events.jsonl", "points.jsonl", "data.jsonl"):
        (run_path / name).write_text("", encoding="utf-8")
    _write_rows(run_path / "tables" / "points.csv", ["point_id"], [])


def _write_coords(run_path: Path, coords: dict[str, np.ndarray]) -> None:
    for dim, values in coords.items():
        _write_rows(run_path / "tables" / "coords" / f"{dim}.csv", [dim], ({dim: value} for value in values))


def _write_summary_csv(path: Path, coords: dict[str, np.ndarray], dims: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[*dims, "value"])
        writer.writeheader()
        shape = tuple(len(coords[dim]) for dim in dims)
        for index in np.ndindex(shape):
            row = {dim: coords[dim][item] for dim, item in zip(dims, index)}
            row["value"] = 1000.0 + sum((axis + 1) * item for axis, item in enumerate(index))
            writer.writerow(row)


def _write_trace_csv(path: Path, coords: dict[str, np.ndarray], dims: tuple[str, ...], slow_count: int, multichannel: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[*dims, "value"])
        writer.writeheader()
        shape = tuple(len(coords[dim]) for dim in dims)
        for index in np.ndindex(shape):
            row = {dim: coords[dim][item] for dim, item in zip(dims, index)}
            slow_part = index[:slow_count]
            channel_offset = index[slow_count] * 100 if multichannel else 0
            row["value"] = sum((axis + 1) * item for axis, item in enumerate(slow_part)) + channel_offset + index[-1]
            writer.writerow(row)


def _write_manifest(
    run_path: Path, coords: dict[str, np.ndarray], data_vars: dict[str, Any], backends: dict[str, str] | None = None
) -> None:
    backends = backends or {"csv": "tables"}
    manifest_coords = {
        dim: {
            "unit": {"mw_freq_hz": "Hz", "tau_s": "s", "time_s": "s", "field_v": "V"}.get(dim),
            "backends": {"zarr": f"arrays.zarr:/coords/{dim}"} if "zarr" in backends else {"csv": f"tables/coords/{dim}.csv"},
        }
        for dim in coords
    }
    _write_json(run_path / "dataset_manifest.json", {"schema_version": 1, "backends": backends, "coords": manifest_coords, "data_vars": data_vars})


def _write_data_keys(run_path: Path, rows: list[tuple[str, str]]) -> None:
    _write_rows(run_path / "tables" / "data_keys.csv", ["key", "kind"], ({"key": key, "kind": kind} for key, kind in rows))


def _write_rows(path: Path, fieldnames: list[str], rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_readme(root: Path, runs: list[Path], zarr_status: str) -> None:
    lines = [
        "# Large Qulab Advanced Storage Stability Data",
        "",
        "This batch intentionally targets the 200MB-1GB range for manual viewer stability testing.",
        f"Zarr status: {zarr_status}.",
        "",
        "Runs:",
    ]
    lines.extend(f"- `{path.name}`" for path in runs)
    lines.extend(["", "Open with:", "", "```bash"])
    lines.extend(f"PYTHONPATH=src python -m qulab.viewer.pyqt_viewer_app {path} csv" for path in runs)
    lines.extend(["```", ""])
    root.joinpath("README.md").write_text("\n".join(lines), encoding="utf-8")


def _zarr_write(root: Any, key: str, values: np.ndarray) -> None:
    if hasattr(root, "create_array"):
        root.create_array(key, data=values, overwrite=True)
    else:
        root.create_dataset(key, data=values, overwrite=True)


def _zarr_create(root: Any, key: str, shape: tuple[int, ...], chunks: tuple[int, ...]) -> Any:
    if hasattr(root, "create_array"):
        return root.create_array(key, shape=shape, chunks=chunks, dtype="f8", overwrite=True)
    return root.create_dataset(key, shape=shape, chunks=chunks, dtype="f8", overwrite=True)


def _fill_summary_zarr(array: Any, shape: tuple[int, ...]) -> None:
    first_dim = shape[0] if shape else 0
    for start in range(0, first_dim, 32):
        stop = min(start + 32, first_dim)
        block_shape = (stop - start, *shape[1:])
        block = np.zeros(block_shape, dtype=float)
        for local_index in np.ndindex(block_shape):
            index = (local_index[0] + start, *local_index[1:])
            block[local_index] = 1000.0 + sum((axis + 1) * item for axis, item in enumerate(index))
        array[start:stop, ...] = block


def _fill_trace_zarr(array: Any, shape: tuple[int, ...], slow_count: int, multichannel: bool) -> None:
    first_dim = shape[0] if shape else 0
    for start in range(0, first_dim, 8):
        stop = min(start + 8, first_dim)
        block_shape = (stop - start, *shape[1:])
        block = np.zeros(block_shape, dtype=float)
        for local_index in np.ndindex(block_shape):
            index = (local_index[0] + start, *local_index[1:])
            slow_part = index[:slow_count]
            channel_offset = index[slow_count] * 100 if multichannel else 0
            block[local_index] = sum((axis + 1) * item for axis, item in enumerate(slow_part)) + channel_offset + index[-1]
        array[start:stop, ...] = block


if __name__ == "__main__":
    raise SystemExit(main())
