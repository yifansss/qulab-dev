# Prompt 009-followup P9.2: Sequence Bundle Runtime + Preflight + RunStore Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是完成 P9 的第二个小目标：在 P9.1 manifest/loader 基础上，把现有 workflow scan point 接到 concrete ASG sequence bundle entry，并完成运行事件、preflight、RunStore artifact/provenance。这个 worker 完成 P9 Phase C + Phase D，不实现 generator hook，也不实现 GUI scan authoring。

---

## /goal

在当前 `qulab` 项目中实现端到端但仍可无硬件测试的 sequence bundle runtime：

```text
existing workflow scan point
    -> resolve bundle entry from current coordinates
    -> call existing resource.load_sequence(sequence_file=...)
    -> emit SequenceSelected event
    -> continue arm/start/read
    -> RunStore records exact manifest/entry/file/hash/point coordinates
```

同时扩展 preflight，在任何硬件输出之前检查 bundle coverage、entry 文件、ASG trigger metadata 和可静态判断的 DAQ acquisition window。目标是让手写 workflow YAML 已经可以执行 Rabi/Ramsey/Echo 类 bundle scan；不依赖 Operator Parameters 自动生成 scan 节点。

---

## 硬依赖与开始条件

本 worker 必须在 `P9.1 Sequence Bundle Manifest Model + Loader` 已完成后开始。

开始前必须确认：

1. P9.1 focused tests 通过。
2. 项目中只有一套 canonical `SequenceBundle` / `SequenceBundleEntry` / `SequenceBundleSelection` 类型。
3. `ParsedExperiment` 已能访问已加载的 bundle registry。
4. loader 已实现 project/manifest-relative path、hash、match 与 coverage。

如果 P9.1 尚未完成或公共 API 与 prompt 不同，应先读取其实际实现并适配；不得复制一套新的 loader 到 executor、adapter 或 storage。

---

## 必须先阅读

修改前必须完整阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/HARDWARE_SYNC.md`
4. `docs/DATA_MODEL.md`
5. `docs/IMPLEMENTATION_ORDER.md` 中 P6、P9
6. `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
7. `docs/CONFIG_SCHEMA.md`
8. `workers/core_worker.md`
9. `workers/adapter_worker.md`
10. `workers/sync_worker.md`
11. `workers/storage_worker.md`
12. `workers/qa_worker.md`

同时检查当前实现：

```text
src/qulab/config/parser.py
src/qulab/config/runner.py
src/qulab/core/context.py
src/qulab/core/events.py
src/qulab/core/executor.py
src/qulab/core/procedure.py
src/qulab/instruments/adapters/mock.py
src/qulab/instruments/adapters/pycontrol.py
src/qulab/sync/validators.py
src/qulab/sequence_files.py
src/qulab/storage/run_store.py
src/qulab/storage/metadata.py
configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml
tests/unit/test_executor_dry_run.py
tests/unit/test_sync_validator.py
tests/unit/test_sequence_artifacts.py
tests/integration/test_dry_run_storage.py
```

---

## 当前事实与设计约束

- workflow `scan` 已把当前值写入 `ExperimentContext.parameters` 和 `coords`。
- `${tau_s}` 会在 action kwargs 执行前解析。
- `ActionStep.save_as` 当前用于生成 `DataPoint`，不能假设它会把返回值写回 parameter context。
- ASG mock 与 pycontrol adapter 已有 `load_sequence(sequence_file=...)`。
- pycontrol ASG 的 sequence 文件读取不应要求 GUI；真正 `arm/start` 才要求 connected hardware。
- RunStore 已支持静态 config 中单 sequence 文件的 snapshot/artifact。
- 旧 workflow 中直接调用 `asg.load_sequence` 的行为必须保持不变。

本 worker 不应为实现 bundle runtime 改写通用 scan engine，也不应改变 `save_as` 的全局语义。

---

## 严格任务范围

### 必须实现

- workflow action `resource.load_sequence_from_bundle` 的明确 runtime 语义；
- 从当前 point context 解析 coordinates；
- 使用 P9.1 canonical resolver 选择 entry；
- 委托现有 `resource.load_sequence(sequence_file=...)`；
- `SequenceSelected` structured event；
- workflow-aware bundle coverage preflight；
- trigger/window 静态 preflight；
- RunStore manifest、selection table、unique sequence artifact 和 metadata summary；
- dry-run Rabi bundle 示例；
- mock/integration tests；
- 文档更新。

### 明确不实现

- 不实现 pre-run generator hook（P9 Phase E）；
- 不实现 fixed/linspace/range GUI 控件或自动生成 scan node（P9 Phase F）；
- 不实现 pulse entity abstraction或 pulse compiler；
- 不修改 standalone sequence editor；
- 不新增危险硬件输出捷径；
- 不要求真实 ASG/NI 才能通过测试；
- 不把每个 point 的完整 sequence bytes 重复写入 metadata.json。

---

## Canonical Workflow Contract

MVP 使用一个单步、显式且不依赖 `save_as` 回写 context 的 action：

```yaml
procedure:
  - scan:
      name: tau_s
      values: [20e-9, 40e-9, 60e-9]
      body:
        - measurement:
            name: rabi_point
            body:
              - call: asg.load_sequence_from_bundle
                args:
                  bundle: rabi_tau
                  coordinates:
                    tau_s: "${tau_s}"
              - call: asg.compile_sequence
              - run:
                  name: pulse_readout
                  steps:
                    - call: daq.arm
                    - call: asg.arm
                    - call: asg.start
                    - call: daq.read
                      save_as: pse_ai1_trace
```

语义必须是：

1. `bundle` 是 experiment config `sequence_bundles` 中的 bundle id。
2. `coordinates` 在 action 执行时通过现有 `ExperimentContext.resolve()` 解析。
3. runtime 使用 bundle 已配置的 match mode/tolerance；action-level override 如支持，必须显式且通过同一 validator。
4. 选中 entry 后，调用目标 resource 的现有 `load_sequence(sequence_file=<absolute resolved path>)`。
5. load 成功后才 emit `SequenceSelected`。
6. action 返回 JSON-safe selection mapping，便于日志或可选 `save_as`，但 provenance 不依赖用户写 `save_as`。
7. load 失败时不得 emit 成功 selection event，原始 adapter error 必须保留。

不要要求每个 adapter 各自重新实现 manifest parsing。推荐把该 action 作为 executor 委托给独立 runtime service，例如：

```text
src/qulab/sequence_runtime.py
```

`ExperimentExecutor` 可以识别受限的 virtual action method `load_sequence_from_bundle`，然后调用 runtime service 与资源的 existing `load_sequence`。特殊分支必须小、明确、有测试；其余 action 继续走现有 `_resolve_action()`。

如项目中已经存在更通用且成熟的 framework action registry，可复用它，但不得为了本目标引入大型 plugin system。

---

## Context / Registry Contract

P9.1 bundle registry 必须在运行时可访问。推荐：

```python
@dataclass
class ExperimentContext:
    ...
    sequence_bundles: dict[str, SequenceBundle] = field(default_factory=dict)
```

`parse_experiment_config()` 构建 context 后注入已验证 registry。不得把 dataclass model 塞入可 YAML 序列化的 `resolved_config`。

runtime 必须检查：

- bundle id 存在；
- bundle resource 与 action target resource 相同；
- target resource 存在；
- target resource callable `load_sequence`；
- selection sequence file/hash 与 P9.1 loader 结果一致。

错误必须包含 action resource、bundle id 和 requested coordinates。

---

## SequenceSelected Event Contract

在 `src/qulab/core/events.py` 增加 structured event，字段至少包括：

```python
@dataclass
class SequenceSelected(Event):
    type: str = field(init=False, default="SequenceSelected")
    point_id: str | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    resource: str = ""
    bundle_id: str = ""
    entry_id: str = ""
    requested_coordinates: dict[str, Any] = field(default_factory=dict)
    entry_coordinates: dict[str, Any] = field(default_factory=dict)
    manifest_path: str = ""
    manifest_sha256: str = ""
    sequence_file: str = ""
    sequence_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

要求：

- event payload 可被当前 event JSONL writer 直接序列化；
- `point_id` 和 `coords` 来自执行时 context；
- event 在 adapter `load_sequence` 成功后发出；
- 每次 scan point 选择都发一条，即使多个 point 选择同一个 entry；
- event 不包含 sequence 文件全文；
- event 不代替普通 StepStarted/StepCompleted/ErrorRaised。

更新必要的 `__init__.py` public exports 和 event tests。

---

## Preflight Contract

扩展现有 validation，但保持 `SyncValidationResult`/issue 展示链路兼容。可以新增专门 validator，再由 parser/prepare 汇总；不要让 GUI 需要理解两种互不兼容的 result。

### 1. Workflow-aware coverage

对每个 `*.load_sequence_from_bundle` action：

- 确认 bundle 存在且 resource 一致；
- 分析其外层 workflow scan nodes；
- 对 action `coordinates` 中的 `ParameterRef` 生成可静态枚举的 coordinate combinations；
- 使用 P9.1 coverage resolver 验证每个 planned point；
- missing/ambiguous match 是 preflight error；
- missing manifest/file/hash mismatch 已由 P9.1 作为 error；
- 如果 coordinate 依赖无法静态解析的运行时值，给 actionable warning，不得伪装为 coverage success。

只枚举与该 action coordinate 有关的 scan 维度，避免无关 average 造成重复组合。为防止巨大扫描拖慢 Prepare，可设清楚、可配置或合理的点数上限；超过上限时采用逐维/索引校验或给明确 warning，不能卡住 GUI。

### 2. Trigger metadata

如果 entry metadata 提供 `trigger_channels`：

- 对 bundle 所有将使用的 entry 汇总 channel；
- 检查 `sync.triggers[].source` 中目标 ASG resource 是否声明相同 channel，例如 `asg.ch6`；
- metadata channel 不在 sync source 中时 warning 或 error 的规则必须稳定：明确用于 DAQ start trigger 且缺失时 error，仅为附加 trigger hint 时 warning；
- channel 比较应规范化常见大小写，例如 `CH6` 与 `ch6`；
- 不声称静态检查可以证明物理接线正确。

### 3. DAQ acquisition window

如果 entry metadata 提供 `duration_s`，且 workflow 中可静态读到：

```text
sample_rate
samples
```

计算：

```text
acquisition_window_s = samples / sample_rate
```

规则：

- 非正 sample_rate/samples 仍按现有 config validation 报错；
- acquisition window 小于 required sequence/readout duration 时 error；
- 刚好相等允许，但可以建议 margin；
- metadata 或 literal args 不完整时 warning，不报虚假 error；
- 如果 `duration_s` 表示完整 sequence，而 DAQ 只需覆盖 readout 子窗，manifest 可支持更精确的 `readout_window_s`/`required_acquisition_s`；存在该字段时优先使用，语义必须写入 docs；
- 不用这个检查替代 NI route/clock/trigger hardware validation。

### 4. Route consistency

做可静态判断的 config consistency：

- `sync.triggers[].target` 的 PFI 与 DAQ configure action 的 `start_trigger` 一致；
- edge 配置一致；
- resource/device/channel 名称沿用现有 NI normalization 规则。

不要建立虚构的 NI 型号 routing table。硬件是否支持 route 仍需要 NI-DAQmx/实验台验证。

---

## RunStore Provenance Contract

RunStore 必须同时记录 bundle-level 和 point-level provenance。

推荐 run folder：

```text
artifacts/sequences/<bundle_id>/manifest.yaml
artifacts/sequences/<bundle_id>/<entry_id>__<short_sha256>.json
sequence_selections.jsonl
metadata.json
```

### Bundle-level metadata

`metadata.json` 至少记录：

```json
{
  "sequence_bundles": [
    {
      "id": "rabi_tau",
      "resource": "asg",
      "manifest_source": "...",
      "manifest_artifact": "artifacts/sequences/rabi_tau/manifest.yaml",
      "manifest_sha256": "...",
      "entry_count": 3,
      "coordinates": ["tau_s"]
    }
  ],
  "sequence_selection_count": 3
}
```

### Point-level selection table

每个 `SequenceSelected` event append 一行 JSON：

```json
{
  "point_id": "p000001",
  "coords": {"tau_s": 2e-8},
  "resource": "asg",
  "bundle_id": "rabi_tau",
  "entry_id": "tau_20ns",
  "requested_coordinates": {"tau_s": 2e-8},
  "entry_coordinates": {"tau_s": 2e-8},
  "source_path": ".../tau_20ns.json",
  "artifact_path": "artifacts/sequences/rabi_tau/tau_20ns__abc123.json",
  "sha256": "...",
  "metadata": {"duration_s": 8e-6}
}
```

规则：

- point table append-only；
- 同一 entry 被 100 个 point 使用时 artifact 只复制一次，但 selection table 保留 100 行；
- artifact 文件名防止不同 source basename 冲突；
- copy 后可重新 hash 或确保 copy bytes 与 source hash 一致；
- source 在 run 中途消失或改变时 fail closed，并记录 ErrorRaised；
- metadata.json 不嵌入大型逐点 list，只存 summary/count/path；
- existing `sequence_snapshots` 保持兼容，不要删除；
- failed/partial run 也保留已发生的 selections；
- writer 正常 close，Windows 下文件句柄不泄漏。

如果 RunStore 尚未 open 就收到 event，沿用现有明确错误语义。

---

## Adapter 与硬件安全

- `load_sequence_from_bundle` 最终必须委托现有 `load_sequence`，不绕过 adapter。
- 不把 ASG vendor driver import 移到模块 import time。
- 不在 Prepare/preflight 中 connect、arm、start 或打开输出。
- dry-run 使用 `MockPulseSequencer` 验证 selected file。
- pycontrol adapter 的行为只需通过 unit contract 测试；本 worker 不要求无授权真实硬件动作。
- 不允许 bundle metadata 自动打开 ASG/MW/NI AO output。
- 任何硬件 run 仍遵循现有 connect、安全授权、arm/start/cleanup 路径。

---

## 示例配置

新增一个完全 mock、无硬件的 canonical 示例：

```text
configs/experiments/dry_run_rabi_sequence_bundle.yaml
```

要求：

- 引用 P9.1 三点 Rabi bundle；
- 使用现有 workflow `scan tau_s`；
- 在 measurement 内调用 `asg.load_sequence_from_bundle`；
- mock DAQ 产生一个可存储结果；
- dry-run 后产生三个 `SequenceSelected` events；
- RunStore 可由每个 point 重建所选 entry/file/hash。

可以再增加 Bench05 的 bundle 版本 template，但不得直接把原有、已用于实验台 bring-up 的 `bench_05_pse_ai1_asg_triggered_trace.template.yaml` 改成未验证的新机制。旧单 sequence bench 路径必须保留作为 fallback。

---

## 测试矩阵

至少新增：

```text
tests/unit/test_sequence_bundle_runtime.py
tests/unit/test_sequence_bundle_preflight.py
tests/unit/test_sequence_selected_event.py
tests/unit/test_sequence_bundle_runstore.py
tests/integration/test_rabi_sequence_bundle_dry_run.py
```

必须覆盖：

1. 三点 `tau_s` scan 每点选择正确 entry。
2. target resource 的 `load_sequence` 收到正确 resolved concrete path。
3. bundle resource 与 action resource 不一致时 preflight error。
4. unknown bundle id 在硬件动作前失败。
5. missing coverage 在 Prepare/preflight 阶段失败，而不是运行到中途。
6. nearest tolerance 生效。
7. adapter load 失败时 emit ErrorRaised，不 emit SequenceSelected。
8. 每次成功选择 emit SequenceSelected，字段完整且 JSON-safe。
9. point_id/coords 与 measurement point 一致。
10. RunStore 复制 manifest。
11. 同一 entry 多次选择只复制一个 artifact。
12. selection JSONL 保留每个 point 的记录。
13. metadata 记录 bundle summary 和 selection count。
14. trigger metadata 与 `sync.triggers` 一致时通过。
15. trigger channel mismatch 给正确 severity/code/message。
16. DAQ window 足够时通过。
17. DAQ window 小于 required duration 时 preflight error。
18. 无 optional duration/trigger metadata 时只给有限 warning，不阻止兼容运行。
19. old direct `asg.load_sequence` workflow 行为不变。
20. 所有测试无 Qt、无 NI/ASG SDK、无硬件也可运行。

错误测试必须断言稳定 issue code，不要只匹配整段脆弱文案。

---

## 文档更新

完成后更新：

```text
docs/CONFIG_SCHEMA.md
docs/DATA_MODEL.md
docs/HARDWARE_SYNC.md
docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md
docs/IMPLEMENTATION_ORDER.md
```

文档必须明确：

- P9 Phase C/D 已完成；
- canonical workflow action 是 `resource.load_sequence_from_bundle`；
- P9 Phase E generator hook 仍 planned；
- P9 Phase F Operator scan authoring 仍后置 planned；
- 旧单 sequence config/bench tests 仍受支持；
- preflight 只能验证 config/metadata consistency，不能证明物理接线或 NI hardware route 可用。

---

## 验收命令

worker 必须实际执行并报告：

```bash
python -m pytest tests/unit/test_sequence_bundle_runtime.py
python -m pytest tests/unit/test_sequence_bundle_preflight.py
python -m pytest tests/unit/test_sequence_selected_event.py
python -m pytest tests/unit/test_sequence_bundle_runstore.py
python -m pytest tests/integration/test_rabi_sequence_bundle_dry_run.py
python -m pytest
```

并执行 canonical dry-run smoke，使用项目在 Windows/macOS/Linux 均可接受的环境变量写法说明。实际 worker 当前平台可运行：

```bash
PYTHONPATH=src python -c "from qulab.config.runner import run_dry_config; print(run_dry_config('configs/experiments/dry_run_rabi_sequence_bundle.yaml', 'runs').executor_state)"
```

在 Windows 实验机文档中应给出 PowerShell 等价写法：

```powershell
$env:PYTHONPATH = "src"
python -c "from qulab.config.runner import run_dry_config; print(run_dry_config('configs/experiments/dry_run_rabi_sequence_bundle.yaml', 'runs').executor_state)"
```

如果项目已可 editable install，则优先使用安装后的 `python -m ...`，不要强制用户依赖 Unix inline env syntax。

---

## 完成定义

只有同时满足以下条件才可宣告完成：

- 手写 workflow scan 能逐点选择并 load concrete sequence；
- provenance 不依赖用户添加 `save_as`；
- missing coverage 在 hardware output 前被阻止；
- trigger/window static validation 有稳定 issue code；
- RunStore 可由 point_id 重建 bundle/entry/source/artifact/hash；
- artifact 去重且 selection history 完整；
- mock dry-run 示例通过；
- old single-sequence workflows 和全量 tests 不回归；
- 没有实现或偷带 Phase E/F；
- 文档准确反映已完成与待完成边界。

---

## 最终汇报格式

worker 最终回答必须包含：

1. 实际新增/修改文件。
2. runtime action 的最终 YAML/API contract。
3. preflight 新增 issue code 与 severity 摘要。
4. RunStore 新文件和 metadata 字段。
5. canonical dry-run 的 point -> entry 结果。
6. 实际测试命令与 pass/skip 数量。
7. 兼容性和剩余风险，特别是未做真实硬件 route/trigger 验证。
8. 明确保留的后续任务：P9 Phase E generator hook、P9 Phase F Operator scan authoring，以及单独规划的 P10 live compute。

