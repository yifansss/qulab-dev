# Planner Handoff Temp - 2026-06-28

This temporary document is for the next planner/agent. It summarizes the user's project background, key requirements, current implementation status, worker progress, and recommended next steps. Read this before continuing the thread.

## 1. Project Background

The project is `qulab`, located at:

```text
<QULAB_PROJECT_ROOT>
```

The user is building a lightweight but powerful experiment orchestration framework for NV center / solid-state spin / quantum sensing experiments.

Existing sibling projects:

```text
../pycontrol       # existing Python instrument drivers
../panel(basic)   # old/simple panel, not the target architecture
```

Main user goal:

- Build a general framework that can express experiments as config/procedure trees.
- Support single/multi-dimensional scans, averaging, complex per-point measurement procedures, full data provenance, plotting, GUI operation, and later real hardware.
- Avoid becoming a huge LabVIEW clone, but match/surpass LabVIEW / Labscript / QCoDeS in the specific lab workflow.
- Preserve ease of use for researchers while keeping the architecture powerful.

Core design principle:

```text
Driver = how to talk to a concrete device.
Adapter = how that device exposes Qulab capabilities.
Procedure = experimental logic: setup/scan/average/measurement/run/cleanup.
Sync = hardware trigger/clock/arm/start/read relationships.
Storage = all data, metadata, config, events, and provenance.
GUI = config/procedure editor + operator console, not hardcoded experiment logic.
```

## 2. Key User Requirements

### Experiment Procedure

The user emphasized that the core generality is not a full timing compiler; the important abstraction is experiment setup/procedure editing:

- Easy Python/object style or YAML config.
- Nested loops like normal `for` loops.
- GUI workflow/procedure tree similar in spirit to Scratch/LabVIEW block logic, but maintainable and Git-friendly.
- Each instrument can have its own sub-panel for detailed hardware-specific settings.

The framework must support:

- 1D, 2D, and higher-dimensional scans.
- One or multiple frequency sources, e.g. one fixed and one scanned, or both scanned.
- Average/no-average modes.
- Per-point measurement procedures that can include special pulse sequences, multiple actions, raw traces, and summaries.
- Complex data storage and later browsing.

### Timing and Sync

The user repeatedly asked about ASG/NI synchronization:

- ASG pulse generator can act as master for pulse experiments.
- NI can act as master for AO/AI internal synchronization.
- Mixed mode must be supported:
  - NI AO sets a slow parameter, waits settle.
  - ASG performs precise pulse sequence inside each point.
  - NI counts/acquires under ASG trigger/gate/clock.

Important distinction:

```text
Procedure timing: macro order, scan/average/set/read.
Pulse sequence timing: shot-level ASG/AWG laser/MW/readout gates.
Sync plan: inter-device trigger/clock/arm/start/read.
```

### NI Driver Concern

The user noted current `../pycontrol/DataAcquisition/driver.py` is limited:

- lacks external trigger start for output/acquisition;
- lacks ASG-master support;
- has limited AO/AI sync;
- current AO-point-to-AI-point sync can waste NI AI sampling rate;
- needs AO slow point + many AI samples / trace per point;
- needs explicit support for ASG master / NI master / mixed mode.

Prompt 007 was created to add an advanced NI sync driver in `../pycontrol/DataAcquisition/sync_driver.py` without modifying old `driver.py`, and to update Qulab adapter selection via config:

```yaml
daq:
  adapter: pycontrol_ni
  driver: sync
  pycontrol_path: ../pycontrol
```

### Data Storage and Viewer

The user asked whether current storage is enough. Current answer:

- MVP storage was `metadata.json + events.jsonl + points.jsonl + data.jsonl + run_index.sqlite`.
- For high-dimensional slow scans and per-point fast trace data, advanced storage is needed.

User requirements for viewer/data browser:

- 2D slow scan with scalar per point:
  - arbitrary profile along either scan direction;
  - 2D heatmap.
- Higher-dimensional scan:
  - select any 1 dimension for line plot;
  - select any 2 dimensions for heatmap;
  - all other dimensions become selectors/sliders/dropdowns.
- Per-point trace:
  - click/select any slow-scan point and view its trace;
  - multi-channel traces need channel selection;
  - overlay selected point traces if practical.
- Viewer must not hang on large data.
- Viewer must be read-only by default and never corrupt raw data.

008 worker has now clarified the storage/viewer direction:

```text
JSONL + SQLite remain audit/index layer.
CSV backend is mandatory readable baseline.
Zarr backend is optional high-performance backend.
dataset_manifest.json provides one logical model across CSV/Zarr.
RunReader / DatasetModel / SliceController are the only access path for GUI/viewer/analysis.
```

## 3. Current Test Status

Latest verification command:

```bash
python -m pytest
```

Result observed in this session:

```text
78 passed, 6 skipped
```

Skips are expected for hardware/optional dependency paths.

## 4. Worker Progress Summary

### 001 Core Foundation Worker - Done

Implemented:

- `Parameter`, `ParameterRef`, `P`, `ScanValues`
- structured events, `EventBus`
- `Procedure`, `ActionStep`, `ScanStep`, `AverageStep`, `MeasurementStep`, `RunStep`, `CleanupStep`
- `ExperimentContext`
- `ExperimentExecutor`
- dry-run nested scan and point IDs

Purpose:

```text
Python object procedure -> dry-run execution -> event stream
```

### 002 Storage RunStore Worker - Done

Implemented:

- `RunStore`
- `metadata.json`
- `events.jsonl`
- `data.jsonl`
- `points.jsonl`
- `run_index.sqlite`

Important:

- Core/storage remain decoupled.
- Executor does not write files directly.
- RunStore subscribes to EventBus.

### 003 Config + Mock Instruments + Sync Worker - Done

Implemented:

- YAML loader/parser
- `ParsedExperiment`
- mock instruments and `InstrumentRegistry`
- basic `SyncPlan`, `TriggerEdge`, `SyncValidator`
- dry-run YAML examples
- `run_dry_config(...)`

Purpose:

```text
YAML -> context/resources/procedure/sync -> dry-run -> RunStore
```

### 004 GUI Operator Console Worker - Done

Implemented Tkinter MVP:

- load dry-run YAML
- procedure tree display
- common parameter edits
- Prepare/Start dry-run
- EventBus/RunStore integration
- log and simple Canvas plot

Prompt 004-updated was later created to upgrade to PyQt/PySide white/clean operator UI and workflow editor.

### 004-updated PyQt Operator Workflow Worker - Likely Done

Tests now include:

- `test_pyqt_operator_import.py`
- `test_workflow_model.py`
- `test_workflow_yaml_roundtrip.py`
- `test_gui_edit_dry_run_effect.py`
- `test_pyqt_controller_roundtrip.py`

This suggests 004-updated has been implemented. Next planner should inspect:

```text
src/qulab/gui/qt_compat.py
src/qulab/gui/pyqt_operator_app.py
src/qulab/gui/workflow_model.py
src/qulab/gui/workflow_editor.py
src/qulab/gui/yaml_editor.py
```

and verify GUI behavior if needed.

### 005 Pycontrol Hardware Adapter Worker - Done

Implemented:

- `src/qulab/instruments/adapters/pycontrol.py`
- pycontrol adapters for ASG, NI, LMX, AWG
- safe `hardware_check` CLI
- hardware config templates
- multi-microwave dry-run example
- hardware tests marked and skipped by default

Important:

- `../pycontrol` is not copied into Qulab.
- Qulab adapter uses `pycontrol_path` or `QULAB_PYCONTROL_PATH` and imports drivers only in `connect()`.
- Default tests do not connect hardware.

### 006 Bench Commissioning Worker - Prompt Created

Prompt exists:

```text
prompts/006_bench_commissioning_worker.md
```

Purpose:

- staged bench workflow:
  - dry-run
  - connect-only
  - identify/read-only
  - configure-only
  - dark-count/readout-only
  - armed output, explicit authorization only
- GUI bench checklist
- sequence template rendering

Unknown if implemented; tests/files should be checked if needed.

### 007 Advanced NI Sync Driver Worker - Prompt Created / Likely Implemented

Prompt exists:

```text
prompts/007_advanced_ni_sync_driver_worker.md
```

Tests now include:

- `test_ni_sync_driver_api_contract.py`
- `test_pycontrol_ni_driver_selection.py`
- `test_ni_sync_config_templates.py`
- `test_ni_sync_yaml_dry_run.py`
- `test_ni_sync_hardware.py` skipped

This suggests some or all of 007 has been implemented. Next planner should verify whether the new driver was written directly to:

```text
../pycontrol/DataAcquisition/sync_driver.py
```

or only represented through Qulab tests/patches. Important because `../pycontrol` is outside the Qulab writable root and may require explicit write permission.

### 008 Advanced Storage and Viewer Worker - Done / Recently Completed

User reports 008 completed CSV and Zarr dual-format viewer support. Current files confirm:

```text
src/qulab/storage/csv_backend.py
src/qulab/storage/zarr_backend.py
src/qulab/storage/array_backend.py
src/qulab/storage/run_reader.py
src/qulab/storage/dataset_model.py
src/qulab/storage/slicing.py
src/qulab/storage/synthetic.py
src/qulab/viewer/models.py
src/qulab/viewer/plot_data.py
src/qulab/viewer/pyqt_viewer_app.py
```

Docs/prompts added:

```text
docs/DATA_VIEWER_REQUIREMENTS.md
prompts/002_followup_dual_csv_zarr_storage_backend.md
prompts/004_followup_gui_viewer_dual_csv_zarr_backend.md
prompts/008_followup_dual_csv_zarr_advanced_storage_viewer.md
prompts/supplements/dual_storage_backend_support.md
prompts/supplements/gui_storage_viewer_dual_backend_instruction.md
```

Confirmed tests:

```text
78 passed, 6 skipped
```

## 5. Current Storage / Viewer Architecture

Current baseline run folder:

```text
metadata.json
events.jsonl
points.jsonl
data.jsonl
run_index.sqlite
```

Advanced storage requirements now documented:

```text
tables/                 # CSV backend, mandatory advanced baseline
arrays.zarr/            # optional high-performance backend
dataset_manifest.json   # shared logical model for CSV/Zarr
```

Important rules:

- CSV backend is mandatory for readability and no heavy dependencies.
- Zarr backend is optional but preferred for large high-dimensional trace data.
- JSONL + SQLite remain for audit/index compatibility.
- GUI/viewer/analysis must not open CSV/Zarr paths directly.
- They must use:

```python
RunReader
DatasetModel
SliceController
```

Current reader behavior from files:

- `RunReader(run_path, backend="auto" | "csv" | "zarr")`
- auto prefers Zarr if available and manifest declares it; otherwise CSV.
- old JSONL-only runs still have fallback summary access.

Current slicing behavior:

- `slice_1d(data_key, x_dim, selectors)`
- `slice_2d(data_key, x_dim, y_dim, selectors)`
- `get_point_trace(data_key, point_selectors, channel=None, time_dim="time_s")`

## 6. Do 002 and 004 Need Follow-up?

Yes. Because 008 clarified storage/viewer semantics, 002 and 004 should be refined.

However, prompt files already exist:

```text
prompts/002_followup_dual_csv_zarr_storage_backend.md
prompts/004_followup_gui_viewer_dual_csv_zarr_backend.md
```

The next planner should decide whether these follow-ups are already fully satisfied by 008 or still require targeted workers.

### 002 Follow-up: What to Check

The storage follow-up should ensure:

1. `RunStore` can actually write advanced CSV/Zarr backends based on config:

```yaml
storage:
  backend: csv
```

or:

```yaml
storage:
  backends: [csv, zarr]
```

2. `dataset_manifest.json` is generated by real RunStore execution, not only synthetic tests.
3. `tables/` is created for real dry-run examples when requested.
4. Zarr writing is optional and cleanly skipped/error-reported if package missing.
5. `run_index.sqlite` data_keys point to manifest/backend URIs.

Potential issue:

- Current `RunStore` inspected in this session still seemed primarily JSONL-oriented. It may not yet route live DataPoint events into CSV/Zarr advanced backends unless 008 added code elsewhere or synthetic helpers only. Next planner should inspect `RunStore` after 008 carefully.

Recommended action:

- If RunStore cannot write CSV/Zarr from config yet, send a targeted 002-followup worker.

### 004 Follow-up: What to Check

The GUI/viewer follow-up should ensure:

1. Operator/data viewer uses `RunReader/DatasetModel/SliceController`.
2. GUI has backend selector:

```text
Auto | CSV | Zarr
```

3. GUI can open a run folder or parent `runs/` directory.
4. GUI supports:
   - 1D line plot;
   - 2D heatmap;
   - higher-dimensional selectors;
   - point trace lookup;
   - multi-channel trace channel selection.
5. GUI remains read-only for raw data.
6. Qt tests skip cleanly if Qt missing.

Potential issue:

- 004-updated PyQt operator GUI may focus on experiment running/workflow editing, while 008 viewer may be a separate viewer. The user likely wants a coherent UI story. Next planner should decide whether to:
  - keep run operator and data viewer separate for now; or
  - add a viewer tab inside PyQt operator.

Recommended action:

- If viewer functionality is only backend/model but not visible enough, send a 004-followup GUI/viewer worker using the existing prompt.

## 7. Recommended Immediate Next Steps

### Step A - Verify 008 Integration Depth

Run/read:

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.storage.run_reader import RunReader; print(RunReader.__name__)"
PYTHONPATH=src python -c "from qulab.storage.slicing import SliceController; print(SliceController.__name__)"
PYTHONPATH=src python -c "from qulab.viewer.pyqt_viewer_app import main; print(main.__name__)"
```

Inspect:

```text
src/qulab/storage/run_store.py
src/qulab/storage/csv_backend.py
src/qulab/storage/zarr_backend.py
src/qulab/storage/synthetic.py
src/qulab/viewer/pyqt_viewer_app.py
tests/integration/test_advanced_storage_synthetic_run.py
```

Question to answer:

> Does normal dry-run execution through RunStore generate CSV/Zarr/manifest when storage config asks for it, or only synthetic test runs?

### Step B - Issue 002 Follow-up If Needed

If RunStore advanced writing is incomplete, use:

```text
prompts/002_followup_dual_csv_zarr_storage_backend.md
```

Focus this worker on real RunStore integration, not just reader/synthetic examples.

### Step C - Issue 004 Follow-up If Needed

If GUI/viewer UI is incomplete, use:

```text
prompts/004_followup_gui_viewer_dual_csv_zarr_backend.md
```

Focus this worker on:

- user-visible run browser/data viewer;
- backend selector;
- high-dimensional selectors;
- trace panel;
- read-only safety.

### Step D - Do Not Rush Hardware Output

User is interested in real hardware, but there are still important safety and NI sync concerns. Avoid running output actions until:

- advanced NI sync driver is verified;
- hardware_check staged workflow is complete;
- user provides real config and explicitly authorizes connect/output/AO actions.

## 8. Important User Preferences

- User prefers complete, concrete worker prompts.
- User often asks if a worker can "一次多做一点"; answer can be yes if safety boundaries remain clear.
- User cares strongly about GUI usability and visual clarity.
- Preferred GUI style:
  - clean white main color;
  - professional lab control panel;
  - useful procedure/workflow tree editor.
- User wants powerful but lightweight architecture.
- User dislikes vague plans; provide exact files/prompts/goals.
- User wants core decisions written into docs/prompts so future agents inherit them.

## 9. Known Caveats

- The project directory was reported earlier as not a git repository. Do not assume `git status` works.
- There are `__pycache__` and `.DS_Store` files in listings; avoid touching unless asked.
- `../pycontrol` is a sibling directory outside Qulab writable root. Editing it may require escalated permission.
- Network is restricted. Do not ask workers to install packages from the internet.
- Optional packages (`zarr`, `h5py`, `PySide6`, `PyQt6`, `pyqtgraph`) must be optional; tests should skip gracefully if absent.

## 10. Current Best Answer to User's Latest Question

User asked whether 002 and 004 need follow-up after 008.

Answer:

```text
Yes, conceptually. 008 clarified the storage/viewer semantics enough that storage and GUI follow-ups should be aligned with CSV+Zarr dual backend. The repository already contains 002-followup and 004-followup prompt files. The next planner should first verify whether 008 fully satisfied those follow-ups. If not, send targeted 002-followup to integrate RunStore writing, and targeted 004-followup to expose the viewer in GUI.
```

