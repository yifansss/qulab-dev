# Prompt 004-followup: GUI/Viewer CSV + Zarr Backend Support

This followup belongs to **Prompt 004 / 004-updated GUI Workers** and all future GUI or viewer workers. It adds concrete GUI requirements for reading CSV and Zarr through the same viewer model.

---

## /goal

Update GUI/viewer planning so Qulab can browse runs stored with either CSV or Zarr backends. The GUI must not contain format-specific storage logic. It must use `RunReader`, `DatasetModel`, and `SliceController` to support identical operations for CSV-backed and Zarr-backed runs.

Success criteria:

1. Viewer has backend selector:

```text
Auto | CSV | Zarr
```

2. GUI works with CSV-only runs.
3. GUI works with Zarr runs when `zarr` is installed.
4. GUI can fall back gracefully if Zarr is unavailable.
5. GUI supports:
   - 1D line plot.
   - 2D heatmap.
   - higher-dimensional selectors.
   - arbitrary profile extraction.
   - point trace inspection.
   - multi-channel trace channel selection.
6. GUI is read-only by default and never mutates raw data files.
7. Default tests pass without Qt display and without optional Zarr.

---

## Must Read

Before implementing, read:

1. `docs/DATA_VIEWER_REQUIREMENTS.md`
2. `docs/DATA_MODEL.md`
3. `prompts/supplements/gui_storage_viewer_dual_backend_instruction.md`
4. `prompts/002_followup_dual_csv_zarr_storage_backend.md`
5. `workers/gui_worker.md`
6. `workers/plotting_worker.md`

---

## Architecture Rule

Do not do this in Qt widgets:

```python
open("tables/traces/photon_bins.csv")
zarr.open("arrays.zarr")
```

Instead:

```python
reader = RunReader(run_path, backend="auto")
model = DatasetModel(reader)
slice_controller = SliceController(model)
line = slice_controller.slice_1d(...)
heatmap = slice_controller.slice_2d(...)
trace = slice_controller.get_point_trace(...)
```

---

## Required Viewer Behavior

### 1D line plot

User chooses:

- data key
- x dimension
- selectors for all other dimensions

### 2D heatmap

User chooses:

- data key
- x dimension
- y dimension
- selectors for all other dimensions

### Higher-dimensional scans

All dimensions not selected for display become:

- slider
- dropdown
- numeric index selector

### Point trace

User selects:

- point by heatmap click, point table row, or coordinate selector
- trace key
- channel if available

Viewer displays:

- time axis
- trace values
- point coordinates
- point status

---

## Backend Selection

Auto mode:

- Prefer Zarr if available and manifest says Zarr exists.
- Fall back to CSV if Zarr unavailable or user chooses CSV.
- Fall back to JSONL summary for old runs.

CSV mode:

- Use CSV backend only.
- Warn if files are large and interaction may be slower.

Zarr mode:

- Use Zarr backend only.
- If `zarr` unavailable, show friendly error and do not crash.

---

## Tests

Non-GUI model tests are required:

```text
tests/unit/test_viewer_backend_selection.py
tests/unit/test_viewer_csv_line_heatmap.py
tests/unit/test_viewer_csv_trace.py
tests/unit/test_viewer_zarr_optional.py
```

Rules:

- CSV tests must always run.
- Zarr tests must use `pytest.importorskip("zarr")`.
- Qt widget tests must skip if Qt unavailable.
- No test should open a real GUI window by default.

---

## Validation Commands

Run:

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.storage.run_reader import RunReader; print(RunReader.__name__)"
PYTHONPATH=src python -c "from qulab.storage.slicing import SliceController; print(SliceController.__name__)"
```

If viewer app exists:

```bash
PYTHONPATH=src python -c "from qulab.viewer.pyqt_viewer_app import main; print(main.__name__)"
```

