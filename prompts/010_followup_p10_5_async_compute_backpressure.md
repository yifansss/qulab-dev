# Prompt 010-followup P10.5: Async Live Compute Queue + Backpressure Worker

下面这份 prompt 可直接交给新的AI worker。目标是完成P10 Phase E：在不阻塞raw acquisition/storage的前提下，把P10.2同步engine扩展为有界异步执行，提供latency/queue/lag metrics、明确backpressure/skip策略、thread-safe event/storage integration和GUI状态。Raw data优先级永远高于derived compute。

---

## /goal

当compute module很慢时：

- hardware/executor继续采集和存raw；
- compute queue有上限；
- operator看到lag/queue/drop状态；
- configured policy决定skip/drop/disable/fail；
- point/coords关联不因out-of-order completion错误；
- run结束按drain policy完成或标记未处理；
- RunStore和GUI线程安全；
- 同步模式仍可选且兼容。

---

## 硬依赖

P10.1-P10.3完成。P10.4可并行或先完成，但result storage不应与live worker线程共用writer实例。

开始前读取P10.2 EventBus/engine/RunStore ordering handoff和P10.3 GUI event queue。不得另建第二套events/catalog。

---

## 必须先阅读

1. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
2. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
3. `docs/DATA_MODEL.md`
4. `workers/core_worker.md`
5. `workers/storage_worker.md`
6. `workers/gui_worker.md`
7. `workers/qa_worker.md`
8. P10.1-P10.4 code/handoffs
9. EventBus、LiveComputeEngine、RunStore、OperatorController、Live Run GUI
10. executor lifecycle/cleanup tests

---

## 严格范围

### 必须实现

- async mode config；
- bounded input queue；
- worker lifecycle；
- deterministic module execution perpoint；
- thread-safe queued event dispatch；
- thread-safe RunStore handling or single serialized dispatch ownership；
- queue policies；
- latency/lag/drop metrics；
- AnalysisStatus queue updates；
- drain/cancel/shutdown semantics；
- raw-priority guarantees；
- GUI lag/status integration；
- stress/race/failure tests；
- docs。

### 不实现

- 不实现distributed compute；
- 不实现GPU scheduler；
- 不实现arbitrary multiprocessing by default；
- 不改变hardware timing；
- 不让queue block成为默认；
- 不丢弃raw DataPoint或SequenceSelected；
- 不修改post-run raw data；
- 不隐藏dropped derived points；
- 不让background thread直接操作Qt widgets。

---

## Config Contract

扩展：

```yaml
analysis:
  live:
    enabled: true
    execution: async           # sync | async
    queue_size: 64
    backpressure: skip_newest  # skip_newest | skip_oldest | latest | disable_module | fail
    drain_on_close: true
    drain_timeout_s: 10
    worker_count: 1
    status_interval_s: 0.5
```

Rules：

- default保持`sync`直到async充分验证，或项目明确切换；
- async `queue_size >= 1`；
- MVP `worker_count=1`保证point/module order；>1只在明确实现per-point dependency和ordering后开放；
- policies enum严格；
- `block`不作为普通policy；若未来支持必须显式并警告会阻塞acquisition；
- drain timeout finite nonnegative；
- per-module override可后置，MVP global policy清楚即可；
- config changes invalidate Prepare。

---

## Architecture Choice

推荐thread worker + bounded `queue.Queue`：

```text
executor thread
  raw EventBus -> RunStore raw -> engine.enqueue(snapshot) -> GUI raw

analysis worker
  process point/DAG -> emit DerivedData/AnalysisStatus through serialized bus
```

Python process mode可作为future extension；本worker不要同时实现thread+process两套不成熟后端。

Input snapshot必须deep-copy/normalize required data，module不能持有executor mutable object。

---

## EventBus and Storage Thread Safety

P10.2 EventBus只保证non-recursive queue，不一定thread-safe。P10.5必须选定并实现一种明确策略：

### Recommended: Serialized EventBus Dispatch

- thread-safe inbound event queue；
- one dispatch owner/lock保证subscribers不并发执行；
- raw emitter可同步等待raw dispatch完成，确保raw stored beforeenqueue/return；
- worker emitted derived进入same queue；
- no subscriber called concurrently；
- FIFO per emitter，cross-thread global ordering按queue arrival；
- point association不依赖arrival order。

如果使用dispatch lock而非dedicated dispatcher，必须证明：

- no deadlock when subscriber emits；
- raw store ordering；
- RunStore writers never concurrent；
- close waits pendingderived dispatch；
- subscriber exception routed correctly to worker/main lifecycle。

RunStore不应靠多个细粒度locks掩盖EventBus concurrent dispatch。优先单一serialized subscriber execution。

GUI仍通过thread-safe event queue在Qt main thread更新。

---

## Queue Item and Point Semantics

Queue item至少：

```python
@dataclass(frozen=True)
class ComputeWorkItem:
    sequence_number: int
    point_id: str
    coords: Mapping[str, Any]
    data_snapshot: Mapping[str, Any]
    metadata: Mapping[str, Any]
    enqueued_monotonic: float
```

P10.2可能在同point多个raw events后才ready。Async boundary应在“module work ready”或“point completed”的明确位置：

- 推荐engine在executor thread只做轻量aggregation/readiness，enqueue immutable module/point work；
- worker执行module DAG；
- 同pointexactly once；
- missing input仍在MeasurementCompleted处理；
- queue policy按work item，不按individual data sample；
- one worker保持scan order；
- future multiple workers的out-of-order通过point_id处理。

不要让worker访问/修改live engine accumulator without synchronization。

---

## Backpressure Policies

### skip_newest

Queue满时不enqueue当前work，raw继续。Emit status包含point/module、dropped count。

### skip_oldest

移除最旧未开始work，enqueue当前。被移除point明确status；不得移除正在执行item。

### latest

保留最新待处理状态。对于每point都需要derived provenance的module不适合；preflight warning。实现语义必须明确是global latest或per-module latest，MVP选择一种并测试。

### disable_module

第一次queue overflow后disable live engine/modules for remainder run，raw继续，emit warning。Post-run recompute仍可用。

### fail

Overflow触发controlled run failure。Raw current event已保存，cleanup执行。

所有drop/disable必须计数并进入metadata/status。不得quietly skip。

---

## Metrics

Per module/engine：

- queue depth/capacity；
- enqueued/completed/skipped/dropped/failed；
- current/last point；
- queue wait latency；
- processing latency；
- end-to-end latency；
- moving average/max latency；
- lagging bool/threshold；
- worker state；
- last error。

Use monotonic clock。AnalysisStatus throttled by`status_interval_s`，但success/error/drop重要状态立即emit。

Metadata final summary记录metrics，不把每次heartbeat都塞metadata.json。可选analysis status JSONL append-only。

---

## Shutdown and Drain

Run lifecycle：

1. executor completes/fails；
2. no newraw work；
3. engine close requested；
4. if drain，等待queue+current work up to timeout；
5. completedderived events dispatch/store；
6. timeout时mark remaining skipped/cancelled；
7. close modules/worker；
8. close RunStore。

Rules：

- RunStore不得在worker仍可能emit时close；
- drain timeout不无限hang；
- `drain_on_close:false`丢弃pending并记录count；
- current Python thread不能强杀正在执行module；timeout后可daemon/leak风险必须设计清楚。推荐cooperative stop并限制module contract；
- worker join状态报告；
- Ctrl-C/GUI Stop/executor error都执行shutdown；
- module close在worker停止后一次；
- setup failure不启动worker或cleanly teardown。

MVP若无法安全终止hung module，文档必须明确thread backend limitation，并建议post-run/未来process isolation。不能声称timeout可以kill arbitrary Python thread。

---

## Failure Routing

Module warn/skip/fail沿P10.2。

Worker thread中的`fail`不能只在线程打印traceback。必须：

- capture exception；
- emit failed AnalysisStatus；
- signal main run/control path；
- fail policy `fail`触发executor/run failure或最迟final status failed；
- cleanup；
- raw preserved。

Event subscriber/storage failure优先级高，必须停止run并报告，不当作module warn。

---

## GUI Integration

P10.3 module status panel已有queue/lag placeholders。接入：

- queue depth/capacity；
- lag indicator；
- dropped/skipped count；
- wait/process latency；
- worker state；
- current point；
- drain status on run completion。

Live plot可晚于raw更新derived；point merge model应已有支持。GUI不阻塞等待derived，不从worker thread操作widgets。

提供tooltip说明live compute lag不等于hardware/data loss；raw storage status单独显示。

---

## Tests

至少覆盖：

1. async raw emit returns withoutwaiting slow module（除短enqueue）。
2. raw stored beforederived。
3. bounded queue never exceeds capacity。
4. one worker deterministic order。
5. skip_newest。
6. skip_oldest。
7. latest exact semantics。
8. disable_module。
9. fail overflow preservesraw/cleanup。
10. metrics counts/latencies/lag。
11. status throttling + immediate errors。
12. point/module exactly once。
13. module DAG dependencies worker execution。
14. samepoint multi raw aggregation。
15. thread-safe EventBus no concurrent RunStore writes。
16. nested emit no deadlock。
17. derived out-of-order GUI association。
18. drain success。
19. drain timeout/pending counts。
20. no-drain behavior。
21. executor failure shutdown。
22. module fail routing fromworker。
23. live-only stillnotpersisted。
24. SequenceSelected/raw不丢失 under backlog。
25. stress hundreds/thousands small points nohang。
26. sync mode regression。
27. full suite。

Use deterministic synchronization primitives/events in tests，禁止flaky arbitrary sleep。Slow module用threading.Event/barrier控制。

---

## Documentation

更新Live Compute plan、Data Model、Operator UI、Implementation Order。说明thread backend不能强杀hung Python code，raw priority和每种policy语义。标记P10 Phase E完成。

---

## 验收命令

建议tests：

```text
tests/unit/test_async_compute_queue.py
tests/unit/test_async_compute_backpressure.py
tests/unit/test_async_compute_metrics.py
tests/unit/test_event_bus_thread_safety.py
tests/unit/test_async_compute_shutdown.py
tests/integration/test_async_compute_run.py
tests/integration/test_async_compute_sequence_run.py
tests/integration/test_async_compute_stress.py
```

执行：

```bash
python -m pytest tests/unit/test_async_compute_queue.py
python -m pytest tests/unit/test_async_compute_backpressure.py
python -m pytest tests/unit/test_async_compute_metrics.py
python -m pytest tests/unit/test_event_bus_thread_safety.py
python -m pytest tests/unit/test_async_compute_shutdown.py
python -m pytest tests/integration/test_async_compute_run.py
python -m pytest tests/integration/test_async_compute_sequence_run.py
python -m pytest tests/integration/test_async_compute_stress.py
python -m pytest
```

---

## 完成定义

- slow compute不阻塞raw acquisition/storage；
- queue有界且policies明确；
- drops/lag全部可见可记录；
- EventBus/RunStore无race/deadlock；
- close/drain不丢未声明状态；
- P9 sequence events/raw永不因compute backlog丢失；
- sync mode兼容；
- stress/full suite稳定通过。

---

## 最终汇报

1. 修改文件和async APIs。
2. threading/event dispatch architecture。
3. five policies精确定义。
4. raw priority/order证明/tests。
5. metrics/GUI显示。
6. drain/timeout/hung module limitation。
7. stress结果和tests。
8. remaining process isolation/future work。

