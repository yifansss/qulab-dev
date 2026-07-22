# P10.6 Live View handoff

Implementation date: 2026-07-22.

P10.6 completes the live plotting path on top of the P10.3 catalog, bounded
buffer, selection/controller, module-status, and sequence-context foundation.
The public controller additions are `list_live_data_specs`, `list_live_points`,
`get_live_selection`, `set_live_selection`, and `clear_live_display`.

Raw and Derived rows use persistent checkboxes. Auto chooses plot shape from
declared data kind and dimensions. Line mode supports compatible scalar
overlays; heatmap keeps missing cells as NaN; trace selects historical/latest
point and a matrix channel. Waiting, active, error, saved, and live-only states
are visible. Checkbox, pause, clear, and auto-follow never modify storage
policy. Event delivery remains in the worker/controller path; Qt widgets are
updated only by the main-thread timer, with at most 200 queue items and one
coalesced refresh per tick.

`qulab.gui.plot_canvas.scientific_plot_canvas_class` is shared with Data Viewer
and selects pyqtgraph, Matplotlib, then native Qt. The native fallback draws
lines and NaN-aware heatmaps rather than replacing them with a table.

The deterministic showcase is
`configs/experiments/live_view_showcase.yaml`; launch instructions are in
`docs/LIVE_VIEW.md`. It covers 2-D scalar scans, saved and live-only derived
values, a declared waiting output, vector trace, and matrix channels.

Automated status at handoff: the headless and integration suites pass; the Qt
behavior test contains rendered canvas-state assertions but is skipped on the
current machine because neither PySide6 nor PyQt6 is installed. Consequently,
the required visible-window manual matrix and the line/derived plus incomplete
heatmap screenshots are not claimed complete and no screenshot artifacts were
fabricated. Run that matrix on the Windows experiment computer with Qt before
calling the cross-platform/manual acceptance complete.

No hardware driver, sequence timing/semantics, or RunStore save policy was
changed. `drivers/pycontrol.zip` remains an unrelated untracked file.
