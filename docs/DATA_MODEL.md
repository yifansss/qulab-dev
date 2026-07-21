# Data Model

## 1. Run Directory

每次运行创建：

```text
runs/YYYY-MM-DD/YYYYMMDD_HHMMSS_<experiment_name>/
```

目录内：

```text
config.yaml
resolved_config.yaml
metadata.json
events.jsonl
data.jsonl
points.jsonl
artifacts/
  sequences/                # copied ASG/AWG sequence files used by this run
  tables/                    # mandatory advanced CSV backend when manifest is present
  arrays.zarr/               # optional high-performance array backend
  dataset_manifest.json      # shared logical dataset manifest for CSV/Zarr
  data.h5                    # optional export/compatibility artifact
preview.png
logs.txt
```

数据根目录维护一个轻量索引数据库：

```text
runs/run_index.sqlite
```

SQLite 只做索引和查询，不直接承载大型数组。真实数据以每个 run folder 内的文件为准。

## 2. Metadata

`metadata.json` 必须包含：

```json
{
  "schema_version": 1,
  "run_id": "20260626_153012_rabi_2d",
  "experiment_name": "rabi_2d",
  "started_at": "2026-06-26T15:30:12+08:00",
  "ended_at": null,
  "status": "running",
  "user": "unknown",
  "machine": "hostname",
  "qulab_version": "0.0.0",
  "git_commit": null,
  "resources": {},
  "sync": {},
  "sequence_snapshots": [
    {
      "reference_id": "resource_asg",
      "label": "asg resource sequence",
      "source": "resources.asg.sequence_file",
      "resource": "asg",
      "source_path": "configs/sequences/rabi.json",
      "artifact_path": "artifacts/sequences/resource_asg_abcdef123456.json",
      "sha256": "abcdef...",
      "mtime": 1782710000.0,
      "size_bytes": 1234,
      "parameters": ["tau_s"],
      "channels": ["ch1", "ch5"],
      "warnings": []
    }
  ],
  "data_keys": []
}
```

Sequence 文件不能只保存路径。每次 run 开始时，storage layer 必须扫描 resource-level
`sequence_file` 和 workflow 中每个 `asg.load_sequence` / sequence-capable load step 的
`args.sequence_file`、`args.path` 或 `args.sequence_path`，把存在的文件复制到
`artifacts/sequences/`，并在 `metadata.json.sequence_snapshots` 记录原始路径、artifact
相对路径、hash、mtime、size、参数和 channel 预览。这样旧 run 不会因为之后修改原始
sequence 文件而失去可复现实验上下文。

### 2.1 Sequence Bundle Provenance

使用 `load_sequence_from_bundle` 时，RunStore 额外保存：

```text
artifacts/sequences/<bundle_id>/manifest.yaml
artifacts/sequences/<bundle_id>/<entry_id>__<short_sha256>.json
sequence_selections.jsonl
```

`metadata.json.sequence_bundles` 保存 bundle id、resource、manifest source/artifact/hash、
entry count 和 coordinate names；`sequence_selection_count` 保存已成功选择次数，
`sequence_selection_table` 指向 append-only point table。每个 successful point selection
在 `sequence_selections.jsonl` 保留 point_id、coords、entry id、source/artifact/hash 和
metadata。同一 entry 被多个 point 使用时只复制一份 artifact，但逐点 selection 行全部
保留。现有 `sequence_snapshots` 不删除，继续服务旧单 sequence workflow。

source 或 manifest 在 run 中途变化时 hash 校验 fail closed。metadata.json 不嵌入大型
逐点 selection list，也不保存 sequence 文件全文。

### 2.2 Planned Sequence Generation Provenance (Phase E)

Phase E 自动生成 bundle 时，RunStore 还应保存 authoring/generation provenance：

```text
artifacts/sequence_generation/<plan_id>/sequence_plan.yaml
artifacts/sequence_generation/<plan_id>/provider_identity.json
artifacts/sequence_generation/<plan_id>/generation_log.txt
artifacts/sequences/<bundle_id>/manifest.yaml
sequence_selections.jsonl
```

`metadata.json.experiment_parameters` 记录参数 label、unit、mode、role 和所属 plan；
`metadata.json.sequence_generation` 记录 plan/provider/template/manifest hash、point count、
cache hit 和 generation status。完整 values/grid 保存在 `sequence_plan.yaml` 与
`resolved_config.yaml`，不在 metadata 中复制大型数组。

生成参数必须编译成普通 workflow scan coordinate，因此每个 `DataPoint.coords`、
`MeasurementStarted/Completed.coords` 和 `SequenceSelected` 都使用同一参数值。这样数据、
实验参数和 concrete sequence 不依赖文件名猜测即可逐点关联。

框架而非用户 provider 负责 manifest、entry id、hash 和 artifact packaging；provider source
identity、版本、source hash、template hash、normalized args 和 generation diagnostics 必须可追溯。
cache 只用于加速，run artifact 才是该次实验的 provenance authority。

## 3. Events

`events.jsonl` 每行一个 JSON：

```json
{"type":"RunStarted","time":"...","run_id":"..."}
{"type":"ParameterChanged","time":"...","name":"mw_freq","value":2870000000.0}
{"type":"DataPoint","time":"...","data":{"counts":1234},"coords":{"mw_freq":2870000000.0}}
{"type":"SequenceSelected","point_id":"p000001","bundle_id":"rabi_tau","entry_id":"tau_20ns","sequence_sha256":"..."}
```

事件必须 append-only。

复杂测量点必须允许多个事件：

```json
{"type":"MeasurementStarted","time":"...","point_id":"p000001","coords":{"mw_freq":2870000000.0,"tau_s":1e-7}}
{"type":"InstrumentSnapshot","time":"...","point_id":"p000001","resource":"asg","snapshot":{"sequence_hash":"abc123"}}
{"type":"ArrayData","time":"...","point_id":"p000001","key":"photon_bins","shape":[1000],"unit":"count"}
{"type":"ArrayData","time":"...","point_id":"p000001","key":"analog_trace","shape":[2,5000],"unit":"V"}
{"type":"DataPoint","time":"...","point_id":"p000001","data":{"counts_mean":1234.5},"coords":{"mw_freq":2870000000.0,"tau_s":1e-7}}
{"type":"MeasurementCompleted","time":"...","point_id":"p000001","status":"ok"}
```

## 4. Dataset

当前默认同时使用 JSONL 审计层和 CSV 数据后端：

```text
data.jsonl       # DataPoint / scalar / small array / table-like records
points.jsonl     # MeasurementPoint lifecycle summary
events.jsonl     # full append-only event stream
metadata.json    # run-level metadata
tables/          # default CSV backend for viewer/analysis data
dataset_manifest.json
```

JSONL 保留的原因：

- 零额外二进制依赖。
- append-only，实验中断时更稳。
- 易调试，人和 AI worker 都能直接阅读。
- 适合作为事件流水、审计记录和与存储后端沟通的兼容层。

CSV 默认保存的原因：

- 同样不需要额外二进制依赖。
- 可以用普通工具直接打开。
- 能通过 `dataset_manifest.json` 暴露给 `RunReader` / `DatasetModel`。
- 是 viewer 和 analysis 的 mandatory baseline backend；Zarr 是 optional 高性能后端。

当前 storage 实现的 JSONL 记录格式如下：

```json
{
  "kind": "data_point",
  "point_id": "p000001",
  "coords": {"mw_freq_hz": 2870000000.0},
  "data": {"counts_mean": 1234.5, "photon_bins": [1, 2, 3]},
  "metadata": {"step_id": "read_counts"},
  "data_specs": {
    "counts_mean": {"kind": "scalar", "unit": null, "shape": []},
    "photon_bins": {"kind": "vector", "unit": null, "shape": [3]}
  },
  "time": "2026-06-26T..."
}
```

`points.jsonl` 是 point lifecycle 的 append-only snapshot。`MeasurementStarted`
会写入 `running` 记录，`MeasurementCompleted` 会追加最终状态；如果 run
关闭时仍有 running point，则追加 `partial` 记录。这样即使异常中断，也能从
events 和 points 中恢复已经开始、已经完成、以及部分完成的 point。

可用版增加 CSV bundle、Zarr，或用于兼容导出的 HDF5：

```text
/coords/mw_freq
/coords/tau
/data/counts
/attrs
```

如果数据 shape 未知，可以先写 appendable table：

```text
/points/index
/points/mw_freq
/points/tau
/points/counts
```

复杂测量点使用 point-centric layout：

```text
/points/index
/points/coords/mw_freq
/points/coords/tau_s
/points/scalars/counts_mean
/points/scalars/contrast
/points/status

/arrays/photon_bins/<point_id>
/arrays/analog_trace/<point_id>
/arrays/apd_time_tags/<point_id>

/snapshots/instruments/<point_id>/<resource_name>
/snapshots/sequences/<point_id>
/analysis/<point_id>
```

说明：

- scalar summary 用规则数组保存，方便快速画图和查询。
- raw array/trace 用 point_id 分组保存，允许每个点 shape 不同。
- point_id 是单调递增稳定 id，不依赖扫描坐标字符串。
- 高维扫描时不要求预分配完整 N 维数组，先使用 append-only point records。
- 如果扫描 shape 完整且规则，后续可以生成 `/grids/...` 作为派生数据。

## 4.2 Advanced Array Backend

当实验进入以下场景时，必须启用高级数组后端：

- 多维慢扫描，例如 `mw_freq_hz x tau_s x magnetic_field_v`。
- 每个慢扫描点对应一个快 trace，例如 photon bins、AI voltage trace、time tags。
- 多通道 trace，例如 `channel x time`。
- 每个 point 有大数组，例如 camera frame、long waveform、shot records。
- 需要交互式切片、剖面、heatmap、trace 查看。

推荐后端优先级：

1. **CSV bundle**：默认保存，作为轻量、可读、易导出的基线后端；用于 summary grids、point tables、小中型 traces。
2. **Zarr + xarray metadata**：optional 高性能方向，适合大数组、chunked slicing 和交互式 viewer。
3. **HDF5**：适合单文件打包和 HDFView/H5Web 等生态，但并发和部分追加更需要谨慎。
4. **JSONL**：继续保留为事件流水、审计日志、小数据 fallback，不再承载大型 trace。

重要要求：CSV 和 Zarr 都必须能表达 qulab 的多维数据需求。两者不是互斥设计，用户应能在 config 中选择：

```yaml
storage:
  backend: csv      # csv | zarr | jsonl | hdf5
```

或同时写入：

```yaml
storage:
  backends: [csv, zarr]
```

CSV 是当前高级 viewer/storage 的 mandatory baseline；即使用户请求 Zarr，运行目录也应保留 CSV 表格。Zarr 是 optional 高性能后端，应通过 config 持久启用，例如 `storage.backends: [csv, zarr]`。GUI 面板可以编辑这个配置，但 viewer 的 `Auto | CSV | Zarr` selector 只决定读取哪个已存在后端，不应修改原始 run 数据或重写配置。

JSONL 负责事件流水、审计和后端通信记录；CSV/Zarr 负责面向分析和 viewer 的数据阵列。

Prompt 008 followup makes CSV mandatory for the first advanced viewer/storage
implementation, and `RunStore` writes CSV by default. A run with advanced arrays therefore uses one shared
`dataset_manifest.json` and can expose the same logical data variables through
CSV and optional Zarr:

```text
tables/
  coords/mw_freq_hz.csv
  coords/tau_s.csv
  summaries/counts_mean.csv
  traces/photon_bins.csv
arrays.zarr/                 # optional, preferred when zarr is installed
dataset_manifest.json
```

The manifest declares `data_vars`, their `dims`, `kind`, `unit`, and per-backend
locations. `RunReader(..., backend="auto")` prefers Zarr when available and
falls back to CSV; `backend="csv"` forces the readable CSV path even when Zarr
exists.

Viewer plot-mode decisions must use these semantic indicators rather than data
key names. For example, a variable named `photon_bins` is displayed as a trace
because its manifest kind is `trace_grid`, not because of the name itself.
Trace grids may also be reduced over `time_s` for slow-scan line or heatmap
overviews when the remaining dimensions describe a scan grid.

推荐 run 目录：

```text
run/
  metadata.json
  events.jsonl
  points.jsonl
  data.jsonl                 # small data and compatibility records
  tables/                    # CSV backend
    points.csv
    summaries/
    traces/
  arrays.zarr/               # chunked advanced arrays
  dataset_manifest.json      # logical dataset descriptions
  run_index.sqlite           # root-level index remains outside or references run
```

推荐 Zarr logical layout：

```text
arrays.zarr/
  coords/
    mw_freq_hz               # shape: [n_mw]
    tau_s                    # shape: [n_tau]
    field_v                  # shape: [n_field]
    time_s                   # shape: [n_time]
    channel                  # shape: [n_channel]

  summaries/
    counts_mean              # shape: [n_mw, n_tau, n_field]
    counts_std               # shape: [n_mw, n_tau, n_field]

  traces/
    photon_bins              # shape: [n_mw, n_tau, n_field, n_time]
    analog_trace             # shape: [n_mw, n_tau, n_field, n_channel, n_time]

  point_records/
    point_id                 # optional mapping for irregular scans
    status
```

For irregular or interrupted scans, storage must also support point-centric ragged layout:

```text
arrays.zarr/points/<point_id>/photon_bins
arrays.zarr/points/<point_id>/analog_trace
```

规则：

- summary scalars should be grid-shaped when scan dimensions are known.
- raw traces can be chunked by slow scan dimensions and time.
- if scan shape is unknown or ragged, write point-centric arrays first and optionally derive regular grids later.
- JSONL remains the source of event history; Zarr/HDF5 stores heavy numeric arrays.
- SQLite stores only index, run path, data key, shape, dtype, uri, and coordinate metadata.

Recommended chunking:

```text
summary grid: chunks like (16, 16, 1)
trace grid:   chunks like (4, 4, 1, 1024) or (1, 1, 1, channel, time_chunk)
```

The exact chunk sizes should be configurable in `storage` config.

### CSV Backend Layout

CSV backend must be first-class, not merely an export afterthought. It should support the same logical dataset model as Zarr through normalized tables and manifest metadata.

Recommended layout:

```text
tables/
  points.csv
  data_keys.csv
  summaries/
    counts_mean.csv
    contrast.csv
  traces/
    photon_bins.csv
    analog_trace.csv
```

`points.csv`:

```text
point_id,status,mw_freq_hz,tau_s,field_v,started_at,completed_at
p000001,ok,2.870e9,1.0e-7,0.1,...
```

Scalar summary CSV can be long-form:

```text
point_id,mw_freq_hz,tau_s,field_v,key,value,unit
p000001,2.870e9,1.0e-7,0.1,counts_mean,1234,count
```

Trace CSV should be long-form to preserve arbitrary dimensions:

```text
point_id,mw_freq_hz,tau_s,channel,time_s,key,value,unit
p000001,2.870e9,1.0e-7,ai0,0.000001,analog_trace,0.012,V
```

For large traces, CSV may become large and slower than Zarr. This is acceptable as a compatibility/readability backend, but viewer must use chunking/streaming/pandas-like lazy reads where possible and warn when files are too large.

CSV backend rules:

- Must include headers.
- Must not lose point_id, coordinates, channel, time axis, unit, or key information.
- Must support scalar per point, vector trace per point, and matrix/multi-channel trace per point.
- Must be reconstructable into the same logical `DatasetModel` used by Zarr.
- Must be read-only safe for viewer.

### Unified Manifest

Both CSV and Zarr must be described by the same `dataset_manifest.json` abstraction:

```json
{
  "schema_version": 1,
  "preferred_backend": "zarr",
  "available_backends": ["csv", "zarr"],
  "coords": {
    "mw_freq_hz": {"unit": "Hz"},
    "tau_s": {"unit": "s"},
    "time_s": {"unit": "s"},
    "channel": {"unit": null}
  },
  "data_vars": {
    "counts_mean": {
      "kind": "scalar_grid",
      "dims": ["mw_freq_hz", "tau_s"],
      "unit": "count",
      "backends": {
        "csv": "tables/summaries/counts_mean.csv",
        "zarr": "arrays.zarr:/summaries/counts_mean"
      }
    },
    "analog_trace": {
      "kind": "trace_grid",
      "dims": ["mw_freq_hz", "tau_s", "channel", "time_s"],
      "unit": "V",
      "backends": {
        "csv": "tables/traces/analog_trace.csv",
        "zarr": "arrays.zarr:/traces/analog_trace"
      }
    }
  }
}
```

The viewer must use the manifest and `RunReader`, not hard-coded file paths.

## 4.1 平均值、动态序列、多通道数据

storage 不预设“实验只需要平均值”。每个 measurement point 可以同时保存 summary 和 raw data。

### 只保存平均值

```json
{
  "kind": "data_point",
  "point_id": "p000001",
  "coords": {"mw_freq_hz": 2870000000.0},
  "data": {"counts_mean": 1234.5, "counts_std": 12.3},
  "data_specs": {
    "counts_mean": {"kind": "scalar", "unit": "count"},
    "counts_std": {"kind": "scalar", "unit": "count"}
  }
}
```

### 保存完整动态测量序列

```json
{
  "kind": "data_point",
  "point_id": "p000002",
  "coords": {"tau_s": 1e-7},
  "data": {
    "counts_mean": 1200.0,
    "photon_bins": [12, 14, 9, 16],
    "time_axis_s": [0.0, 1e-6, 2e-6, 3e-6]
  },
  "data_specs": {
    "counts_mean": {"kind": "scalar", "unit": "count"},
    "photon_bins": {"kind": "vector", "unit": "count", "axis": "time_axis_s"},
    "time_axis_s": {"kind": "axis", "unit": "s"}
  }
}
```

### 保存多通道数据

```json
{
  "kind": "data_point",
  "point_id": "p000003",
  "data": {
    "analog_trace": [[0.01, 0.02, 0.03], [0.10, 0.11, 0.12]],
    "analog_channels": ["ai0", "ai1"],
    "time_axis_s": [0.0, 1e-6, 2e-6]
  },
  "data_specs": {
    "analog_trace": {
      "kind": "matrix",
      "unit": "V",
      "dims": ["channel", "time"],
      "axes": ["analog_channels", "time_axis_s"]
    }
  }
}
```

如果 raw array 很大，`data.jsonl` 中只保存引用：

```json
{
  "kind": "array_ref",
  "point_id": "p000004",
  "key": "camera_frame",
  "uri": "data.h5:/arrays/camera_frame/p000004",
  "shape": [512, 512],
  "dtype": "uint16",
  "unit": "adu"
}
```

## 5. 数据写入原则

1. executor 不直接写 HDF5。
2. storage 订阅 event。
3. 每个 data key 有单位和 shape。
4. 平均前原始数据是否保存由 config 决定。
5. 出错时仍保留已写数据和 metadata。
6. 每个扫描点必须有 `point_id`。
7. 一个扫描点可以产生多个数据对象。
8. 实时绘图可以使用 summary scalar，但不能替代 raw data 保存。
9. 中断实验必须保留已完成和部分完成的 point records。
10. 大数组存文件，小索引进数据库。
11. 数据库中的路径必须能定位到 run folder 和具体数据对象。

## 6. Measurement Point

`MeasurementPoint` 是高维扫描中的最小可追踪数据单元。

每个 point 至少包含：

- `point_id`
- scan coordinates
- started_at
- completed_at
- status
- scalar summaries
- optional raw arrays
- optional artifacts
- optional instrument snapshots
- optional sequence snapshot/hash

状态：

- `running`
- `ok`
- `failed`
- `skipped`
- `partial`

## 7. Data Kinds

必须支持：

- `scalar`：例如 counts_mean、contrast。
- `vector`：例如 photon bins。
- `matrix`：例如 two-channel analog trace。
- `ndarray`：例如 camera image 或多维采样数据。
- `table`：例如 shot records。
- `artifact`：例如 sequence file、preview plot、fit report。
- `metadata`：例如 instrument snapshot。

MVP 至少实现 scalar、vector、matrix、metadata；artifact 可以先保存路径和 hash。

## 8. SQLite Index

SQLite 索引用于快速查找和跨 run 查询，不用于保存大数组。

默认位置：

```text
runs/run_index.sqlite
```

建议表：

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    experiment_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    run_path TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE parameters (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value_json TEXT,
    unit TEXT,
    PRIMARY KEY (run_id, name)
);

CREATE TABLE data_keys (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    kind TEXT,
    unit TEXT,
    shape_json TEXT,
    uri TEXT,
    PRIMARY KEY (run_id, key)
);

CREATE TABLE points (
    run_id TEXT NOT NULL,
    point_id TEXT NOT NULL,
    status TEXT NOT NULL,
    coords_json TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (run_id, point_id)
);

CREATE TABLE artifacts (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT,
    uri TEXT NOT NULL,
    hash TEXT,
    PRIMARY KEY (run_id, name)
);
```

典型查询：

- 找到所有 `rabi` 实验 run。
- 找到某个 run 的数据目录。
- 找到包含 `counts_mean` 的 run。
- 找到某个参数范围内的 run。
- 打开某个 point 的 raw trace 文件引用。

原则：

- SQLite index 可以重建，真实数据以 run folder 文件为准。
- 每次 run 完成时更新 index。
- 实验运行中可以增量更新 index，但不能影响采集可靠性。
- 如果 SQLite 写入失败，不能导致已采集原始数据丢失。

## 9. Data Viewer Requirements

Qulab needs a domain-specific data viewer because generic HDF5/Zarr viewers can inspect arrays but do not understand experiment semantics well enough.

The viewer must support:

- Open a run folder from `runs/` or from `run_index.sqlite`.
- Open a parent folder and select any discovered run folder that contains
  `dataset_manifest.json` from the viewer side panel.
- Show metadata, config, resolved config, resources, sync plan, logs, and event timeline.
- List data keys with kind, unit, shape, backend URI.
- For 1D slow scan scalar data:
  - line plot.
- For 2D slow scan scalar data:
  - heatmap.
  - arbitrary line profile along either scan direction.
  - click point to inspect point metadata.
- For higher-dimensional slow scans:
  - choose one dimension for x line plot, or two dimensions for heatmap.
  - for any scalar dataset with two or more dimensions, both views must be
    available: a one-dimensional line slice and a two-dimensional heatmap slice.
  - selector controls must only expose dimensions not already used by the active
    plot axes.
  - all other dimensions become selectors/sliders/dropdowns.
  - viewer must use lazy loading and slicing, not load the full dataset into memory.
- For each-point trace data:
  - select a slow-scan point and display its trace.
  - support multi-channel traces with channel selector.
  - support point trace overlay for selected points.
- For interrupted/ragged runs:
  - show completed/partial/failed points distinctly.
  - do not corrupt or rewrite raw data.
- Export current view to PNG/CSV/NPZ where practical.

Performance requirements:

- Use lazy reads for Zarr/HDF5 arrays.
- Use the CSV backend for readable fallback and export-friendly datasets; use
  Zarr for large arrays where chunked slicing matters.
- Downsample or decimate large traces for display.
- Never modify raw data from the viewer by default.
- Run selection in the viewer must be read-only: loading another folder must not
  rewrite manifests, CSV tables, Zarr arrays, or JSONL audit files.
- Any derived analysis must be written as a new artifact, not overwrite raw arrays.

Possible third-party tools:

- HDFView / H5Web: good for inspecting HDF5 files, not experiment-aware.
- napari: good for image-like nD arrays, less natural for scan metadata and point traces.
- xarray + hvPlot/HoloViews/Datashader: strong for labeled N-D slicing and large data visualization.
- silx / pyqtgraph: useful for Qt scientific plotting.
- Matplotlib Qt canvas: acceptable fallback when pyqtgraph is not installed.

Recommendation:

- Use Zarr + xarray-style metadata for storage.
- Build a small Qulab-specific viewer on top of PyQt/PySide + pyqtgraph, with
  Matplotlib as a fallback, or a browser/dashboard stack later.
- Keep the storage reader/viewer backend independent from GUI so tests can validate slicing without opening windows.

Large stability datasets can be generated locally with:

```bash
PYTHONPATH=src python -m qulab.scripts.generate_large_stability_data
```

The generated CSV batch targets the 200MB-1GB range for manual stress testing.
For routine development, smaller synthetic runs should remain the default.
When testing optional Zarr support in a conda environment such as `mwcavity`, use:

```bash
conda run -n mwcavity env PYTHONPATH=src python -m qulab.scripts.generate_large_stability_data --root runs/advanced_test_data/large_stability_zarr_validation --force --include-zarr
```

For Zarr runs, `RunReader.get_data_var_metadata(...)` reads manifest and
coordinate arrays only. `SliceController` render paths then call backend
selection reads so Zarr loads only the requested line, heatmap, or trace slice.

当前实现使用 `runs/run_index.sqlite`，包含 `runs`、`data_keys`、`points`
和 `artifacts` 四张表。`RunStore.open()` upsert `runs` 行，`DataPoint`
upsert `data_keys` 行，`MeasurementStarted/MeasurementCompleted` upsert
`points` 行，`RunStore.close()` 更新 run 的最终状态和 `ended_at`。

SQLite 只是索引：如果 SQLite 写入失败，`events.jsonl`、`data.jsonl`、
`points.jsonl` 和 `metadata.json` 仍然继续写入。后续 HDF5/Zarr worker
可以把大数组写入 `data.h5` 或 `data.zarr`，并在 `data.jsonl` 中留下
`array_ref`，同时把 `data_keys.uri` 指向具体对象，例如
`data.h5:/arrays/analog_trace/p000004`。

## 13. Planned Derived Data and Live Compute Provenance

## 12.1 Sequence Generation Provenance (implemented)

Generated runs keep the original authoring `config.yaml`, compiled
`resolved_config.yaml`, compact `metadata.json.sequence_generation` records,
and per-plan artifacts under `artifacts/sequence_generation/<plan_id>/`:
`sequence_plan.yaml`, `provider_identity.json`, and `generation_log.txt`.
P9.2 independently stores the manifest, selected entry/file/hash, and copied
sequence artifact. Consequently a cache hit changes only `cache_hit`; it does
not remove any information needed to reconstruct a run.

`experiment_parameters` distinguishes `sequence_parameter` from
`sequence_coordinate`; `DataPoint.coords`, completed point records, and
`SequenceSelected.requested_coordinates` share the compiled scan coordinate.

实时计算/派生量框架规划见：

```text
docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md
```

数据模型原则：

- raw data 是第一优先级，必须按原始 `DataPoint`/array backend 保存。
- derived data 是单独的数据 key、event 或 artifact，不能覆盖 raw data。
- Live View 中可见的 derived quantity 如果配置为 `save: true`，RunStore 必须保存。
- 如果 derived quantity 只用于现场显示且 `save: false`，GUI 必须清楚标记为 live-only。
- 每个 derived output 都应记录 module provenance：
  - module name
  - module version
  - input keys
  - output keys
  - args/config
  - live 或 post-run
  - fail policy

规划中的 metadata 片段：

```json
{
  "analysis_modules": [
    {
      "name": "trace_summary",
      "module": "analysis_modules.trace_window_mean",
      "class": "TraceWindowMean",
      "version": "1",
      "enabled": true,
      "run_live": true,
      "save": true,
      "show": true,
      "inputs": ["pse_ai1_trace"],
      "outputs": ["signal_mean", "baseline_mean", "contrast"],
      "args": {}
    }
  ]
}
```
