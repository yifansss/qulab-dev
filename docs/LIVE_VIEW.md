# Live View

The Qt Operator Console Live Run page plots raw `DataPoint` and derived
`DerivedData` values while a run is active. It uses the same plotting canvas as
the completed-run Data Viewer. The renderer preference is pyqtgraph,
Matplotlib, then the built-in Qt painter.

Launch the deterministic hardware-free showcase from the repository root:

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app \
  --config configs/experiments/live_view_showcase.yaml
```

Prepare and start the run, then use the source checkboxes. `Auto` chooses a
line for scalar one-dimensional data, a heatmap for scalar two-dimensional
data, and a trace for vector or matrix data. Compatible scalar keys with the
same dimensions and unit can be overlaid. Heatmaps leave incomplete cells
empty. Trace mode exposes point and channel controls; vectors without an
explicit axis use `sample_index`.

The source table distinguishes raw/derived, waiting/active/error, and
saved/live-only values. `Pause display` stops repaint only: event ingestion,
analysis, and storage continue. `Clear display` clears only the bounded GUI
history and does not delete the run store. Auto-follow selects the latest
point for trace display. Table mode is a diagnostic summary and avoids dumping
large arrays into cells.

Plotting is intentionally downstream-only. Live View selects and presents
declared outputs; formulas remain in analysis modules. Malformed or
non-numeric values are isolated as source errors and do not stop the run.

Qt widget tests are skipped automatically when no supported Qt binding is
installed. Headless catalog, buffer, selection, controller, and showcase tests
remain mandatory in that environment.
