# Prompt 002: Storage RunStore Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在已经完成的 core/event/dry-run 基础上，实现自动数据保存闭环：RunStore、metadata、events.jsonl、data 文件、point-centric 数据模型和测试。这个 worker 不应该接触真实硬件，不应该实现 GUI，不应该实现 pycontrol adapter。

---

## /goal

在当前 `qulab` 项目中实现第二阶段 storage 基础：建立可测试、无硬件依赖的 RunStore，使 `ExperimentExecutor` 产生的结构化事件可以自动写入一次实验运行目录。必须支持 metadata、append-only events.jsonl、point-centric data 存储、复杂 measurement point 的 scalar/array/metadata 保存，以及轻量 SQLite run index。用单元测试和集成 dry-run 测试证明数据在实验完成、失败、中断式异常情况下都能保留。完成后 `python -m pytest` 必须通过。

成功标准：

1. 阅读并遵守项目蓝图、数据模型和 storage worker 规范。
2. 实现 `src/qulab/storage/` 下的 RunStore 基础模块。
3. 不导入 PyQt、pycontrol、NI、ASG SDK 或任何真实硬件依赖。
4. 不修改 core API，除非为了 storage 必须做小而清晰的兼容增强。
5. 每次 run 创建唯一 run 目录。
6. 写入：
   - `config.yaml`，如果调用方提供 config。
   - `resolved_config.yaml`，如果调用方提供 resolved config。
   - `metadata.json`
   - `events.jsonl`
   - `data.jsonl` 或 `data.h5`
   - `points.jsonl`
   - `logs.txt`，可先为空或由 log event 追加。
   - `run_index.sqlite`，位于 storage root 或 runs root，用于索引 run/points/data_keys/artifacts。
7. MVP 可以优先使用 JSONL 作为数据后端，若环境已有 `h5py` 可加 HDF5，但不能让默认测试依赖非必要二进制库。SQLite 使用 Python 标准库 `sqlite3`。
8. 支持 point-centric 数据：
   - 每个 `MeasurementStarted` 建立 point record。
   - `DataPoint` 按 `point_id` 关联 coords/data/metadata。
   - array/list 数据可以保存。
   - failed/partial point 也能记录。
9. 支持 RunStore 作为 EventBus subscriber 使用。
10. 增加测试，覆盖 run 目录创建、metadata 更新、events.jsonl 可解析、DataPoint 保存、复杂 point 多输出、失败后文件仍保留。
11. 增加 SQLite index 测试，覆盖 run row、data_keys row、points row。
12. 更新必要文档，说明本阶段实际采用的数据文件格式、SQLite 索引方式和后续 HDF5/Zarr 扩展路径。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读以下文件：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DATA_MODEL.md`
4. `docs/CONFIG_SCHEMA.md`
5. `docs/IMPLEMENTATION_ORDER.md`
6. `workers/storage_worker.md`
7. `workers/core_worker.md`
8. `workers/qa_worker.md`

同时查看当前 core 实现：

```text
src/qulab/core/parameter.py
src/qulab/core/events.py
src/qulab/core/procedure.py
src/qulab/core/context.py
src/qulab/core/executor.py
src/qulab/core/__init__.py
```

重点确认：

- 当前 Event 对象如何转 dict。
- EventBus 如何 subscribe/emit。
- DataPoint、MeasurementStarted、MeasurementCompleted、ErrorRaised 的字段。
- ExperimentExecutor 的失败和 cleanup 行为。

---

## 当前项目目录

项目根目录：

```text
/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab
```

storage 代码应放在：

```text
src/qulab/storage/
```

测试应放在：

```text
tests/unit/
tests/integration/
```

不要修改：

```text
../pycontrol
../panel(basic)
```

不要在默认测试中写入真实项目 `runs/`。测试必须使用 `tmp_path`。

---

## 推荐实现文件

请创建或更新以下文件：

```text
src/qulab/storage/run_store.py
src/qulab/storage/metadata.py
src/qulab/storage/events.py
src/qulab/storage/dataset.py
src/qulab/storage/index.py
src/qulab/storage/__init__.py

tests/unit/test_run_store.py
tests/unit/test_storage_events.py
tests/integration/test_dry_run_storage.py
```

可以根据实际需要增加：

```text
src/qulab/storage/errors.py
src/qulab/storage/paths.py
```

---

## 具体实现要求

### 1. Run Directory

实现 `RunStore`，最小 API 建议：

```python
class RunStore:
    def __init__(
        self,
        root: Path | str = "runs",
        experiment_name: str = "experiment",
        config: dict | None = None,
        resolved_config: dict | None = None,
        run_id: str | None = None,
    ) -> None: ...

    @property
    def run_path(self) -> Path: ...

    def open(self) -> None: ...
    def handle_event(self, event: Event) -> None: ...
    def close(self, status: str = "completed") -> None: ...
```

目录格式：

```text
<root>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<experiment_name>/
```

如果 `run_id` 显式传入，则可以使用稳定目录名，方便测试。

要求：

- experiment_name 需要安全化，使用 snake/kebab compatible 字符，避免空格和路径分隔符。
- 目录已存在时要避免覆盖，可以追加 suffix。
- 测试中 root 使用 `tmp_path`。

### 2. Metadata

实现 metadata create/update。

`metadata.json` 至少包含：

```json
{
  "schema_version": 1,
  "run_id": "...",
  "experiment_name": "...",
  "started_at": "...",
  "ended_at": null,
  "status": "running",
  "qulab_version": "0.0.0",
  "resources": {},
  "sync": {},
  "data_keys": [],
  "point_count": 0,
  "error_count": 0
}
```

要求：

- `open()` 时写入 running metadata。
- `close("completed")` 时更新 ended_at/status。
- 收到 `ErrorRaised` 时 error_count 增加，status 可保持 running，最终 close 时改 failed。
- 收到 `DataPoint` 时更新 data_keys。
- 收到 `MeasurementCompleted` 时更新 point_count 或 completed_point_count。

### 3. Events JSONL

实现 append-only `events.jsonl`：

- 每个 event 一行 JSON。
- 每行必须可以 `json.loads`。
- Event dict 中如果包含 numpy 类型或 Path，需要转成 JSON-safe 类型。
- 每次写入后 flush，保证实验崩溃时已有事件保留。

建议提供：

```python
def event_to_jsonable(event: Event) -> dict: ...
```

### 4. Dataset MVP

MVP 可以优先实现 `data.jsonl`，后续再接 HDF5。不要因为 h5py 缺失让默认测试失败。

`data.jsonl` 每行可以是：

```json
{
  "kind": "data_point",
  "point_id": "p000001",
  "coords": {"mw_freq_hz": 2870000000.0, "tau_s": 1e-7},
  "data": {"counts_mean": 1234.5, "photon_bins": [1, 2, 3]},
  "metadata": {"average_index": 0},
  "time": "..."
}
```

复杂 point record 可以维护内存索引并定期写 `points.jsonl`：

```json
{
  "point_id": "p000001",
  "status": "ok",
  "coords": {"mw_freq_hz": 2870000000.0, "tau_s": 1e-7},
  "data_keys": ["counts_mean", "photon_bins"],
  "started_at": "...",
  "completed_at": "..."
}
```

最低要求：

- `DataPoint` 写入 `data.jsonl`。
- `MeasurementStarted/Completed` 写入 point record 或至少 events.jsonl。
- 一个 point_id 可以出现多条 DataPoint。
- list/dict 数据可保存。

### 4.1 Data Specs

每条 DataPoint 如果能推断 data spec，应记录 key 的 kind/unit/shape 信息。MVP 至少推断：

- scalar：int/float/str/bool。
- vector：一维 list。
- matrix：二维 list。
- object：dict 或未知结构。

这些 spec 应写入 metadata 的 `data_keys` 或 SQLite `data_keys` 表。平均值、完整动态序列、多通道数据都通过 data spec 描述，而不是写死在 storage 代码里。

### 4.2 大数组策略

MVP 允许小数组直接写入 `data.jsonl`。后续 HDF5/Zarr 后端接入后，大数组应写为外部引用：

```json
{
  "kind": "array_ref",
  "point_id": "p000004",
  "key": "analog_trace",
  "uri": "data.h5:/arrays/analog_trace/p000004",
  "shape": [2, 5000],
  "dtype": "float64",
  "unit": "V"
}
```

### 5. Config Snapshots

如果调用方传入 `config` 和 `resolved_config`：

- 写入 `config.yaml`
- 写入 `resolved_config.yaml`

如果没传入：

- 可以不创建，或创建空 `{}`。
- 需要测试或文档说明行为。

使用 `yaml.safe_dump`，项目已有 `pyyaml` 依赖。

### 6. EventBus Integration

RunStore 必须可以这样使用：

```python
bus = EventBus()
store = RunStore(root=tmp_path, experiment_name="dry_run_rabi")
store.open()
bus.subscribe(store.handle_event)

executor = ExperimentExecutor(procedure, ctx, bus, dry_run=True)
executor.run()

store.close(status=executor.state)
```

可以提供 convenience helper，但不要让 executor 直接依赖 storage。

重要边界：

- storage 订阅 EventBus。
- executor 不导入 storage。
- core 不导入 storage。

### 7. SQLite Run Index

实现轻量 SQLite index，使用 Python 标准库 `sqlite3`，不要引入外部数据库依赖。

默认位置：

```text
<root>/run_index.sqlite
```

最低表：

```text
runs(run_id, experiment_name, started_at, ended_at, status, run_path, metadata_json)
data_keys(run_id, key, kind, unit, shape_json, uri)
points(run_id, point_id, status, coords_json, started_at, completed_at)
artifacts(run_id, name, kind, uri, hash)
```

要求：

- `RunStore.open()` 插入或更新 runs row。
- `DataPoint` 更新 data_keys。
- `MeasurementStarted/Completed` 更新 points。
- `RunStore.close()` 更新 runs status/ended_at。
- SQLite 写入失败不能导致 `events.jsonl` 和 `data.jsonl` 已有数据丢失。

可以实现：

```python
class RunIndex:
    def __init__(self, path: Path | str) -> None: ...
    def initialize(self) -> None: ...
    def upsert_run(self, ...) -> None: ...
    def upsert_point(self, ...) -> None: ...
    def upsert_data_key(self, ...) -> None: ...
```

### 8. Error and Partial Data

如果实验失败：

- `events.jsonl` 保留已写事件。
- `metadata.json` 最终 status 为 `failed`。
- 已收到的 DataPoint 仍保留在 `data.jsonl`。
- 如果 point started 但未 completed，应能从 events 或 points 记录看出 partial。

测试中需要构造一个会抛异常的 ActionStep，并确认 cleanup/core 行为仍通过，同时 storage 有 ErrorRaised 和已写数据。

---

## 推荐集成测试示例

实现后，类似测试应该可行：

```python
from qulab.core import (
    ActionStep,
    EventBus,
    ExperimentContext,
    ExperimentExecutor,
    MeasurementStep,
    P,
    Procedure,
    RunStep,
    ScanStep,
    ScanValues,
)
from qulab.storage import RunStore

def read_counts(freq_hz):
    return {"counts_mean": 1000.0, "photon_bins": [1, 2, 3]}

procedure = Procedure(
    name="storage_dry_run",
    body=[
        ScanStep(
            name="mw_freq_hz",
            values=ScanValues.linspace(2.86e9, 2.88e9, 3),
            body=[
                MeasurementStep(
                    name="point",
                    body=[
                        RunStep(
                            name="readout",
                            body=[
                                ActionStep(
                                    name="read_counts",
                                    action=read_counts,
                                    kwargs={"freq_hz": P("mw_freq_hz")},
                                    save_as="counts",
                                )
                            ],
                        )
                    ],
                )
            ],
        )
    ],
)

bus = EventBus()
store = RunStore(root=tmp_path, experiment_name="storage_dry_run")
store.open()
bus.subscribe(store.handle_event)

ctx = ExperimentContext()
executor = ExperimentExecutor(procedure, ctx, bus, dry_run=True)
executor.run()
store.close(status=executor.state)

assert (store.run_path / "metadata.json").exists()
assert (store.run_path / "events.jsonl").exists()
assert (store.run_path / "data.jsonl").exists()
```

---

## 严格禁止

- 不要实现 GUI。
- 不要连接真实硬件。
- 不要导入 `nidaqmx`、`pyvisa`、`serial`、ASG DLL 或 `../pycontrol`。
- 不要让 core 依赖 storage。
- 不要让 executor 直接写文件。
- 不要在测试中写入项目根目录下的真实 `runs/`。
- 不要吞异常。
- 不要为了 HDF5 引入必须联网安装的新依赖。
- 不要提交大数据文件。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.storage import RunStore; print(RunStore.__name__)"
```

如果添加了可选 HDF5 后端，也必须保证没有 h5py 时默认测试仍能通过，或者 h5py 只在 optional test 中使用。

---

## 文档更新要求

完成后至少更新：

```text
docs/DATA_MODEL.md
workers/storage_worker.md
```

如果实际文件格式与蓝图不同，例如 MVP 使用 `data.jsonl` 而不是 `data.h5`，必须在文档中明确：

- MVP 当前格式。
- 为什么这样做。
- 后续如何扩展到 HDF5/Zarr。

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 实现了哪些对象和文件格式。
3. 运行了哪些验证命令，结果是什么。
4. 是否保持了 core/storage 解耦。
5. 还没做什么，明确留给后续 worker。
6. 是否修改了公共 API。

---

## 后续 worker 依赖

这个 worker 完成后，后续 worker 可以继续：

- config worker：把 YAML config 解析为 Procedure，并把原始 config 交给 RunStore 保存。
- plotting worker：订阅 EventBus 或读取 data.jsonl 实时/离线绘图。
- adapter worker：把 mock callable/resource method 替换为 capability/resource 调用。
- gui worker：显示 run path、events log、data summary。
