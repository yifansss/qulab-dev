# Prompt 008: Advanced Storage Backend + Data Viewer Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是把当前 JSONL MVP storage 升级为适合高维慢扫描、每点快 trace、多通道数据的高级存储和查看体系。重点是 Zarr/HDF5 后端、RunReader、lazy slicing、数据查看器后端模型，以及可选 PyQt viewer MVP。默认测试必须无硬件、无 GUI display 依赖。

---

## /goal

在当前 `qulab` 项目中实现 advanced storage 和 data viewer 的第一阶段：保留现有 JSONL/SQLite 作为审计和索引层，新增可选 CSV 与 Zarr 双高级后端用于多维慢扫描和每点 trace 数据；实现 RunReader/DatasetModel/SliceController，使用户能从 run folder 中懒加载数据、选择任意 1 或 2 个扫描维度生成 line/heatmap 数据，并能选取任意扫描点查看该点 trace。viewer 必须双格式支持，通过统一 reader/model 读取 CSV 或 Zarr。若 Qt 可用，可新增一个只读 Data Viewer MVP；无 Qt 或无 Zarr 时默认测试仍必须通过或清楚 skip。完成后 `python -m pytest` 必须通过。

---

## 必须先阅读

1. `PROJECT_BLUEPRINT.md`
2. `docs/DATA_MODEL.md`
3. `docs/DATA_VIEWER_REQUIREMENTS.md`
4. `docs/OPERATOR_UI.md`
5. `workers/storage_worker.md`
6. `workers/plotting_worker.md`
7. `workers/gui_worker.md`
8. 当前实现：
   - `src/qulab/storage/`
   - `src/qulab/gui/plot_model.py`
   - `src/qulab/config/`

---

## 当前事实

当前 storage 已实现：

```text
metadata.json
events.jsonl
points.jsonl
data.jsonl
run_index.sqlite
```

这适合 MVP、审计和小数据，不适合长期承载大型 trace/multichannel/high-dimensional array。

新 worker 不能破坏现有 RunStore 默认行为。Advanced backend 必须是 optional。

---

## 推荐新增文件

```text
src/qulab/storage/backends.py
src/qulab/storage/array_backend.py
src/qulab/storage/zarr_backend.py
src/qulab/storage/hdf5_backend.py
src/qulab/storage/run_reader.py
src/qulab/storage/dataset_model.py
src/qulab/storage/slicing.py
src/qulab/viewer/__init__.py
src/qulab/viewer/models.py
src/qulab/viewer/plot_data.py
src/qulab/viewer/pyqt_viewer_app.py      # optional if Qt available
```

Tests:

```text
tests/unit/test_run_reader.py
tests/unit/test_dataset_slicing.py
tests/unit/test_viewer_models.py
tests/unit/test_advanced_storage_manifest.py
tests/integration/test_advanced_storage_synthetic_run.py
```

---

## Advanced Storage Requirements

### 1. Manifest

Add `dataset_manifest.json` in run folder when advanced CSV/Zarr arrays or tables are present.

Example:

```json
{
  "schema_version": 1,
  "backends": {
    "csv": "tables",
    "zarr": "arrays.zarr"
  },
  "coords": {
    "mw_freq_hz": {"uri": "arrays.zarr:/coords/mw_freq_hz", "unit": "Hz"},
    "tau_s": {"uri": "arrays.zarr:/coords/tau_s", "unit": "s"},
    "time_s": {"uri": "arrays.zarr:/coords/time_s", "unit": "s"}
  },
  "data_vars": {
    "counts_mean": {
      "uri": "arrays.zarr:/summaries/counts_mean",
      "dims": ["mw_freq_hz", "tau_s"],
      "kind": "scalar_grid",
      "unit": "count",
      "backends": {
        "csv": "tables/summaries/counts_mean.csv",
        "zarr": "arrays.zarr:/summaries/counts_mean"
      }
    },
    "photon_bins": {
      "uri": "arrays.zarr:/traces/photon_bins",
      "dims": ["mw_freq_hz", "tau_s", "time_s"],
      "kind": "trace_grid",
      "unit": "count"
    }
  }
}
```

### 2. Backend Interface

Implement optional interface:

```python
class ArrayBackend:
    def write_array(self, key, data, dims, coords=None, attrs=None): ...
    def read_array(self, key, selection=None): ...
    def list_arrays(self): ...
```

Implement both:

```python
class CsvBackend(ArrayBackend): ...
class ZarrBackend(ArrayBackend): ...
```

CSV is mandatory for this worker because it needs no heavy binary dependency. Zarr is optional if installed; if not installed, code must be import-safe and tests should skip Zarr-specific write/read.

If `zarr` is not installed:

- import should not fail globally.
- backend constructor should raise clear optional dependency error.
- tests requiring backend should skip.

### 3. CSV Backend

CSV backend must support:

- point table.
- scalar summaries in long-form CSV.
- trace data in long-form CSV.
- multi-channel trace rows with `channel` and `time_s`.
- reconstruction into `DatasetModel`.

Required files:

```text
tables/points.csv
tables/data_keys.csv
tables/summaries/<key>.csv
tables/traces/<key>.csv
```

### 4. Zarr Backend

Zarr backend should support:

- coordinate arrays.
- scalar grids.
- trace grids.
- chunked reads for slicing.

If Zarr is unavailable, fallback must be graceful and CSV tests must still pass.

### 5. Synthetic Advanced Run

Create helper for tests:

```python
create_synthetic_advanced_run(
    root,
    dims={"mw_freq_hz": 5, "tau_s": 4, "time_s": 100},
    include_trace=True,
    backend="csv" | "zarr" | "both",
)
```

It should create a fake run folder with metadata, manifest, coords, summary grid, and trace grid. CSV version must always work. Zarr version should work when zarr is installed and skip otherwise.

---

## Reader / Viewer Model Requirements

### 1. RunReader

```python
reader = RunReader(run_path)
reader.metadata
reader.list_data_keys()
reader.get_coords()
reader.get_data_var("counts_mean")
reader.get_trace(point_selection, key="photon_bins")
```

Must support:

- existing JSONL-only runs.
- advanced manifest runs.
- CSV backend runs.
- Zarr backend runs.
- missing optional backend with clear errors.

### 2. SliceController

For N-dimensional scalar grid:

```python
slice_1d(data_key, x_dim, selectors) -> LineData
slice_2d(data_key, x_dim, y_dim, selectors) -> HeatmapData
```

Rules:

- `x_dim` and `y_dim` are selected by user.
- all other dims must have selector indices/values.
- no full-load of entire array if backend supports lazy slicing.
- output contains labels, units, coords, values.

### 3. Trace Selection

```python
get_point_trace(data_key, point_selectors, channel=None) -> TraceData
```

Must support:

- trace dims like `[mw_freq_hz, tau_s, time_s]`.
- multi-channel trace dims like `[mw_freq_hz, tau_s, channel, time_s]`.
- selected point returns time axis and trace values.

### 4. Viewer UI MVP

If implementing PyQt viewer:

```bash
PYTHONPATH=src python -m qulab.viewer.pyqt_viewer_app <run_path>
```

UI requirements:

- Open run folder.
- Backend selector: Auto / CSV / Zarr.
- Data key list.
- Dimension selector panel.
- 1D line plot.
- 2D heatmap or table fallback.
- Point trace panel.
- Read-only by default.

If Qt is not available, app should print friendly message and exit.

---

## Third-Party Policy

Do not require network install.

Allowed optional imports if already installed:

- `zarr`
- `xarray`
- `numpy`
- `PySide6` / `PyQt6`
- `pyqtgraph`

Core tests must not fail if optional packages are absent. Use `pytest.importorskip`.

---

## Documentation Updates

Update:

```text
docs/DATA_MODEL.md
docs/DATA_VIEWER_REQUIREMENTS.md
README.md
workers/storage_worker.md
workers/plotting_worker.md
```

Explain:

- current MVP JSONL format.
- advanced Zarr/HDF5 backend.
- how to view high-dimensional data.
- why generic HDF viewers are insufficient.
- how raw data safety is preserved.

---

## Validation Commands

Run:

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.storage.run_reader import RunReader; print(RunReader.__name__)"
PYTHONPATH=src python -c "from qulab.storage.slicing import SliceController; print(SliceController.__name__)"
```

If viewer is implemented:

```bash
PYTHONPATH=src python -c "from qulab.viewer.pyqt_viewer_app import main; print(main.__name__)"
```

Do not require opening a real GUI window during automated tests.

---

## Final Response Requirements

Worker must report:

1. Which advanced backends were implemented: CSV, Zarr, or both.
2. Whether optional dependencies were available.
3. How JSONL and advanced arrays coexist.
4. How to slice 1D/2D views from higher-dimensional scans.
5. How to inspect per-point traces.
6. Tests and validation commands.
7. Remaining limitations.
