"""Qt-free live raw/derived catalog and bounded point buffer."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace
from numbers import Real
from typing import Any, Iterable

import numpy as np

from qulab.analysis import AnalysisExecutionPlan
from qulab.core import AnalysisStatus, DataPoint, DerivedData, Event
from qulab.storage.slicing import HeatmapData, LineData, TraceData


@dataclass(frozen=True)
class LiveDataKeySpec:
    key: str
    source_kind: str
    data_kind: str = "unknown"
    unit: str | None = None
    dims: tuple[str, ...] = ()
    source_module: str | None = None
    saved: bool = True
    visible_default: bool = False
    status: str = "declared"


class LiveDataCatalog:
    def __init__(self) -> None:
        self._specs: dict[str, LiveDataKeySpec] = {}
        self._module_outputs: dict[str, tuple[str, ...]] = {}

    def declare(self, spec: LiveDataKeySpec) -> None:
        existing = self._specs.get(spec.key)
        if existing is not None and existing.source_kind != spec.source_kind:
            self._specs[spec.key] = replace(existing, status="error")
            return
        self._specs[spec.key] = spec

    def declare_from_config(self, raw_keys: Iterable[str] = (), analysis_plan: AnalysisExecutionPlan | None = None,
                            coord_dims: Iterable[str] = ()) -> None:
        dims = tuple(coord_dims)
        for key in raw_keys:
            self.declare(LiveDataKeySpec(key, "raw", dims=dims, status="declared"))
        if analysis_plan:
            for module in analysis_plan.modules:
                self._module_outputs[module.instance_name] = module.effective_outputs
                for key in module.effective_outputs:
                    self.declare(LiveDataKeySpec(key, "derived", dims=dims,
                                                source_module=module.instance_name, saved=module.save,
                                                visible_default=module.show, status="waiting"))

    def handle_event(self, event: Event) -> None:
        if isinstance(event, DataPoint):
            self._activate(event.data, "raw", event.coords, {}, None, True, False)
        elif isinstance(event, DerivedData):
            self._activate(event.data, "derived", event.coords, event.units, event.source_module, event.save, event.show)
        elif isinstance(event, AnalysisStatus) and event.state in {"failed", "warning"}:
            for key in self._module_outputs.get(event.module, ()):
                spec = self._specs.get(key)
                if spec is not None and spec.status != "active":
                    self._specs[key] = replace(spec, status="error")

    def _activate(self, data: dict[str, Any], source: str, coords: dict[str, Any], units: dict[str, str | None],
                  module: str | None, saved: bool, visible: bool) -> None:
        for key, value in data.items():
            existing = self._specs.get(key)
            if existing is not None and existing.source_kind != source:
                self._specs[key] = replace(existing, status="error")
                continue
            kind, extra_dims = _kind_dims(value)
            dims = tuple(coords) + extra_dims
            self._specs[key] = LiveDataKeySpec(key, source, kind, units.get(key), dims, module, saved,
                                               existing.visible_default if existing else visible, "active")

    def list_raw(self) -> tuple[LiveDataKeySpec, ...]:
        return tuple(spec for spec in self._specs.values() if spec.source_kind == "raw")

    def list_derived(self) -> tuple[LiveDataKeySpec, ...]:
        return tuple(spec for spec in self._specs.values() if spec.source_kind == "derived")

    def get(self, key: str) -> LiveDataKeySpec:
        return self._specs[key]


class LivePointBuffer:
    def __init__(self, max_points: int = 1000) -> None:
        if max_points < 1:
            raise ValueError("max_points must be >= 1")
        self.max_points = max_points
        self._points: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def handle_event(self, event: Event) -> None:
        if not isinstance(event, (DataPoint, DerivedData)) or not event.point_id:
            return
        point = self._points.setdefault(event.point_id, {"point_id": event.point_id, "coords": deepcopy(event.coords), "data": {}})
        if point["coords"] != event.coords:
            point["error"] = "coordinate mismatch"
            return
        point["data"].update(deepcopy(event.data))
        self._points.move_to_end(event.point_id)
        while len(self._points) > self.max_points:
            self._points.popitem(last=False)

    def clear(self) -> None:
        self._points.clear()

    def points(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(point) for point in self._points.values())

    def line(self, key: str, x_dim: str) -> LineData:
        rows = [(point["coords"][x_dim], point["data"][key]) for point in self._points.values()
                if x_dim in point["coords"] and key in point["data"] and _number(point["data"][key])]
        return LineData(key, x_dim, np.asarray([row[0] for row in rows]), np.asarray([row[1] for row in rows], dtype=float))

    def heatmap(self, key: str, x_dim: str, y_dim: str) -> HeatmapData:
        rows = [(point["coords"][x_dim], point["coords"][y_dim], point["data"][key]) for point in self._points.values()
                if x_dim in point["coords"] and y_dim in point["coords"] and key in point["data"] and _number(point["data"][key])]
        xs = _unique(row[0] for row in rows); ys = _unique(row[1] for row in rows)
        values = np.full((len(ys), len(xs)), np.nan)
        xi = {value: index for index, value in enumerate(xs)}; yi = {value: index for index, value in enumerate(ys)}
        for x, y, value in rows:
            values[yi[y], xi[x]] = value
        return HeatmapData(key, x_dim, y_dim, np.asarray(xs), np.asarray(ys), values)

    def trace(self, key: str, point_id: str, channel: Any | None = None) -> TraceData:
        point = self._points[point_id]; value = deepcopy(point["data"][key])
        if channel is not None:
            value = value[int(channel)]
        array = np.asarray(value)
        if array.ndim != 1:
            raise ValueError("trace selection must resolve to one dimension")
        return TraceData(key, "time_s", np.arange(len(array), dtype=float), array, point_coords=deepcopy(point["coords"]))


def _kind_dims(value: Any) -> tuple[str, tuple[str, ...]]:
    if _number(value) or isinstance(value, (str, bool)) or value is None:
        return "scalar", ()
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(item, (list, tuple)) for item in value):
            return "matrix", ("channel", "time_s")
        return "vector", ("time_s",)
    return "unknown", ()


def _number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _unique(values):
    output = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
