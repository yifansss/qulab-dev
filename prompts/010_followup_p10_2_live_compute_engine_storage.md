# Prompt 010-followup P10.2: Live Compute Engine + Derived Storage Worker

下面这份 prompt 可直接交给新的AI worker。目标是完成P10 Phase B：实现同步轻量LiveComputeEngine、queued EventBus re-emit、`DerivedData`/`AnalysisStatus`事件、per-point input aggregation和module DAG执行、fail policy、conditional RunStore storage，以及runner/controller lifecycle。此worker不做GUI、不做post-run recompute、不做async queue。

---

## /goal

端到端事件流：

```text
raw DataPoint
  -> raw stored first
  -> point accumulator
  -> ready modules in dependency order
  -> DerivedData event
      -> saved conditionally
      -> downstream modules may consume output
      -> future Live View consumes event
```

Raw data必须始终优先保存；module失败不能静默覆盖或丢失raw。`warn|skip|fail`语义稳定且可测试。

---

## 硬依赖

P10.1完成并通过。读取实际AnalysisPlan、registry、module adapter和issue APIs，不复制schema/registry。

P9.1/P9.2与可选P9.3 preparation仍须兼容。P10.2避免修改P9.3C GUI-owned files。

---

## 必须先阅读

1. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
2. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
3. `docs/DATA_MODEL.md`
4. `workers/core_worker.md`
5. `workers/storage_worker.md`
6. `workers/qa_worker.md`
7. P10.1 implementation/handoff
8. `src/qulab/core/events.py`
9. `src/qulab/core/executor.py`
10. `src/qulab/config/runner.py`
11. `src/qulab/gui/controller.py`
12. `src/qulab/storage/run_store.py`
13. `src/qulab/storage/advanced_writer.py`
14. `src/qulab/storage/dataset.py`
15. EventBus and RunStore tests

---

## 严格范围

### 必须实现

- queued non-recursive EventBus dispatch；
- `DerivedData` event；
- `AnalysisStatus` event；
- synchronous LiveComputeEngine；
- per-point raw/derived accumulator；
- module DAG readiness/exactly-once execution；
- module setup/process/close lifecycle；
- output/result validation；
- warn/skip/fail handling；
- show/save/live-only semantics；
- conditional RunStore derived writes；
- data specs/manifest raw-vs-derived metadata；
- runner/controller integration；
- engine status/provenance summary；
- tests/docs/example dry-run。

### 不实现

- 不实现Qt/Live View；
- 不实现post-run recompute；
- 不实现worker thread/process或bounded queue；
- 不实现具体实验公式；
- 不允许module hardware access；
- 不改变P9 SequenceSelected semantics；
- 不让derived覆盖raw key；
- 不把live-only derived payload写入event/data files。

---

## 推荐模块

```text
src/qulab/analysis/engine.py
src/qulab/analysis/runtime.py
src/qulab/analysis/events.py   # 或core/events.py，选择一个canonical export
```

建议tests：

```text
tests/unit/test_event_bus_queued_emit.py
tests/unit/test_derived_data_event.py
tests/unit/test_live_compute_engine.py
tests/unit/test_live_compute_dependencies.py
tests/unit/test_live_compute_fail_policy.py
tests/unit/test_live_compute_runstore.py
tests/integration/test_live_compute_dry_run.py
tests/integration/test_live_compute_sequence_plan_run.py
```

---

## EventBus Queued Re-Emit

当前同步EventBus必须支持subscriber在处理raw event时emit derived event，但不能递归dispatch导致顺序混乱。

要求语义：

```text
emit(raw)
  subscriber A handles raw
  subscriber B handles raw and queues derived
  subscriber C handles raw
  then all subscribers handle derived
```

实现可以使用internal deque + `_dispatching` guard。P10.2仍是单线程，不需要async thread safety；P10.5再扩展。

Rules：

- event order稳定；
- nested emit queued FIFO；
- subscriber list snapshot semantics与当前兼容；
- subscriber exception传播，不丢失already emitted event history；
- no infinite loop protection可设reasonable max/depth diagnostics，但engine必须ignore DerivedData；
- existing EventBus tests不回归。

Subscription order在runner/controller必须为：

1. RunStore；
2. LiveComputeEngine；
3. external/GUI callback。

因此raw先由RunStore保存；queued DerivedData在raw所有subscriber处理后再分发。

---

## Event Contracts

推荐`DerivedData`：

```python
@dataclass
class DerivedData(Event):
    point_id: str = ""
    coords: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    source_module: str = ""
    module_version: str = ""
    input_keys: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    units: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    save: bool = True
    show: bool = False
    run_mode: str = "live"
    latency_s: float | None = None
```

`AnalysisStatus`：

```python
@dataclass
class AnalysisStatus(Event):
    module: str = ""
    state: str = "idle"
    point_id: str | None = None
    message: str | None = None
    latency_s: float | None = None
    queue_depth: int = 0
    error_type: str | None = None
    fail_policy: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

同步states至少：`setup|ready|running|success|skipped|warning|failed|closed`。

Events必须JSON-safe并public export。Derived event不伪装成raw DataPoint；GUI/storage不通过metadata猜kind。

---

## Engine Lifecycle

推荐API：

```python
engine = LiveComputeEngine(plan, registry, event_bus)
engine.setup(run_context)
event_bus.subscribe(engine.handle_event)
...
engine.close()
```

Setup：

- instantiate enabled `run_live` modules；
- call setup按topological/config order；
- emit status；
- setup fail按module policy处理；`fail`阻止run，raw acquisition尚未开始；
- run_context JSON-safe，包含run id/config/parameter/sequence plan summaries，不包含hardware driver对象。

Close：

- 每个成功setup的module调用close，即使executor失败；
- close error产生status/log，默认不覆盖已有hardware failure；
- idempotent；
- runner先close engine再close RunStore，使final statuses可存储。

---

## Point Aggregation and Readiness

一个measurement可发多个raw DataPoint。Engine按`point_id`累积：

```text
point_id -> coords + merged raw/derived values + executed modules
```

Rules：

- 默认只处理有point_id的raw DataPoint；setup/run-level point_id None忽略并status/debug；
- raw keys merge但同point同key不同value是collision/error，不静默覆盖；
- coords必须一致；不一致error；
- module在所有effective inputs可用时执行；
- 每module每point exactly once；
- result合并后可能使下游module ready；
- DAG topological deterministic；
- DerivedData event不作为新的raw event进入engine，但engine内部将result加入accumulator并触发downstream；
- MeasurementCompleted时对未执行module检查missing inputs，按policy产生skipped/warning/fail；
- point完成后释放accumulator，避免长run内存增长；
- MeasurementCompleted可能在derived queued event之后，queued FIFO tests确保合理顺序。

若raw DataPoint在MeasurementStarted前出现，允许创建accumulator但记录warning或按现有executor行为处理。

---

## Result Validation

在emit前：

- normalize ComputeResult/mapping；
- data non-empty或None代表no output/skip，语义明确；
- keys必须等于/属于declared effective outputs；extra key error；
- namespace映射只做一次；
- raw/previous derived key collision error；
- values/units/metadata/quality可JSON/storage serialize；
- module不能返回输入mapping同一mutable对象并被后续修改；framework深拷贝/normalize；
- units keys必须是output subset；
- output size可有reasonable warning但不限制合法trace；
- latency使用monotonic clock。

---

## Fail Policies

### warn

- emit AnalysisStatus warning；
-记录analysis error；
- 当前module该point无output；
- run继续；
- dependent modules最终missing input并按各自policy处理。

### skip

- emit skipped status，GUI可见但普通operator log可低噪声；
- 当前point无output；
- run继续。

### fail

- emit failed status；
- raise `LiveComputeError`；
- EventBus subscriber exception传播到executor action/DataPoint emit；
- 因RunStore subscriber先执行，当前raw event已经持久化；
- executor发ErrorRaised并cleanup；
- final run failed。

不要把compute fail伪装成hardware error；metadata分别计数。

---

## Show/Save/Emit Semantics

- module `show`决定GUI默认选择，不决定是否计算；
- module `save`和global save决定DerivedData.save；
- `show:true, save:false` -> event供live callback，但RunStore不得写events.jsonl/data.jsonl/CSV/Zarr；
- `show:false, save:true` -> event持久化但GUI默认隐藏；
- `emit_events:false`：若module save/show都不需要event，engine可内部处理；但为了storage统一，建议validation要求save/show时emit；契约必须清楚；
- status events可存analysis diagnostics，但不进入data vars。

RunStore `handle_event`在写generic event log前识别live-only DerivedData并skip payload persistence。不得先写events.jsonl再说live-only。

---

## RunStore Derived Storage

Saved DerivedData应通过与DataPoint兼容的dataset writer路径，但保留source metadata：

- data.jsonl记录kind `derived_data`或等价明确kind；
- advanced CSV/Zarr写入同logical data vars；
- dataset manifest var记录`source_kind: derived`、`source_module`、`module_version`；
- metadata data specs区分raw/derived；
- raw key永不覆盖；
- point record data_keys可包含saved derived key；
- live-only output不出现在completed RunReader catalog；
- `analysis_error_count`与`error_count`分开；
- optional `analysis_status.jsonl`可记录module statuses，但不能包含large result payload。

Metadata最小summary：module name/path/version/source hash/enabled/run_live/show/save/fail policy/inputs/effective outputs/args。

如果同一个derived key由后续recompute产生，P10.4将使用独立group；本阶段不处理覆盖。

---

## Runner/Controller Integration

`run_dry_config()`和`OperatorController.start_run()`：

1. Prepare/parse analysis plan。
2. Create EventBus和RunStore。
3. Open RunStore。
4. Subscribe RunStore。
5. Create/setup LiveComputeEngine。
6. Subscribe engine。
7. Subscribe external/GUI callback。
8. Connect hardware only afterall preflight/setup成功。
9. Execute。
10. Disconnect/cleanup。
11. Close engine。
12. Close store。

如果engine setup fail before executor，store可记录failed preparation/run或cleanly close；hardware不得connect。

P9 generated sequence config与analysis config必须在同一次run工作。SequenceSelected和DerivedData按point_id/coords独立关联。

---

## Example Test Module/Config

新增无具体实验公式的generic example：raw `counts`乘scale -> `scaled_counts`。

Config同时可使用P9 generated Rabi小扫描，验证：

- tau coords；
- SequenceSelected；
- raw counts；
- derived scaled_counts；
- RunStore raw/derived specs。

不要新增依赖numpy的example。

---

## Tests

至少覆盖：

1. queued nested emit raw-before-derived order。
2. engine ignores DerivedData/status。
3. setup/process/close lifecycle。
4. one raw scalar -> one derived scalar。
5. multiple raw DataPoint merge beforemodule ready。
6. module exactly once per point。
7. module chain A->B topological execution。
8. missing input at MeasurementCompleted。
9. raw duplicate/collision/coords mismatch。
10. output undeclared/namespace/collision/serialization error。
11. warn/skip/fail policies。
12. fail preservescurrent raw event andruns cleanup。
13. show/save four combinations。
14. live-only not in events/data/manifest/RunReader。
15. saved derived in JSONL/CSV and optional Zarr whenavailable。
16. metadata module provenance和analysis error count。
17. point accumulator cleanup。
18. engine close onexecutor failure。
19. P9 SequenceSelected + P10 DerivedData samepoint coords。
20. old no-analysis run unchanged。
21. full suite。

---

## 文档更新

更新Live Compute plan、Data Model、Config Schema、Implementation Order。标记P10 Phase B完成；GUI/recompute/async保持planned。

---

## 验收命令

```bash
python -m pytest tests/unit/test_event_bus_queued_emit.py
python -m pytest tests/unit/test_derived_data_event.py
python -m pytest tests/unit/test_live_compute_engine.py
python -m pytest tests/unit/test_live_compute_dependencies.py
python -m pytest tests/unit/test_live_compute_fail_policy.py
python -m pytest tests/unit/test_live_compute_runstore.py
python -m pytest tests/integration/test_live_compute_dry_run.py
python -m pytest tests/integration/test_live_compute_sequence_plan_run.py
python -m pytest
```

---

## 完成定义

- raw先保存，derived后产生；
- multi-event point和module DAG正确；
- show/save/fail语义明确；
- live-only绝不落盘；
- saved derived被RunReader/manifest识别；
- P9 sequence run兼容；
- 无GUI/async/recompute混入；
- full suite通过。

---

## 最终汇报

1. 修改文件/public API。
2. EventBus ordering。
3. engine point/DAG lifecycle。
4. fail/show/save semantics。
5. storage/manifest/metadata格式。
6. P9+P10 integration run结果。
7. tests。
8. 给P10.3/P10.5的event/status/thread-safety handoff。

