# Storage Worker Specification

## Mission

实现每次实验的完整可复现存储。

## Must Read

- `docs/DATA_MODEL.md`
- `docs/CONFIG_SCHEMA.md`

## Deliverables

1. `storage/run_store.py`
2. `storage/metadata.py`
3. `storage/events.py`
4. `storage/dataset.py`
5. tests

## Required Behavior

每次 run 创建：

```text
runs/YYYY-MM-DD/YYYYMMDD_HHMMSS_<experiment_name>/
```

写入：

- `config.yaml`
- `resolved_config.yaml`
- `metadata.json`
- `events.jsonl`
- `data.jsonl`
- `points.jsonl`
- `logs.txt`
- `run_index.sqlite` at the storage root

本阶段默认保留 `data.jsonl` 作为事件/审计/兼容沟通层，同时写入 CSV backend
和 `dataset_manifest.json` 作为 viewer/analysis 的默认数据入口。CSV 不要求额外
二进制依赖，逐行表格可读；Zarr 是 optional 高性能后端。后续可以增加 HDF5/Zarr
后端：小 summary 继续写 JSONL/CSV，大数组写入 `arrays.zarr` 或兼容导出的
`data.h5`，并在 manifest 和 SQLite `data_keys.uri` 中保存引用。

Prompt 008 followup adds the advanced read/view path:

- CSV backend is the default mandatory baseline and stores readable tables
  under `tables/`.
- Zarr backend is optional and preferred by `RunReader(..., backend="auto")`
  when the optional `zarr` dependency is installed.
- Both backends share `dataset_manifest.json`, `RunReader`, `DatasetModel`, and
  `SliceController`.
- JSONL/SQLite remain the audit and index layer; advanced CSV/Zarr files provide
  multidimensional viewer-ready arrays and per-point traces.

## Rules

1. event log append-only。
2. metadata 状态必须在 failed/completed 时更新。
3. 数据写入失败必须发出 error。
4. 不把大型 run 输出提交到 git。
5. tests 使用临时目录。
6. 每个扫描点用 point_id 关联 scalar、array、snapshot、artifact。
7. 高维扫描默认 append-only，不要求预分配完整 N 维数组。
8. core/executor 不导入 storage；storage 通过 `EventBus.subscribe(store.handle_event)` 接入。
9. SQLite 索引失败不能破坏已经写入的 JSONL 和 metadata 文件。

## Tests

覆盖：

- run dir naming。
- metadata create/update。
- events jsonl parseable。
- data point append。
- array data append。
- multiple outputs for one point_id。
- partial point after failure。
- failure still preserves files。
