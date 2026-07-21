"""Convenience helpers that produce plot-ready data from a run folder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qulab.storage import DatasetModel, RunReader, SliceController
from qulab.storage.run_reader import BackendPreference
from qulab.storage.slicing import HeatmapData, LineData, TraceData


def _controller(run_path: Path | str, backend: BackendPreference) -> SliceController:
    return SliceController(DatasetModel(RunReader(run_path, backend=backend)))


def line_from_run(
    run_path: Path | str, data_key: str, x_dim: str, selectors: dict[str, Any] | None = None, backend: BackendPreference = "auto"
) -> LineData:
    return _controller(run_path, backend).slice_1d(data_key, x_dim, selectors or {})


def heatmap_from_run(
    run_path: Path | str,
    data_key: str,
    x_dim: str,
    y_dim: str,
    selectors: dict[str, Any] | None = None,
    backend: BackendPreference = "auto",
) -> HeatmapData:
    return _controller(run_path, backend).slice_2d(data_key, x_dim, y_dim, selectors or {})


def trace_from_run(
    run_path: Path | str,
    data_key: str,
    point_selectors: dict[str, Any],
    channel: Any | None = None,
    backend: BackendPreference = "auto",
) -> TraceData:
    return _controller(run_path, backend).get_point_trace(data_key, point_selectors, channel=channel)
