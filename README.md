# Qulab

Qulab is a lightweight experiment orchestration and data framework for NV center, solid-state spin, and quantum sensing experiments.

Current status: P7/P8 dry-run Operator Console with Tkinter MVP, optional PyQt/PySide workflow editor, and first-stage pycontrol hardware adapters.

Implemented objects:

- `Parameter`, `ParameterRef`, `P`, and `ScanValues`
- structured events and in-memory `EventBus`
- `Procedure` with `ActionStep`, `ScanStep`, `AverageStep`, `MeasurementStep`, `RunStep`, and `CleanupStep`
- `ExperimentContext` with parameter resolution, scan coordinates, mock resources, and monotonic `point_id` generation
- dry-run `ExperimentExecutor` for setup/body/cleanup execution and append-only event emission
- YAML config loading and parsing via `qulab.config`
- mock instrument registry/adapters for microwave source, pulse sequencer, DAQ counter, and analog IO
- pycontrol adapter wrappers for ASG24100, NI-DAQmx, LMX2572, and Rigol DG/AWG
- safe hardware config preflight CLI via `qulab.scripts.hardware_check`
- sync plan dataclasses and basic preflight validation
- `run_dry_config(...)` convenience runner that stores dry-run results with `RunStore`
- Tkinter Operator Console MVP via `qulab.gui.operator_app`
- GUI controller/view models for parameter edits, procedure tree display, preflight resources, event log, and simple live line plot
- optional PySide6/PyQt6 Operator Console via `qulab.gui.pyqt_operator_app`
- editable workflow model with YAML round-trip support for scan, average, call, enabled, add, duplicate, and delete operations
- advanced run readers for dual CSV + optional Zarr datasets via `RunReader`, `DatasetModel`, and `SliceController`

The core layer is intentionally hardware-free. It does not import GUI libraries, pycontrol, NI/ASG SDKs, storage/HDF5, or plotting code. The pycontrol adapter module and registry are import-safe: real pycontrol drivers are imported only during adapter `connect()`.

Dry-run YAML examples:

- `configs/experiments/dry_run_odmr.yaml`
- `configs/experiments/dry_run_rabi.yaml`
- `configs/experiments/dry_run_two_mw_scan.yaml`
- `configs/setups/mock_nv_setup.yaml`

Run a YAML dry-run experiment and write a `RunStore` directory:

```python
from qulab.config import run_dry_config

result = run_dry_config("configs/experiments/dry_run_rabi.yaml", "runs")
print(result.executor_state)
print(result.run_path)
```

Launch the Tkinter Operator Console MVP:

```bash
PYTHONPATH=src python -m qulab.gui.operator_app
```

Launch the recommended PyQt/PySide Operator Console:

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

The PyQt/PySide entry first tries `PySide6`, then `PyQt6`. If neither is installed, importing the module is still safe and the launch command prints a clear message. No network install is required by the project.

The GUI defaults to `configs/experiments/dry_run_rabi.yaml`. You can load Rabi or ODMR, edit common scan/average parameters, click Prepare, then Start. It shows mock resources, sync/preflight issues, procedure tree, event log, a simple Canvas line plot, and the final run path under `runs/`.
The PyQt/PySide Operator Console embeds the same read-only data viewer panel used by `qulab.viewer.pyqt_viewer_app`; after a run completes, the Run Data tab opens the new run path through `RunReader`, `DatasetModel`, and `SliceController`.

Advanced data viewing:

- `metadata.json`, `events.jsonl`, `points.jsonl`, `data.jsonl`, and SQLite remain the audit/index layer.
- Advanced run folders may add `dataset_manifest.json` plus a mandatory CSV table backend under `tables/`.
- If `zarr` is installed, the same manifest can also point to `arrays.zarr/`; `backend="auto"` prefers Zarr and falls back to CSV.
- Use `RunReader`, `DatasetModel`, and `SliceController` to read 1D lines, 2D heatmaps from higher-dimensional scans, and per-point traces without tying code to a GUI toolkit.
- The optional data viewer uses `pyqtgraph` when installed, falls back to a Matplotlib Qt canvas, and only uses simple Qt painting as a last resort.
- For scalar data with two or more dimensions, the viewer supports both `Heatmap` mode with two displayed dimensions and `Line Slice` mode with one displayed dimension. Selector controls show only the remaining dimensions that define the slice position.
- The data viewer can be launched on either a single run folder or a parent folder. Its left panel lists discovered run folders with `dataset_manifest.json`; selecting a run loads that folder without restarting the app.
- Storage write policy is persistent config: CSV is the mandatory baseline, while Zarr is enabled by `storage.backends: [csv, zarr]`. The viewer's `Auto | CSV | Zarr` selector only chooses how an existing run is read; it does not mutate raw data or rewrite the storage config.

```python
from qulab.storage import DatasetModel, RunReader, SliceController

reader = RunReader("path/to/run", backend="auto")
controller = SliceController(DatasetModel(reader))
line = controller.slice_1d("counts_mean", "mw_freq_hz", selectors={"tau_s": 0})
trace = controller.get_point_trace("photon_bins", {"mw_freq_hz": 0, "tau_s": 0})
```

Generate manual advanced storage test data:

```bash
PYTHONPATH=src python -m qulab.scripts.generate_advanced_test_data --include-zarr
PYTHONPATH=src python -m qulab.scripts.generate_large_stability_data
PYTHONPATH=src python -m qulab.viewer.pyqt_viewer_app runs/advanced_test_data/large_stability_validation csv
```

If optional packages such as `zarr`, Qt, or pyqtgraph are installed in a conda
environment, run the same commands through that environment. For example:

```bash
conda run -n mwcavity env PYTHONPATH=src python -m qulab.scripts.generate_large_stability_data --root runs/advanced_test_data/large_stability_zarr_validation --force --include-zarr
conda run -n mwcavity env PYTHONPATH=src python -m qulab.viewer.pyqt_viewer_app
```

The viewer path argument is optional. Without a path it opens `runs/` and lets
the user choose a run folder from the left panel.

Current GUI limits:

- mock/dry-run only; no real hardware adapters are imported or connected.
- Stop logs the request but does not provide reliable mid-run cancellation yet.
- live plotting in the operator console is still minimal, while the offline data viewer provides line, heatmap, and trace plots through the shared advanced storage model.
- workflow editing covers scan values, average count, call args, enabled, add/duplicate/delete for scan/average/call; richer step libraries and drag/drop are still future work.

Basic validation:

```bash
PYTHONPATH=src python -c "import qulab; print(qulab.__version__)"
PYTHONPATH=src python -c "from qulab.storage.run_reader import RunReader; print(RunReader.__name__)"
PYTHONPATH=src python -c "from qulab.storage.slicing import SliceController; print(SliceController.__name__)"
python -m pytest
```

Hardware preparation:

- Start with `configs/setups/real_nv_setup.template.yaml` or `configs/experiments/hardware_odmr.template.yaml`; copy it before editing real ports, device names, and paths.
- Switch a mock resource by changing `adapter: mock_microwave` to `adapter: pycontrol_lmx` and setting `simulation: false`. Qulab now vendors the driver tree at `drivers/pycontrol`, and adapters use that path by default. Use `pycontrol_path` or `QULAB_PYCONTROL_PATH` only when you intentionally want to override the bundled driver path.
- For two microwave sources, use distinct resource names such as `mw_drive` and `mw_probe`; one can be fixed in `setup` while the other is scanned, or both can be nested scans as in `dry_run_two_mw_scan.yaml`.
- Run safe preflight without connecting hardware:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/dry_run_two_mw_scan.yaml --dry-run
```

Bench checklist before real connect-only:

- Verify ASG/NI/MW/AWG cabling, reference clocks, trigger polarity, and NI device name.
- Confirm microwave loads/attenuators and laser interlocks are safe.
- Confirm no AO voltage write is present unless `--allow-ao` is intended.
- Run connect checks only with explicit operator approval:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config path/to/real_nv_setup.yaml --connect-only
```

Start here:

- `PROJECT_BLUEPRINT.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_ORDER.md`
- `workers/README.md`
