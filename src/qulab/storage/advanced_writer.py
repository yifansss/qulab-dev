"""Writers for optional CSV and Zarr dataset backends."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .array_backend import OptionalDependencyError
from .dataset import infer_data_spec
from .events import to_jsonable
from .manifest import DatasetManifest


class AdvancedDatasetWriter:
    """Collect point data and materialize CSV/Zarr backends on close."""

    def __init__(self, run_path: Path, backends: list[str]) -> None:
        self.run_path = run_path
        self.backends = backends
        self.records: list[dict[str, Any]] = []
        self.points: dict[str, dict[str, Any]] = {}

    def open(self) -> None:
        if "zarr" in self.backends:
            try:
                import zarr  # noqa: F401
            except ImportError as exc:
                raise OptionalDependencyError("Zarr backend requires the optional 'zarr' package") from exc

    def add_point_started(self, point_id: str, coords: dict[str, Any], started_at: str) -> None:
        self.points[point_id] = {
            "point_id": point_id,
            "status": "running",
            "coords": to_jsonable(coords),
            "started_at": started_at,
            "completed_at": None,
        }

    def add_point_completed(self, point_id: str, status: str, coords: dict[str, Any], completed_at: str) -> None:
        point = self.points.setdefault(
            point_id,
            {"point_id": point_id, "status": "running", "coords": to_jsonable(coords), "started_at": None},
        )
        point["status"] = status
        point["coords"] = to_jsonable(coords)
        point["completed_at"] = completed_at

    def add_data_point(self, payload: dict[str, Any]) -> None:
        self.records.append(payload)

    def close(self) -> None:
        if not self.backends:
            return
        logical = _build_logical_dataset(self.records)
        manifest = _build_manifest(logical, self.backends)
        if "csv" in self.backends:
            _write_csv_backend(self.run_path, logical, self.points)
        if "zarr" in self.backends:
            _write_zarr_backend(self.run_path, logical)
        manifest.write(self.run_path / "dataset_manifest.json")


def _build_logical_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    coord_values: dict[str, list[Any]] = {}
    variables: dict[str, dict[str, Any]] = {}
    for record in records:
        coords = dict(record.get("coords", {}))
        for name, value in coords.items():
            _append_unique(coord_values.setdefault(name, []), value)
        for key, value in _flatten_data_vars(record.get("data", {})).items():
            spec = infer_data_spec(value)
            if spec["kind"] == "object":
                continue
            var = variables.setdefault(
                key,
                {
                    "key": key,
                    "kind": _manifest_kind(spec["kind"]),
                    "unit": spec.get("unit"),
                    "scan_dims": tuple(coords.keys()),
                    "records": [],
                    "shape": spec.get("shape"),
                    "source_kind": record.get("source_kind", "raw"),
                    "analysis_mode": record.get("analysis_mode"),
                    "source_module": record.get("source_module"),
                    "module_version": record.get("module_version"),
                    "input_keys": record.get("input_keys", []),
                    "result_id": record.get("result_id"),
                    "input_lineage": next(iter(record.get("data_specs", {}).values()), {}).get("input_lineage", []),
                },
            )
            var["records"].append({"point_id": record.get("point_id"), "coords": coords, "value": value})
            var["shape"] = spec.get("shape")
            var["kind"] = _manifest_kind(spec["kind"])

    for var in variables.values():
        if var["kind"] == "trace_grid":
            if len(var.get("shape") or []) == 2:
                for channel in range(int(var["shape"][0])):
                    _append_unique(coord_values.setdefault("channel", []), channel)
                for time in range(int(var["shape"][1])):
                    _append_unique(coord_values.setdefault("time_s", []), float(time))
                var["extra_dims"] = ("channel", "time_s")
            else:
                length = int((var.get("shape") or [0])[0] or 0)
                for time in range(length):
                    _append_unique(coord_values.setdefault("time_s", []), float(time))
                var["extra_dims"] = ("time_s",)
        else:
            var["extra_dims"] = ()

    return {"coords": coord_values, "data_vars": variables}


def _build_manifest(logical: dict[str, Any], backends: list[str]) -> DatasetManifest:
    manifest_coords = {
        name: {
            "unit": _coord_unit(name),
            "column": name,
            "backends": {"csv": f"tables/coords/{name}.csv"} if "csv" in backends else {},
        }
        for name in logical["coords"]
    }
    data_vars: dict[str, dict[str, Any]] = {}
    for key, var in logical["data_vars"].items():
        dims = list(var["scan_dims"]) + list(var.get("extra_dims", ()))
        entry = {
            "kind": var["kind"],
            "dims": dims,
            "unit": var.get("unit"),
            "value_column": "value",
            "backends": {},
            "source_kind": var.get("source_kind", "raw"),
        }
        for name in ("analysis_mode", "source_module", "module_version", "input_keys", "result_id", "input_lineage"):
            if var.get(name) is not None:
                entry[name] = var[name]
        if "csv" in backends:
            group = "summaries" if var["kind"] == "scalar_grid" else "traces"
            entry["backends"]["csv"] = f"tables/{group}/{key}.csv"
        if "zarr" in backends:
            group = "summaries" if var["kind"] == "scalar_grid" else "traces"
            entry["backends"]["zarr"] = f"arrays.zarr:/{group}/{key}"
        data_vars[key] = entry
    preferred = "zarr" if "zarr" in backends else ("csv" if "csv" in backends else None)
    return DatasetManifest(preferred_backend=preferred, available_backends=backends, coords=manifest_coords, data_vars=data_vars)


def _write_csv_backend(run_path: Path, logical: dict[str, Any], points: dict[str, dict[str, Any]]) -> None:
    for dim, values in logical["coords"].items():
        _write_rows(run_path / "tables" / "coords" / f"{dim}.csv", [dim], [{dim: value} for value in values])
    _write_points_csv(run_path, points, logical["coords"])
    _write_rows(
        run_path / "tables" / "data_keys.csv",
        ["key", "kind", "unit"],
        [
            {"key": key, "kind": var["kind"], "unit": var.get("unit")}
            for key, var in sorted(logical["data_vars"].items())
        ],
    )
    for key, var in logical["data_vars"].items():
        if var["kind"] == "scalar_grid":
            rows = _scalar_rows(key, var)
            fields = ["point_id", *var["scan_dims"], "key", "value", "unit"]
            _write_rows(run_path / "tables" / "summaries" / f"{key}.csv", fields, rows)
        else:
            rows = _trace_rows(key, var)
            fields = ["point_id", *var["scan_dims"], *var["extra_dims"], "key", "value", "unit"]
            _write_rows(run_path / "tables" / "traces" / f"{key}.csv", fields, rows)


def _write_zarr_backend(run_path: Path, logical: dict[str, Any]) -> None:
    try:
        import zarr  # type: ignore
    except ImportError as exc:
        raise OptionalDependencyError("Zarr backend requires the optional 'zarr' package") from exc

    root = zarr.open_group(str(run_path / "arrays.zarr"), mode="w")
    for dim, values in logical["coords"].items():
        _zarr_write(root, f"coords/{dim}", np.asarray(values))
    for key, var in logical["data_vars"].items():
        dims = tuple(var["scan_dims"]) + tuple(var.get("extra_dims", ()))
        coords = logical["coords"]
        values = np.full(tuple(len(coords[dim]) for dim in dims), np.nan, dtype=float)
        indexes = {dim: {value: index for index, value in enumerate(coords[dim])} for dim in dims}
        for row in _scalar_rows(key, var) if var["kind"] == "scalar_grid" else _trace_rows(key, var):
            index = tuple(indexes[dim][row[dim]] for dim in dims)
            values[index] = float(row["value"])
        group = "summaries" if var["kind"] == "scalar_grid" else "traces"
        _zarr_write(root, f"{group}/{key}", values)


def _write_points_csv(run_path: Path, points: dict[str, dict[str, Any]], coord_values: dict[str, list[Any]]) -> None:
    coord_fields = [dim for dim in coord_values if dim not in {"time_s", "channel"}]
    fields = ["point_id", "status", *coord_fields, "started_at", "completed_at"]
    rows = []
    for point in points.values():
        coords = point.get("coords", {})
        rows.append(
            {
                "point_id": point.get("point_id"),
                "status": point.get("status"),
                **{dim: coords.get(dim) for dim in coord_fields},
                "started_at": point.get("started_at"),
                "completed_at": point.get("completed_at"),
            }
        )
    _write_rows(run_path / "tables" / "points.csv", fields, rows)


def _scalar_rows(key: str, var: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for record in var["records"]:
        row = {
            "point_id": record.get("point_id"),
            **record["coords"],
            "key": key,
            "value": record["value"],
            "unit": var.get("unit"),
        }
        rows.append(row)
    return rows


def _trace_rows(key: str, var: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for record in var["records"]:
        value = to_jsonable(record["value"])
        if "channel" in var["extra_dims"]:
            for channel, trace in enumerate(value):
                for time_index, item in enumerate(trace):
                    rows.append(
                        {
                            "point_id": record.get("point_id"),
                            **record["coords"],
                            "channel": channel,
                            "time_s": float(time_index),
                            "key": key,
                            "value": item,
                            "unit": var.get("unit"),
                        }
                    )
        else:
            for time_index, item in enumerate(value):
                rows.append(
                    {
                        "point_id": record.get("point_id"),
                        **record["coords"],
                        "time_s": float(time_index),
                        "key": key,
                        "value": item,
                        "unit": var.get("unit"),
                    }
                )
    return rows


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _zarr_write(root: Any, key: str, values: np.ndarray) -> None:
    if hasattr(root, "create_array"):
        root.create_array(key, data=values, overwrite=True)
    else:
        root.create_dataset(key, data=values, overwrite=True)


def _append_unique(values: list[Any], value: Any) -> None:
    value = to_jsonable(value)
    if value not in values:
        values.append(value)


def _manifest_kind(kind: str) -> str:
    return "scalar_grid" if kind == "scalar" else "trace_grid" if kind in {"vector", "matrix"} else "metadata"


def _coord_unit(name: str) -> str | None:
    return {"mw_freq_hz": "Hz", "freq_hz": "Hz", "tau_s": "s", "time_s": "s", "field_v": "V"}.get(name)


def _flatten_data_vars(data: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        jsonable = to_jsonable(value)
        if isinstance(jsonable, dict):
            for nested_key, nested_value in jsonable.items():
                if nested_key not in flattened:
                    flattened[nested_key] = nested_value
                else:
                    flattened[f"{key}.{nested_key}"] = nested_value
        else:
            flattened[key] = jsonable
    return flattened
