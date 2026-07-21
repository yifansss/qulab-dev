# Supplement: GUI/Viewer Instructions for CSV + Zarr Backends

This supplement applies to GUI Worker, PyQt Worker, Plotting Worker, and Data Viewer Worker.

## Goal

All GUI and viewer code must treat CSV and Zarr as interchangeable data backends exposed through a common reader/model layer.

## Do

- Use `RunReader`.
- Use `DatasetModel`.
- Use `SliceController`.
- Provide backend selector:

```text
Auto | CSV | Zarr
```

- In Auto mode:
  - prefer Zarr for large multidimensional arrays if available.
  - fallback to CSV if Zarr is absent or data exists only in CSV.
  - fallback to JSONL summary for old runs.

- For high-dimensional scans:
  - user chooses x dimension for line plot.
  - user chooses x/y dimensions for heatmap.
  - all remaining dimensions become selectors.

- For point traces:
  - user selects a point from heatmap/table.
  - viewer displays trace.
  - multi-channel trace gets a channel selector.

## Do Not

- Do not parse CSV directly inside Qt widgets.
- Do not open Zarr arrays directly inside Qt widgets.
- Do not load full large datasets into memory.
- Do not mutate raw data files.
- Do not require optional packages for default unit tests.

## Required Tests

GUI/model tests should cover:

- CSV-backed synthetic run line plot data.
- CSV-backed synthetic run heatmap data.
- CSV-backed point trace lookup.
- Zarr-backed equivalent tests with `pytest.importorskip("zarr")`.
- Backend selector fallback behavior.

