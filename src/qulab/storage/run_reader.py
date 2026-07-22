"""Read Qulab run folders through JSONL, CSV, and optional Zarr backends."""

from __future__ import annotations

import json
import csv
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .array_backend import DataArray, OptionalDependencyError
from .csv_backend import CsvBackend
from .zarr_backend import ZarrBackend

BackendPreference = Literal["auto", "csv", "zarr"]


class RunReader:
    """Open a run folder and expose logical dataset variables."""

    def __init__(self, run_path: Path | str, backend: BackendPreference = "auto") -> None:
        self.run_path = Path(run_path)
        self.backend_preference = backend
        self.metadata = self._read_json("metadata.json", default={})
        self.manifest = self._read_json("dataset_manifest.json", default=None)
        self.backend_name = self._select_backend(backend)
        self.backend = self._open_backend(self.backend_name) if self.backend_name is not None else None

    def list_data_groups(self) -> list[str]:
        groups = ["raw"]
        if self.manifest and any(spec.get("source_kind") == "derived" for spec in self.manifest.get("data_vars", {}).values()):
            groups.append("live")
        analysis = self.run_path / "analysis"
        if analysis.exists():
            groups.extend(f"analysis:{path.name}" for path in sorted(analysis.iterdir())
                          if path.is_dir() and not path.name.startswith(".tmp_") and (path / "metadata.json").exists())
        return groups

    def list_data_keys(self, group: str | None = None) -> list[str]:
        if group and group.startswith("analysis:"):
            return self._analysis_reader(group).list_data_keys()
        if self.manifest:
            keys = sorted(self.manifest.get("data_vars", {}).keys()) if self.backend is None else self.backend.list_arrays()
            if group in {"raw", "live"}:
                wanted = "raw" if group == "raw" else "derived"
                keys = [key for key in keys if self.manifest.get("data_vars", {}).get(key, {}).get("source_kind", "raw") == wanted]
            return keys
        metadata_keys = self.metadata.get("data_keys", [])
        keys = [item for item in metadata_keys if isinstance(item, dict) and "key" in item]
        if group in {"raw", "live"}:
            wanted = "raw" if group == "raw" else "derived"
            keys = [item for item in keys if item.get("source_kind", "raw") == wanted]
        return sorted(item["key"] for item in keys)

    def get_coords(self) -> dict[str, np.ndarray]:
        if not self.manifest:
            return {}
        return self._read_manifest_coords(tuple(self.manifest.get("coords", {}).keys()))

    def get_data_var_metadata(self, key: str, group: str | None = None) -> DataArray:
        """Return dims, coords, kind, and unit without loading the data variable."""

        if group and group.startswith("analysis:"):
            return self._analysis_reader(group).get_data_var_metadata(key)
        self._validate_group_key(key, group)
        if not self.manifest:
            data = self.get_data_var(key, group=group)
            return DataArray(data.key, data.dims, data.coords, np.asarray([]), data.kind, data.unit, data.attrs)
        try:
            spec = self.manifest["data_vars"][key]
        except KeyError as exc:
            raise KeyError(f"unknown data variable {key!r}") from exc
        dims = tuple(spec.get("dims", []))
        return DataArray(
            key=key,
            dims=dims,
            coords=self._read_manifest_coords(dims),
            values=np.asarray([]),
            kind=spec.get("kind", "array"),
            unit=spec.get("unit"),
            attrs={"backend": self.backend_name, **spec},
        )

    def get_data_var(self, key: str, selection: dict[str, Any] | None = None, group: str | None = None) -> DataArray:
        if group and group.startswith("analysis:"):
            return self._analysis_reader(group).get_data_var(key, selection=selection)
        self._validate_group_key(key, group)
        if self.backend is not None:
            return self.backend.read_array(key, selection=selection)
        return self._read_jsonl_data_var(key)

    def iter_compute_points(self, input_keys: list[str] | tuple[str, ...], *, include_status: tuple[str, ...] = ("ok",)):
        """Reconstruct one raw ComputePoint per measurement point from public run records."""
        from qulab.analysis import ComputePoint
        requested: dict[str, tuple[str, str]] = {}
        for selector in input_keys:
            if selector.startswith("live:"):
                requested[selector] = (selector[5:], "derived_data")
            elif selector.startswith("analysis:"):
                raise ValueError("analysis result inputs require explicit group reading and are not raw point inputs")
            else:
                requested[selector] = (selector, "data_point")
        statuses: dict[str, str] = {}
        points_path = self.run_path / "points.jsonl"
        if points_path.exists():
            for line in points_path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line); statuses[str(row.get("point_id"))] = str(row.get("status"))
        points: OrderedDict[str, dict[str, Any]] = OrderedDict()
        data_path = self.run_path / "data.jsonl"
        if not data_path.exists(): return
        with data_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line); point_id = row.get("point_id")
                if not point_id: continue
                record = points.setdefault(point_id, {"coords": row.get("coords", {}), "data": {}, "metadata": {}, "timestamp": row.get("time", "")})
                if record["coords"] != row.get("coords", {}):
                    raise ValueError(f"coordinate mismatch while reconstructing point {point_id}")
                for exposed, (key, kind) in requested.items():
                    if row.get("kind") == kind and key in row.get("data", {}):
                        record["data"][exposed] = row["data"][key]
                record["metadata"].update(row.get("metadata", {})); record["timestamp"] = row.get("time", record["timestamp"])
        for point_id, record in points.items():
            if statuses.get(point_id, "ok") not in include_status: continue
            yield ComputePoint(point_id, record["coords"], record["data"], record["metadata"], record["timestamp"])

    def _analysis_reader(self, group: str) -> "RunReader":
        result_id = group.split(":", 1)[1]
        if not result_id or "/" in result_id or "\\" in result_id:
            raise KeyError(f"invalid analysis group: {group}")
        path = self.run_path / "analysis" / result_id
        if not (path / "metadata.json").exists():
            raise KeyError(f"unknown analysis group: {group}")
        return RunReader(path, backend=self.backend_preference)

    def _validate_group_key(self, key: str, group: str | None) -> None:
        if group not in {"raw", "live"}: return
        if key not in self.list_data_keys(group=group):
            raise KeyError(f"data variable {key!r} is unavailable in group {group!r}")

    def get_trace(self, point_selection: dict[str, Any], key: str = "photon_bins", channel: Any | None = None) -> DataArray:
        selection = dict(point_selection)
        if channel is not None:
            selection["channel"] = channel
        return self.get_data_var(key, selection=selection)

    def get_point_status(self, point_selection: dict[str, Any]) -> str | None:
        """Return point lifecycle status for exact coordinate selectors when available."""

        csv_status = self._get_point_status_from_csv(point_selection)
        if csv_status is not None:
            return csv_status
        return self._get_point_status_from_jsonl(point_selection)

    def _read_json(self, name: str, default: Any) -> Any:
        path = self.run_path / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_manifest_coords(self, dims: tuple[str, ...]) -> dict[str, np.ndarray]:
        if not self.manifest:
            return {}
        coords: dict[str, np.ndarray] = {}
        coord_specs = self.manifest.get("coords", {})
        for dim in dims:
            coord_spec = coord_specs.get(dim, {})
            if self.backend_name == "zarr" and self.backend is not None and hasattr(self.backend, "root"):
                coords[dim] = np.asarray(self.backend.root[f"coords/{dim}"][:])
                continue
            csv_entry = coord_spec.get("backends", {}).get("csv")
            if csv_entry:
                path = self.run_path / str(csv_entry)
                with path.open("r", encoding="utf-8", newline="") as file:
                    rows = csv.DictReader(file)
                    column = coord_spec.get("column", dim)
                    coords[dim] = np.asarray([_parse_coord_cell(row[column]) for row in rows])
        return coords

    def _select_backend(self, preference: BackendPreference) -> str | None:
        if not self.manifest:
            if preference == "zarr":
                raise OptionalDependencyError("Run has no dataset_manifest.json with a Zarr backend")
            if preference == "csv":
                raise OptionalDependencyError("Run has no dataset_manifest.json with a CSV backend")
            return None
        backends = self.manifest.get("backends", {})
        available_backends = set(self.manifest.get("available_backends", [])) or set(backends)
        if preference == "csv":
            if "csv" not in available_backends:
                raise OptionalDependencyError("Run manifest does not declare a CSV backend")
            return "csv"
        if preference == "zarr":
            if "zarr" not in available_backends:
                raise OptionalDependencyError("Run manifest does not declare a Zarr backend")
            if not ZarrBackend.available():
                raise OptionalDependencyError("Zarr backend was requested but the optional 'zarr' package is unavailable")
            return "zarr"
        preferred = self.manifest.get("preferred_backend")
        if preferred == "zarr" and "zarr" in available_backends and ZarrBackend.available():
            return "zarr"
        if "zarr" in available_backends and ZarrBackend.available():
            return "zarr"
        if "csv" in available_backends:
            return "csv"
        return None

    def _open_backend(self, name: str) -> CsvBackend | ZarrBackend:
        if name == "csv":
            assert self.manifest is not None
            return CsvBackend(self.run_path, self.manifest)
        if name == "zarr":
            assert self.manifest is not None
            return ZarrBackend(self.run_path, self.manifest)
        raise ValueError(f"unknown backend {name!r}")

    def _read_jsonl_data_var(self, key: str) -> DataArray:
        path = self.run_path / "data.jsonl"
        if not path.exists():
            raise KeyError(f"data variable {key!r} is unavailable")
        xs: list[float] = []
        values: list[float] = []
        coord_name = "index"
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            record = json.loads(line)
            if key not in record.get("data", {}):
                continue
            coords = record.get("coords", {})
            if coords:
                coord_name = next(iter(coords))
                xs.append(float(coords[coord_name]))
            else:
                xs.append(float(index))
            numeric = _find_numeric_scalar(record["data"][key])
            if numeric is None:
                continue
            values.append(numeric)
        if not values:
            raise KeyError(f"data variable {key!r} is unavailable")
        return DataArray(
            key=key,
            dims=(coord_name,),
            coords={coord_name: np.asarray(xs, dtype=float)},
            values=np.asarray(values, dtype=float),
            kind="scalar_grid",
        )

    def _get_point_status_from_csv(self, point_selection: dict[str, Any]) -> str | None:
        path = self.run_path / "tables" / "points.csv"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                if _row_matches_selectors(row, point_selection):
                    return row.get("status") or None
        return None

    def _get_point_status_from_jsonl(self, point_selection: dict[str, Any]) -> str | None:
        path = self.run_path / "points.jsonl"
        if not path.exists():
            return None
        status = None
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if _coords_match_selectors(record.get("coords", {}), point_selection):
                status = record.get("status")
        return status


def _parse_coord_cell(value: str) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _row_matches_selectors(row: dict[str, str], selectors: dict[str, Any]) -> bool:
    return all(name in row and _values_equal(_parse_coord_cell(row[name]), value) for name, value in selectors.items())


def _coords_match_selectors(coords: dict[str, Any], selectors: dict[str, Any]) -> bool:
    return all(name in coords and _values_equal(coords[name], value) for name, value in selectors.items())


def _values_equal(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return left == right


def _find_numeric_scalar(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for preferred in ("counts_mean", "mean", "value"):
            if preferred in value:
                found = _find_numeric_scalar(value[preferred])
                if found is not None:
                    return found
        for item in value.values():
            found = _find_numeric_scalar(item)
            if found is not None:
                return found
    return None
