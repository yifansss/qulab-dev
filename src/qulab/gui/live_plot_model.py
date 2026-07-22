"""Live plot selection rules independent of Qt and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .live_data_catalog import LiveDataCatalog, LivePointBuffer


@dataclass
class LivePlotSelection:
    keys: tuple[str, ...] = ()
    plot_type: str = "line"
    x_dim: str | None = None
    y_dim: str | None = None
    selectors: Mapping[str, Any] = field(default_factory=dict)
    point_id: str | None = None
    channel: Any | None = None


class LivePlotModel:
    def __init__(self, catalog: LiveDataCatalog, buffer: LivePointBuffer) -> None:
        self.catalog = catalog
        self.buffer = buffer
        self.selection = LivePlotSelection()

    def initialize_defaults(self) -> None:
        if self.selection.keys:
            return
        visible = [spec.key for spec in (*self.catalog.list_raw(), *self.catalog.list_derived()) if spec.visible_default]
        if visible:
            self.select(tuple(visible[:1]))

    def select(self, keys: tuple[str, ...], *, plot_type: str | None = None, x_dim: str | None = None,
               y_dim: str | None = None, selectors: Mapping[str, Any] | None = None,
               point_id: str | None = None, channel: Any | None = None) -> LivePlotSelection:
        specs = [self.catalog.get(key) for key in keys]
        if len(specs) > 1:
            if any(spec.data_kind != "scalar" for spec in specs):
                raise ValueError("only scalar keys can be overlaid")
            if any(spec.dims != specs[0].dims for spec in specs) or len({spec.unit for spec in specs}) > 1:
                raise ValueError("overlay keys require matching dimensions and units")
        inferred = plot_type or _plot_type(specs[0] if specs else None)
        dims = specs[0].dims if specs else ()
        scan_dims = tuple(dim for dim in dims if dim not in {"time_s", "channel"})
        x_dim = x_dim or (scan_dims[0] if scan_dims else None)
        y_dim = y_dim or (scan_dims[1] if inferred == "heatmap" and len(scan_dims) > 1 else None)
        self.selection = LivePlotSelection(keys, inferred, x_dim, y_dim, dict(selectors or {}), point_id, channel)
        return self.selection

    def selector_dims(self) -> tuple[str, ...]:
        if not self.selection.keys:
            return ()
        dims = self.catalog.get(self.selection.keys[0]).dims
        displayed = {self.selection.x_dim, self.selection.y_dim, "time_s" if self.selection.plot_type == "trace" else None}
        return tuple(dim for dim in dims if dim not in displayed and dim != "channel")

    def get_plot_data(self, selection: LivePlotSelection | None = None):
        selected = selection or self.selection
        if not selected.keys:
            return None
        if selected.plot_type == "line":
            if selected.x_dim is None:
                raise ValueError("line plot requires x_dim")
            return tuple(self.buffer.line(key, selected.x_dim) for key in selected.keys)
        if selected.plot_type == "heatmap":
            if len(selected.keys) != 1 or selected.x_dim is None or selected.y_dim is None:
                raise ValueError("heatmap requires one key and x/y dimensions")
            return self.buffer.heatmap(selected.keys[0], selected.x_dim, selected.y_dim)
        if selected.plot_type == "trace":
            if len(selected.keys) != 1 or selected.point_id is None:
                raise ValueError("trace requires one key and point_id")
            return self.buffer.trace(selected.keys[0], selected.point_id, selected.channel)
        if selected.plot_type == "table":
            return self.buffer.points()
        raise ValueError(f"unsupported live plot type: {selected.plot_type}")


def _plot_type(spec) -> str:
    if spec is None:
        return "line"
    if spec.data_kind in {"vector", "matrix", "trace"}:
        return "trace"
    scan_dims = [dim for dim in spec.dims if dim not in {"time_s", "channel"}]
    return "heatmap" if len(scan_dims) >= 2 else "line"
