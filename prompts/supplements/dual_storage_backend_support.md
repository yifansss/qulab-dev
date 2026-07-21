# Supplement: CSV + Zarr Dual Storage Backend Support

This supplement applies to all future Storage, GUI, Plotting, Viewer, and Config workers.

## Requirement

Qulab must support both CSV and Zarr as selectable storage/data-viewing backends while preserving the existing JSONL + SQLite event/index layer.

Users must be able to choose:

```yaml
storage:
  backend: csv
```

or:

```yaml
storage:
  backend: zarr
```

or:

```yaml
storage:
  backends: [csv, zarr]
```

## Architecture

The system must use:

```text
events.jsonl / points.jsonl / metadata.json / run_index.sqlite
  for audit, point lifecycle, config, and indexing

CSV backend
  for readable tabular summaries and traces

Zarr backend
  for chunked high-dimensional arrays and large trace data

dataset_manifest.json
  for logical data model and backend URIs

RunReader / DatasetModel / SliceController
  for viewer and analysis access
```

GUI and analysis code must never hard-code CSV or Zarr paths. They must ask `RunReader` for data.

## CSV Must Support

- scalar per point.
- 1D and 2D slow-scan summaries.
- higher-dimensional slow scan using long-form coordinate columns.
- per-point vector trace.
- multi-channel trace with channel and time columns.
- point status and partial/failed points.

CSV may be slower for very large data but must remain correct and readable.

## Zarr Must Support

- coordinate arrays.
- scalar grids.
- trace grids.
- multi-channel traces.
- chunked lazy slicing.
- irregular point fallback through point-centric arrays or manifest references.

Zarr is preferred for high-volume data and interactive viewer performance.

## Viewer Must Support Both

Viewer requirements:

- Backend selector: Auto / CSV / Zarr.
- Same UI operations for both:
  - 1D line plot.
  - 2D heatmap.
  - higher-dimensional selectors.
  - arbitrary profile extraction.
  - point trace inspection.
  - multi-channel trace channel selection.
- Must be read-only by default.
- Must never modify raw CSV/Zarr/JSONL files unless explicitly saving derived artifacts.

## Worker Instruction

Any worker touching storage, plotting, viewer, or GUI must:

1. Read this supplement.
2. Preserve JSONL + SQLite compatibility.
3. Avoid format-specific logic in UI widgets.
4. Add tests for CSV path.
5. Add Zarr tests only when zarr is available, using skip if missing.
6. Keep default `python -m pytest` passing without optional dependencies.

