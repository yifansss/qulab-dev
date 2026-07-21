# Prompt 010-followup P10.4: Analysis Provenance + Post-Run Recompute Worker

下面这份 prompt 可直接交给新的AI worker。目标是完成P10 Phase D：完善live analysis provenance，实现基于RunReader的post-run recompute CLI/API，把结果写入版本化analysis result group，扩展RunReader/Data Viewer读取raw、live-derived和recomputed-derived，同时绝不覆盖raw或既有analysis结果。

---

## /goal

对任意完成或部分完成run，用户可以：

```bash
python -m qulab.analysis.recompute --run <run_path> --module trace_summary
```

使用同一P10 module contract重新处理raw point data，保存为新的immutable result group，并记录module source/version/args/input hashes/timestamp。Raw JSONL/CSV/Zarr和既有derived结果保持byte-for-byte不变。

---

## 硬依赖

P10.1、P10.2完成。P10.3最好完成，以便Data Viewer category UI集成；如P10.3未完成，可先实现headless RunReader catalog并清楚handoff，不能虚构GUI。

开始前读取实际DerivedData storage、dataset manifest和RunReader APIs。

---

## 必须先阅读

1. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
2. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
3. `docs/DATA_MODEL.md`
4. `docs/DATA_VIEWER_REQUIREMENTS.md`
5. `workers/storage_worker.md`
6. `workers/qa_worker.md`
7. P10.1/P10.2/P10.3 handoffs
8. `src/qulab/storage/run_reader.py`
9. `src/qulab/storage/dataset_model.py`
10. `src/qulab/storage/slicing.py`
11. `src/qulab/storage/manifest.py`
12. `src/qulab/storage/csv_backend.py`
13. `src/qulab/storage/zarr_backend.py`
14. `src/qulab/analysis/` current implementation
15. run metadata/index code

---

## 严格范围

### 必须实现

- complete live module provenance schema；
- immutable recompute run/result IDs；
- recompute CLI/API；
- raw point reconstruction via RunReader/DatasetModel；
- module DAG or selected module dependency execution；
- versioned analysis result storage；
- append-only analysis history；
- raw/derived hash/lineage records；
- RunReader result-group discovery/selection；
- DatasetModel/SliceController access to recompute outputs；
- Data Viewer group/source display ifP10.3 available；
- compare live-derived/recomputed keys without collision；
- interrupted recompute atomicity/recovery；
- tests/docs。

### 不实现

- 不修改raw arrays/tables/JSONL/events；
- 不覆盖live-derived keys；
- 不复用RunStore打开原run为普通run写入；
- 不连接hardware；
- 不实现new formulas；
- 不实现async live queue；
- 不让CLI默认执行所有modules without explicit selection/plan；
- 不把recompute结果混入raw namespace。

---

## Recommended Layout

```text
src/qulab/analysis/recompute.py
src/qulab/analysis/result_store.py
src/qulab/analysis/lineage.py
```

Run folder：

```text
analysis/
  history.jsonl
  <result_id>/
    analysis_config.yaml
    metadata.json
    events.jsonl              # optional analysis-only statuses/errors
    data.jsonl
    dataset_manifest.json
    tables/
    arrays.zarr/              # optional if selected/available
```

Do not use ambiguous `derived/` files at run root that may collide with future versions.

建议tests：

```text
tests/unit/test_analysis_lineage.py
tests/unit/test_analysis_result_store.py
tests/unit/test_recompute_point_reader.py
tests/unit/test_recompute_cli.py
tests/unit/test_run_reader_analysis_groups.py
tests/integration/test_post_run_recompute.py
tests/integration/test_recompute_raw_immutability.py
tests/integration/test_recompute_viewer_slicing.py
```

---

## Result ID and Atomicity

默认result id：

```text
YYYYMMDD_HHMMSS_<module_or_plan>_<short_config_hash>
```

Rules：

- output目录已存在时fail，除非explicit new id；不提供in-place overwrite；
- 写到`analysis/.tmp_<uuid>`；
- complete validation后atomic rename；
- failure保留history failed record和可选diagnostic，但不暴露partial final group；
- stale temp可由`--cleanup-temp`显式清理，不自动删除未知用户目录；
- result metadata status `running|completed|failed|partial`；
- rerun same config仍创建new result by default，便于比较；
- optional `--reuse-if-identical`只在所有input/source/config hashes完全一致时可返回existing group，并明确报告。

---

## Recompute CLI

必须支持等价命令：

```bash
python -m qulab.analysis.recompute \
  --run runs/2026-.../run_id \
  --module trace_summary \
  --result-id trace_summary_window_v2 \
  --set signal_window_s='[1e-6,3e-6]' \
  --backend csv
```

建议选项：

```text
--run <path>                 required
--module <instance>          repeatable or selected dependency closure
--config <analysis yaml>     optional override/new plan
--result-id <id>
--backend csv|zarr|both
--set key=<yaml-safe-value>  explicit args override, no eval
--dry-run                    validate/list points/output keys, no write
--allow-partial              include completed points from failed/partial run
--reuse-if-identical
```

PowerShell和POSIX examples入docs。CLI return codes明确：0 success，2 config/validation，3 data/input，4 compute failure（或遵循项目现有CLI规范）。

禁止用Python `eval` parse `--set`；使用YAML scalar/list safe parser并经过argument validation。

---

## Raw Point Reconstruction

Recompute必须通过RunReader/DatasetModel公共API读取，不ad hoc直接读tables/arrays。

需要一个point iterator contract：

```python
reader.iter_compute_points(
    input_keys,
    *,
    include_status=("ok",),
) -> Iterator[ComputePoint]
```

Rules：

- one ComputePoint per measurement point；
- merge requested raw keys from possibly multiplerecords；
- preserve point_id/coords/timestamp/metadata；
- missing input per point按module fail policy；
- default只读取source_kind raw；
- module dependency closure可读取本次recompute中上游derived；
- 使用existing live-derived作为input必须explicit source selection，避免version ambiguity；
- lazy/chunked wherebackend supports；
- 不full-load大型run if only subset keys needed；
- trace time/channel coords preserved；
- partial run requires`--allow-partial`并记录included/excluded counts。

如果current RunReader不能逐点重建multi-event raw data，扩展统一API并加legacy JSONL/CSV/Zarr tests。

---

## Module Selection and Dependencies

`--module X`默认执行X及其enabled dependencies。规则：

- dependency output来自同一recompute result；
- raw inputs来自raw group；
- live-derived input必须通过explicit selector如`live:<key>`；
- recompute group input如`analysis:<result_id>:<key>`必须explicit；
- ambiguity error；
- selected module must `run_post:true` unless explicit `--force-run-post`，该flag仅跳过eligibility，不跳过contract validation；
- module setup run_context标记`mode: post`和source run/result；
- close always。

---

## Result Storage

Result group storesonly derived outputs andanalysis diagnostics。Manifest data vars include：

```json
{
  "source_kind": "derived",
  "analysis_mode": "post",
  "source_module": "trace_summary",
  "module_version": "2",
  "result_id": "...",
  "input_lineage": ["raw:pse_ai1_trace"]
}
```

Storage：

- JSONL analysis audit baseline；
- CSV mandatory baseline；
- Zarr optional；
- point ids/coords align source run；
- no raw copies except optional hashes/index；
- quality/units/metadata preserved；
- output key collisions withinresult error；
- same key acrosslive/recompute groups allowed becausegroup identity explicit。

Run root `dataset_manifest.json`不必重写来merge groups。推荐在`analysis/history.jsonl`注册result group；RunReader发现root raw manifest + analysis child manifests。若更新root metadata summary，必须atomic并保留raw fields。

---

## Provenance and Lineage

Live module metadata和recompute result metadata至少：

- module instance/import target/class/function；
- module declared/runtime version；
- source path/hash；
- inputs/effective outputs/namespace；
- normalized args；
- dependency graph；
- run_live/run_post/show/save/fail policy；
- Qulab version/git commit ifavailable；
- source run id/path；
- result id/mode/start/end/status；
- raw dataset manifest hash；
- relevant raw files/group hashes或stable data fingerprint；
- point included/skipped/failed counts；
- backend；
- error count；
- parent analysis group inputs；
- command/override summary withoutsecrets。

Do not copy environment variables, credentials, or full arbitrary `sys.path` into provenance.

`analysis/history.jsonl` append-only recordsstart/completion/failure events。Metadata summary may listresult IDs/status buthistory is authority。

---

## Raw Immutability Verification

Tests capture hashes before/after for：

```text
config.yaml
resolved_config.yaml
events.jsonl
data.jsonl
points.jsonl
dataset_manifest.json
tables/**
arrays.zarr/**
artifacts/sequences/**
```

Recompute may append/createonly under`analysis/` and optional atomic metadata summary explicitly documented。Raw hashes must remain unchanged。

No file mode that opensraw Zarr/CSV forwrite。

---

## RunReader/DatasetModel Integration

Add group-aware catalog：

```python
reader.list_data_groups()
reader.list_data_keys(group="raw")
reader.list_data_keys(group="live")
reader.list_data_keys(group="analysis:<result_id>")
reader.get_data_var(key, group=...)
```

Backward compatibility：existing call withoutgroup usescurrentraw+saved-live behavior or documenteddefault, but ambiguity must not silently chooseone ofmultipleanalysis results。

`DataKeyInfo`增加source kind/group/module/version。SliceController接受group-qualified data key或DatasetModel selection。

Data Viewer categories：

```text
Raw
Live Derived
Recomputed
  result_id A
  result_id B
```

Viewer read-only。可比较compatible live/recomputed scalars，但不能“promote”或overwrite raw。

---

## Failure Policy

- default module fail policy沿P10.1 plan；
- recompute failure不改变source run status；
- result group status failed/partial；
- raw missing/invalid givesdata error；
- one point warn/skip may continue；
- `fail` stops result generation；
- atomic final group只对completed；如果支持partial final，必须explicit `--keep-partial`并清楚status；MVP可不支持。

---

## Tests

至少覆盖：

1. CLI dry-run no writes。
2. valid scalar recompute。
3. trace input recompute。
4. dependency closure A->B。
5. run_post eligibility。
6. args override safe parse/validation。
7. missing input warn/skip/fail。
8. partial run gate。
9. result id collision/no overwrite。
10. failed temp not exposed final。
11. history start/completed/failed records。
12. metadata source/module/config/input lineage。
13. CSV result read/slice。
14. optional Zarr result read/slice。
15. group catalog/ambiguity/default compatibility。
16. same key live vs recompute groups coexist。
17. viewer category model。
18. source raw hashes unchanged。
19. P9 sequence artifacts/provenance unchanged。
20. legacy JSONL-only run recompute ifinputsavailable。
21. full suite。

---

## 文档更新

更新Live Compute plan、Data Model、Data Viewer Requirements、Implementation Order。标记P10 Phase D完成；async Phase E保持planned。

---

## 验收命令

```bash
python -m pytest tests/unit/test_analysis_lineage.py
python -m pytest tests/unit/test_analysis_result_store.py
python -m pytest tests/unit/test_recompute_point_reader.py
python -m pytest tests/unit/test_recompute_cli.py
python -m pytest tests/unit/test_run_reader_analysis_groups.py
python -m pytest tests/integration/test_post_run_recompute.py
python -m pytest tests/integration/test_recompute_raw_immutability.py
python -m pytest tests/integration/test_recompute_viewer_slicing.py
python -m pytest
```

实际运行CLI dry-run和一次small synthetic recompute，报告result path/group/keys。

---

## 完成定义

- completed run可用同一module contract重算；
- result group versioned/atomic/可读取；
- raw和live-derived不被覆盖；
- provenance/lineage足以复现；
- viewer可区分raw/live/recomputed；
- P9 sequence artifacts保持不变；
- full suite通过。

---

## 最终汇报

1. 修改文件/public APIs。
2. CLI示例和return behavior。
3. result folder/manifest格式。
4. lineage/hash策略。
5. RunReader/viewer group semantics。
6. raw immutability hash结果。
7. tests。
8. 给P10.5的storage/threading boundary handoff。

