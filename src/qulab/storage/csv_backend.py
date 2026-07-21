"""CSV implementation of the advanced storage backend."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .array_backend import DataArray


class CsvBackend:
    """Read Qulab advanced arrays stored as long-form CSV tables."""

    name = "csv"

    def __init__(self, run_path: Path | str, manifest: dict[str, Any]) -> None:
        self.run_path = Path(run_path)
        self.manifest = manifest

    def list_arrays(self) -> list[str]:
        return sorted(
            key for key, spec in self.manifest.get("data_vars", {}).items() if self._csv_path(spec) is not None
        )

    def read_array(self, key: str, selection: dict[str, Any] | None = None) -> DataArray:
        spec = self._data_spec(key)
        path = self._csv_path(spec)
        if path is None:
            raise KeyError(f"data variable {key!r} has no CSV backend entry")
        rows = _read_csv(path)
        dims = tuple(spec.get("dims", []))
        value_column = spec.get("value_column", "value")
        coords = self._coords_from_manifest_and_rows(dims, rows)
        shape = tuple(len(coords[dim]) for dim in dims)
        values = np.full(shape, np.nan, dtype=float)
        coord_indexes = {dim: {value: index for index, value in enumerate(coords[dim].tolist())} for dim in dims}

        for row in rows:
            try:
                index = tuple(coord_indexes[dim][_parse_cell(row[dim])] for dim in dims)
            except KeyError as exc:
                raise ValueError(f"CSV row for {key!r} is missing dimension column {exc.args[0]!r}") from exc
            values[index] = float(row[value_column])

        data = DataArray(
            key=key,
            dims=dims,
            coords=coords,
            values=values,
            kind=spec.get("kind", "array"),
            unit=spec.get("unit"),
            attrs={"backend": self.name, **spec},
        )
        return _select_data_array(data, selection)

    def _data_spec(self, key: str) -> dict[str, Any]:
        try:
            spec = self.manifest["data_vars"][key]
        except KeyError as exc:
            raise KeyError(f"unknown data variable {key!r}") from exc
        return spec

    def _csv_path(self, spec: dict[str, Any]) -> Path | None:
        backend_entry = spec.get("backends", {}).get("csv")
        if backend_entry is None and str(spec.get("uri", "")).endswith(".csv"):
            backend_entry = spec.get("uri")
        if backend_entry is None:
            return None
        return self.run_path / str(backend_entry)

    def _coords_from_manifest_and_rows(self, dims: tuple[str, ...], rows: list[dict[str, str]]) -> dict[str, np.ndarray]:
        coords: dict[str, np.ndarray] = {}
        manifest_coords = self.manifest.get("coords", {})
        for dim in dims:
            coord_entry = manifest_coords.get(dim, {})
            csv_entry = coord_entry.get("backends", {}).get("csv")
            if rows and all(dim in row for row in rows):
                coords[dim] = np.array(_unique_in_order(_parse_cell(row[dim]) for row in rows))
            elif csv_entry:
                coord_rows = _read_csv(self.run_path / str(csv_entry))
                column = coord_entry.get("column", dim)
                coords[dim] = np.array([_parse_cell(row[column]) for row in coord_rows])
            else:
                coords[dim] = np.array(_unique_in_order(_parse_cell(row[dim]) for row in rows))
        return coords


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _parse_cell(value: str) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _unique_in_order(values: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _select_data_array(data: DataArray, selection: dict[str, Any] | None) -> DataArray:
    if not selection:
        return data
    slices: list[Any] = []
    dims: list[str] = []
    coords: dict[str, np.ndarray] = {}
    for dim in data.dims:
        if dim not in selection:
            slices.append(slice(None))
            dims.append(dim)
            coords[dim] = data.coords[dim]
            continue
        selector = selection[dim]
        index = _selector_to_index(data.coords[dim], selector)
        slices.append(index)
        if isinstance(index, slice):
            dims.append(dim)
            coords[dim] = data.coords[dim][index]
    values = data.values[tuple(slices)]
    return DataArray(
        key=data.key,
        dims=tuple(dims),
        coords=coords,
        values=np.asarray(values),
        kind=data.kind,
        unit=data.unit,
        attrs=data.attrs,
    )


def _selector_to_index(coord: np.ndarray, selector: Any) -> int | slice:
    if isinstance(selector, slice):
        return selector
    if isinstance(selector, int):
        return selector
    matches = np.where(coord == selector)[0]
    if len(matches) == 0:
        try:
            numeric = float(selector)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None:
            matches = np.where(coord == numeric)[0]
    if len(matches) == 0:
        raise KeyError(f"selector {selector!r} not found in coordinate")
    return int(matches[0])
