"""Live plot selection rules independent of Qt and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .live_data_catalog import LiveDataCatalog, LivePointBuffer


@dataclass
class LivePlotSelection:
    keys: tuple[str, ...] = ()
    plot_type: str = "auto"
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
        self._defaults_initialized = False

    def initialize_defaults(self) -> None:
        if self._defaults_initialized:
            return
        self._defaults_initialized = True
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
        requested = (plot_type or "auto").lower()
        inferred = _plot_type(specs[0] if specs else None) if requested == "auto" else requested
        dims = specs[0].dims if specs else ()
        scan_dims = tuple(dim for dim in dims if dim not in {"time_s", "sample_index", "channel"})
        x_dim = x_dim or (scan_dims[0] if scan_dims else None)
        y_dim = y_dim or (scan_dims[1] if inferred == "heatmap" and len(scan_dims) > 1 else None)
        self.selection = LivePlotSelection(keys, inferred, x_dim, y_dim, dict(selectors or {}), point_id, channel)
        return self.selection

    def selector_dims(self) -> tuple[str, ...]:
        if not self.selection.keys:
            return ()
        dims = self.catalog.get(self.selection.keys[0]).dims
        displayed = {self.selection.x_dim, "time_s", "sample_index"}
        if self.selection.plot_type == "heatmap": displayed.add(self.selection.y_dim)
        return tuple(dim for dim in dims if dim not in displayed and dim != "channel")

    def get_plot_data(self, selection: LivePlotSelection | None = None):
        selected = selection or self.selection
        if not selected.keys:
            return None
        if selected.plot_type == "line":
            return tuple(self.buffer.line(key, selected.x_dim, dict(selected.selectors)) for key in selected.keys)
        if selected.plot_type == "heatmap":
            if len(selected.keys) != 1 or selected.x_dim is None or selected.y_dim is None:
                raise ValueError("heatmap requires one key and x/y dimensions")
            return self.buffer.heatmap(selected.keys[0], selected.x_dim, selected.y_dim, dict(selected.selectors))
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
    scan_dims = [dim for dim in spec.dims if dim not in {"time_s", "sample_index", "channel"}]
    return "heatmap" if len(scan_dims) >= 2 else "line"
