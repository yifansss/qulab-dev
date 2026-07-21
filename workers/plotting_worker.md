# Plotting Worker Specification

## Mission

实现实时绘图和基础分析接口。绘图只订阅事件，不控制硬件。

## Deliverables

1. `plotting/subscribers.py`
2. `plotting/live_plot.py`
3. `plotting/line.py`
4. `plotting/heatmap.py`
5. `plotting/analysis.py`

## Rules

1. plotting 不导入 pycontrol。
2. plotting 不直接访问 adapter。
3. 支持 headless tests。
4. GUI plotting 和 CLI plotting 共享数据 reducer。
5. 大数据更新要节流，避免阻塞 executor。

## MVP

- line plot for ODMR。
- heatmap for 2D Rabi。
- save preview png。

## Advanced Viewer Data

Prompt 008 followup routes offline viewer plotting through storage models:

- Use `RunReader` and `DatasetModel` to discover data keys, dims, units, and
  backend URIs.
- Use `SliceController.slice_1d(...)` for line plots and
  `SliceController.slice_2d(...)` for heatmaps.
- For scalar data with two or more dimensions, plotting must expose both a
  one-dimensional line slice and a two-dimensional heatmap slice.
- Do not infer plot modes from variable names. Use `dataset_manifest.json`
  `kind`/`dims`, or JSONL `data_specs` as fallback.
- For `trace_grid` variables, expose Trace mode and optionally reduced
  Line/Heatmap overview modes by reducing over the trace axis.
- Selector controls should be derived from hidden dimensions only: exclude the
  active line x-axis, or exclude both heatmap axes.
- Use `SliceController.get_point_trace(...)` for selected point traces and
  multi-channel trace views.
- Plotting code should not hard-code CSV or Zarr paths; backend selection is
  handled by `RunReader`.
- Prefer pyqtgraph for large interactive plots, with Matplotlib and simple Qt
  rendering as fallbacks.
- Use `qulab.scripts.generate_large_stability_data` for manual large-data
  stability runs in the 200MB-1GB range; default automated tests should continue
  to use small synthetic runs.
- Use `--include-zarr` in an environment with Zarr installed, for example
  `conda run -n mwcavity env PYTHONPATH=src python -m qulab.scripts.generate_large_stability_data --include-zarr`.
