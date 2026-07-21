"""Synthetic advanced runs for reader and viewer tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .array_backend import OptionalDependencyError
from .zarr_backend import ZarrBackend


def create_synthetic_advanced_run(
    root: Path | str,
    dims: dict[str, int] | None = None,
    include_trace: bool = True,
    backend: Literal["csv", "zarr", "both"] = "csv",
    multichannel: bool = False,
    run_id: str = "synthetic_advanced_run",
) -> Path:
    """Create a fake run folder with a shared manifest and CSV/Zarr data."""

    dims = dict(dims or {"mw_freq_hz": 5, "tau_s": 4, "time_s": 20})
    if include_trace:
        dims.setdefault("time_s", 20)
    run_path = Path(root) / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    _write_json(run_path / "metadata.json", {"schema_version": 1, "run_id": run_id, "experiment_name": run_id, "data_keys": []})
    (run_path / "events.jsonl").write_text("", encoding="utf-8")
    (run_path / "points.jsonl").write_text("", encoding="utf-8")
    (run_path / "data.jsonl").write_text("", encoding="utf-8")

    coords = _make_coords(dims, multichannel)
    slow_dims = tuple(dim for dim in ("mw_freq_hz", "tau_s", "field_v") if dim in coords)
    summary = _summary_values(coords, slow_dims)
    trace = _trace_values(coords, slow_dims, multichannel) if include_trace else None
    backends: dict[str, str] = {}
    data_vars: dict[str, Any] = {}
    manifest_coords = {dim: {"unit": _unit_for(dim), "backends": {}} for dim in coords}

    if backend in {"csv", "both"}:
        backends["csv"] = "tables"
        _write_csv_backend(run_path, coords, slow_dims, summary, trace, multichannel)
        for dim in coords:
            manifest_coords[dim]["backends"]["csv"] = f"tables/coords/{dim}.csv"
    if backend in {"zarr", "both"}:
        if not ZarrBackend.available():
            raise OptionalDependencyError("Zarr synthetic run requested but optional 'zarr' package is unavailable")
        backends["zarr"] = "arrays.zarr"
        _write_zarr_backend(run_path, coords, slow_dims, summary, trace, multichannel)

    data_vars["counts_mean"] = {
        "dims": list(slow_dims),
        "kind": "scalar_grid",
        "unit": "count",
        "value_column": "value",
        "backends": {},
    }
    if "csv" in backends:
        data_vars["counts_mean"]["backends"]["csv"] = "tables/summaries/counts_mean.csv"
    if "zarr" in backends:
        data_vars["counts_mean"]["backends"]["zarr"] = "arrays.zarr:/summaries/counts_mean"

    if include_trace:
        trace_dims = list(slow_dims)
        if multichannel:
            trace_dims.append("channel")
        trace_dims.append("time_s")
        data_vars["photon_bins"] = {
            "dims": trace_dims,
            "kind": "trace_grid",
            "unit": "count",
            "value_column": "value",
            "backends": {},
        }
        if "csv" in backends:
            data_vars["photon_bins"]["backends"]["csv"] = "tables/traces/photon_bins.csv"
        if "zarr" in backends:
            data_vars["photon_bins"]["backends"]["zarr"] = "arrays.zarr:/traces/photon_bins"

    _write_json(
        run_path / "dataset_manifest.json",
        {"schema_version": 1, "backends": backends, "coords": manifest_coords, "data_vars": data_vars},
    )
    return run_path


def _make_coords(dims: dict[str, int], multichannel: bool) -> dict[str, np.ndarray]:
    coords: dict[str, np.ndarray] = {}
    if "mw_freq_hz" in dims:
        coords["mw_freq_hz"] = np.linspace(2.86e9, 2.88e9, dims["mw_freq_hz"])
    if "tau_s" in dims:
        coords["tau_s"] = np.linspace(0.0, 1e-6, dims["tau_s"])
    if "field_v" in dims:
        coords["field_v"] = np.linspace(-1.0, 1.0, dims["field_v"])
    if multichannel:
        coords["channel"] = np.arange(dims.get("channel", 2))
    if "time_s" in dims:
        coords["time_s"] = np.linspace(0.0, 1e-6, dims["time_s"])
    return coords


def _summary_values(coords: dict[str, np.ndarray], slow_dims: tuple[str, ...]) -> np.ndarray:
    values = np.zeros(tuple(len(coords[dim]) for dim in slow_dims), dtype=float)
    for index in np.ndindex(values.shape):
        values[index] = 1000.0 + sum((axis + 1) * item for axis, item in enumerate(index))
    return values


def _trace_values(coords: dict[str, np.ndarray], slow_dims: tuple[str, ...], multichannel: bool) -> np.ndarray:
    dims = list(slow_dims)
    if multichannel:
        dims.append("channel")
    dims.append("time_s")
    values = np.zeros(tuple(len(coords[dim]) for dim in dims), dtype=float)
    for index in np.ndindex(values.shape):
        slow_part = index[: len(slow_dims)]
        channel_offset = index[len(slow_dims)] * 100 if multichannel else 0
        time_index = index[-1]
        values[index] = sum((axis + 1) * item for axis, item in enumerate(slow_part)) + channel_offset + time_index
    return values


def _write_csv_backend(
    run_path: Path,
    coords: dict[str, np.ndarray],
    slow_dims: tuple[str, ...],
    summary: np.ndarray,
    trace: np.ndarray | None,
    multichannel: bool,
) -> None:
    for dim, values in coords.items():
        _write_rows(run_path / "tables" / "coords" / f"{dim}.csv", [dim], [{dim: value} for value in values])
    summary_rows = []
    for index in np.ndindex(summary.shape):
        row = {dim: coords[dim][item] for dim, item in zip(slow_dims, index)}
        row["value"] = summary[index]
        summary_rows.append(row)
    _write_rows(run_path / "tables" / "summaries" / "counts_mean.csv", [*slow_dims, "value"], summary_rows)
    if trace is not None:
        trace_dims = list(slow_dims)
        if multichannel:
            trace_dims.append("channel")
        trace_dims.append("time_s")
        trace_rows = []
        for index in np.ndindex(trace.shape):
            row = {dim: coords[dim][item] for dim, item in zip(trace_dims, index)}
            row["value"] = trace[index]
            trace_rows.append(row)
        _write_rows(run_path / "tables" / "traces" / "photon_bins.csv", [*trace_dims, "value"], trace_rows)
    _write_rows(run_path / "tables" / "data_keys.csv", ["key", "kind"], [{"key": "counts_mean", "kind": "scalar_grid"}])
    _write_rows(run_path / "tables" / "points.csv", ["point_id", *slow_dims], [])


def _write_zarr_backend(
    run_path: Path,
    coords: dict[str, np.ndarray],
    slow_dims: tuple[str, ...],
    summary: np.ndarray,
    trace: np.ndarray | None,
    multichannel: bool,
) -> None:
    import zarr  # type: ignore

    root = zarr.open_group(str(run_path / "arrays.zarr"), mode="w")
    for dim, values in coords.items():
        _zarr_write(root, f"coords/{dim}", values)
    _zarr_write(root, "summaries/counts_mean", summary)
    if trace is not None:
        _zarr_write(root, "traces/photon_bins", trace)


def _zarr_write(root: Any, key: str, values: np.ndarray) -> None:
    if hasattr(root, "create_array"):
        root.create_array(key, data=values, overwrite=True)
    else:
        root.create_dataset(key, data=values, overwrite=True)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _unit_for(dim: str) -> str | None:
    return {"mw_freq_hz": "Hz", "tau_s": "s", "time_s": "s", "field_v": "V"}.get(dim)
