# Data Viewer Requirements

This document captures the required viewer behavior for Qulab runs with multidimensional scans and per-point trace data.

## 1. Core Use Cases

### Scalar Per Point

Examples:

- ODMR counts_mean over microwave frequency.
- Rabi contrast over tau.
- 2D scan `mw_freq_hz x tau_s` with one scalar value per point.

Required views:

- 1D line plot.
- 2D heatmap.
- Arbitrary line profile along either heatmap axis.
- For higher-dimensional scans, select 1 or 2 dimensions to display and use selectors for all remaining dimensions.

### Trace Per Point

Examples:

- Each slow scan point has photon bins over time.
- Each point has multi-channel analog trace.
- Each point has shot records.

Required views:

- Select slow-scan point and show its trace.
- Select channel for multi-channel data.
- Overlay traces from multiple selected points.
- Show trace summary scalar if available.

## 2. Data Safety

The viewer must be read-only by default.

Rules:

- Never modify raw data.
- Never rewrite `events.jsonl`, `points.jsonl`, CSV tables, or raw Zarr/HDF5 arrays from the viewer.
- Derived results must be saved as separate artifacts.
- Crashed viewer must not affect run data.

## 3. Performance

The viewer must not load an entire high-dimensional dataset into memory.

Requirements:

- Lazy open run folders.
- Lazy slice arrays.
- Downsample long traces for display.
- Cache small metadata and current slices only.
- Use array backend chunking when available.

## 4. Recommended Architecture

```text
RunReader
  opens metadata/events/points/index
  discovers data keys and backend URIs
  supports CSV and optional Zarr through one logical interface

DatasetModel
  exposes coords, dims, data keys, status masks

SliceController
  maps selected dimensions and selectors into lazy slices

PlotModel
  produces line/heatmap/trace-ready arrays

Viewer UI
  PyQt/PySide or future web UI
```

Keep non-UI models testable without display server.

## 4.1 Dual Backend Requirement

The viewer must support both CSV and Zarr backends through the same logical model.

Rules:

- GUI must not hard-code CSV or Zarr logic.
- GUI calls `RunReader` / `DatasetModel` / `SliceController`.
- `RunReader` selects backend by:
  - user preference,
  - manifest preferred backend,
  - available backend fallback.
- The same UI operations must work for both formats:
  - 1D line plot from scalar per point.
  - 2D heatmap from scalar grid.
  - higher-dimensional slicing by selecting 1 or 2 display dimensions.
  - for scalar data with two or more dimensions, users must be able to choose
    either one displayed dimension for a line slice or two displayed dimensions
    for a heatmap.
  - point trace lookup.
  - multi-channel trace channel selection.
- Available plot modes must be derived from dataset metadata, not from hard-coded
  data key names. The preferred source is `dataset_manifest.json` `data_vars[*].kind`
  and `dims`; JSONL `data_specs`/metadata are fallback indicators for JSONL-only
  runs.
- `scalar_grid` datasets expose line and heatmap views according to dimensionality.
  `trace_grid` datasets expose trace views, and may also expose reduced line or
  heatmap overview views by reducing over the trace axis such as `time_s`.
- Selector controls should only show dimensions not currently used by the active
  plot mode. If `mw_freq_hz` is the line x-axis, the selector panel should show
  all scalar dimensions except `mw_freq_hz`; if `mw_freq_hz` and `tau_s` are the
  heatmap axes, selectors should show only the remaining dimensions.
- If CSV is too large for smooth interaction, viewer should warn and suggest Zarr, but still provide correct read-only access when practical.
- If Zarr dependency is unavailable, CSV backend must still allow basic browsing.

Backend selection UI:

```text
Backend: [Auto | CSV | Zarr]
```

`Auto` should prefer Zarr for large arrays and CSV for small/simple runs if no advanced backend exists.

Run folder selection:

- The viewer may be launched with either one run folder or a parent directory
  containing many run folders.
- If no path argument is provided, the viewer should default to `runs/` and let
  the user choose a folder in the UI.
- The left panel must list discovered run folders that contain
  `dataset_manifest.json`.
- Selecting a run folder should reload metadata, backend, data keys, dimension
  controls, selectors, plot, and table without restarting the app.
- A browse action should allow choosing either a single run folder or a parent
  folder to scan.

Prompt 008 followup requires CSV support before Zarr-only behavior. The viewer
therefore treats CSV as the mandatory baseline backend and Zarr as an optional
preferred backend when installed. All UI code should call `RunReader`,
`DatasetModel`, and `SliceController`; it should not branch directly on CSV file
paths or Zarr array paths.

The Operator Console must reuse the same viewer panel used by the standalone
viewer app. Its Run Data tab opens the completed run path read-only. Storage
backend writing is configured in YAML (`storage.backend` or `storage.backends`);
the viewer backend selector is a read-time override only.

## 5. Third-Party Options

Generic tools:

- HDFView and H5Web inspect HDF5 content but do not understand Qulab run semantics.
- napari is excellent for image-like nD arrays but not ideal as the only experiment browser.
- xarray, hvPlot, HoloViews, and Datashader are strong for labeled N-D slicing and large data.
- pyqtgraph is good for fast Qt plotting.

Recommendation:

- Implement a Qulab-specific viewer.
- Reuse xarray/Zarr/pyqtgraph where available.
- The Qt viewer should prefer pyqtgraph for interactive large line/heatmap data,
  fall back to Matplotlib Qt canvas when pyqtgraph is unavailable, and use simple
  Qt painting only as a last-resort dependency fallback.
- Zarr-backed views should load metadata and coordinate arrays when selecting a
  data key, then read only the selected line, heatmap, or trace slice during
  rendering. CSV remains a compatibility/readability backend and may scan or
  load larger tables unless an index/cache layer is added.
- Do not depend on optional plotting packages for core tests.
