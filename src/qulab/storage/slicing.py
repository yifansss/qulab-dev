"""Slice advanced datasets into viewer-ready line, heatmap, and trace data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dataset_model import DatasetModel


@dataclass(frozen=True)
class LineData:
    key: str
    x_dim: str
    x: np.ndarray
    y: np.ndarray
    unit: str | None = None


@dataclass(frozen=True)
class HeatmapData:
    key: str
    x_dim: str
    y_dim: str
    x: np.ndarray
    y: np.ndarray
    values: np.ndarray
    unit: str | None = None


@dataclass(frozen=True)
class TraceData:
    key: str
    time_dim: str
    time: np.ndarray
    values: np.ndarray
    unit: str | None = None
    point_coords: dict[str, Any] | None = None
    point_status: str | None = None


class SliceController:
    """Map user dimension choices to backend selections."""

    def __init__(self, model: DatasetModel) -> None:
        self.model = model

    def slice_1d(self, data_key: str, x_dim: str, selectors: dict[str, Any] | None = None) -> LineData:
        selectors = dict(selectors or {})
        data = self.model.get_data_var_metadata(data_key)
        self._validate_dims(data_key, data.dims, (x_dim,))
        selection = self._selection_for(data.dims, keep=(x_dim,), selectors=selectors)
        sliced = self.model.get_data_var(data_key, selection=selection)
        axis = sliced.dims.index(x_dim)
        values = np.asarray(sliced.values)
        if axis != 0:
            values = np.moveaxis(values, axis, 0)
        return LineData(data_key, x_dim, sliced.coords[x_dim], np.asarray(values).reshape(len(sliced.coords[x_dim])), data.unit)

    def profile(self, data_key: str, profile_dim: str, selectors: dict[str, Any] | None = None) -> LineData:
        """Extract an arbitrary one-dimensional profile through an N-D scalar dataset."""

        return self.slice_1d(data_key, profile_dim, selectors=selectors)

    def slice_2d(
        self, data_key: str, x_dim: str, y_dim: str, selectors: dict[str, Any] | None = None
    ) -> HeatmapData:
        selectors = dict(selectors or {})
        data = self.model.get_data_var_metadata(data_key)
        self._validate_dims(data_key, data.dims, (x_dim, y_dim))
        selection = self._selection_for(data.dims, keep=(x_dim, y_dim), selectors=selectors)
        sliced = self.model.get_data_var(data_key, selection=selection)
        x_axis = sliced.dims.index(x_dim)
        y_axis = sliced.dims.index(y_dim)
        values = np.moveaxis(np.asarray(sliced.values), (x_axis, y_axis), (1, 0))
        return HeatmapData(
            data_key,
            x_dim,
            y_dim,
            sliced.coords[x_dim],
            sliced.coords[y_dim],
            values.reshape(len(sliced.coords[y_dim]), len(sliced.coords[x_dim])),
            data.unit,
        )

    def get_point_trace(
        self, data_key: str, point_selectors: dict[str, Any], channel: Any | None = None, time_dim: str = "time_s"
    ) -> TraceData:
        selectors = dict(point_selectors)
        if channel is not None:
            selectors["channel"] = channel
        data = self.model.get_data_var_metadata(data_key)
        if time_dim not in data.dims:
            raise ValueError(f"{data_key!r} does not contain trace dimension {time_dim!r}")
        selection = self._selection_for(data.dims, keep=(time_dim,), selectors=selectors)
        sliced = self.model.get_data_var(data_key, selection=selection)
        point_coords = {dim: selectors[dim] for dim in data.dims if dim not in {time_dim, "channel"} and dim in selectors}
        point_status = self.model.reader.get_point_status(point_coords)
        return TraceData(
            data_key,
            time_dim,
            sliced.coords[time_dim],
            np.asarray(sliced.values).reshape(-1),
            data.unit,
            point_coords=point_coords,
            point_status=point_status,
        )

    def selector_dims(self, data_key: str, displayed_dims: tuple[str, ...]) -> tuple[str, ...]:
        """Return dimensions that should be controlled by selectors for a display mode."""

        data = self.model.get_data_var_metadata(data_key)
        self._validate_dims(data_key, data.dims, displayed_dims)
        return tuple(dim for dim in data.dims if dim not in set(displayed_dims))

    def _selection_for(
        self, dims: tuple[str, ...], keep: tuple[str, ...], selectors: dict[str, Any]
    ) -> dict[str, Any]:
        selection: dict[str, Any] = {}
        missing = [dim for dim in dims if dim not in keep and dim not in selectors]
        if missing:
            raise ValueError(f"selectors required for non-displayed dimensions: {', '.join(missing)}")
        for dim in dims:
            if dim not in keep:
                selection[dim] = selectors[dim]
        return selection

    def _validate_dims(self, data_key: str, dims: tuple[str, ...], requested: tuple[str, ...]) -> None:
        missing = [dim for dim in requested if dim not in dims]
        if missing:
            raise ValueError(f"{data_key!r} does not contain dimension(s): {', '.join(missing)}")
