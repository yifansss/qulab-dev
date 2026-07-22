# Prompt 003: Config + Mock Instrument + Sync Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在已经完成的 core 和 storage 基础上，打通“YAML config -> resources/mock instruments -> Procedure -> Sync preflight -> dry-run executor -> RunStore”的完整无硬件闭环。这个 worker 可以一次性做 config parser、mock capability/registry、基础 sync plan，但仍然不允许接触真实硬件和 GUI。

---

## /goal

在当前 `qulab` 项目中实现第三阶段无硬件可运行闭环：从 YAML 实验配置加载 resources、sync、setup、procedure、cleanup，构建 `ExperimentContext`、mock instrument resources、`Procedure` 和 `SyncPlan`，运行基础 preflight validation，并能执行 dry-run 实验且通过 `RunStore` 自动保存结果。完成后必须提供至少两个示例 YAML（dry-run ODMR 和 dry-run Rabi），并有单元/集成测试覆盖 config parser、mock instruments、sync validator、YAML-to-RunStore 全流程。完成后 `python -m pytest` 必须通过。

成功标准：

1. 阅读并遵守项目蓝图、config schema、adapter 规范、sync 规范和现有 core/storage API。
2. 实现 `src/qulab/config/`，支持从 YAML path/string/dict 构建实验对象。
3. 实现 `src/qulab/instruments/` 的 capability base、registry、setup profile 和 mock adapters。
4. 实现 `src/qulab/sync/` 的 `SyncPlan`、`TriggerEdge`、`ExecutionOrder`、`SyncValidator`。
5. 不导入 PyQt、pycontrol、NI、ASG SDK、pyvisa、serial 或任何真实硬件依赖。
6. 支持 YAML 中的 `call: resource.method`，映射到 `ExperimentContext.resources` 中的 mock resource method。
7. 支持 `${param_name}` 参数引用，转换为 core 的 `P("param_name")`。
8. 支持 YAML scan values：
   - explicit list
   - `{start, stop, points}`
   - `{start, stop, step}`
9. 支持 YAML step：
   - `call`
   - `scan`
   - `average`
   - `measurement`
   - `run`
   - `cleanup`
10. 支持基础 mock instruments：
    - mock microwave source
    - mock pulse sequencer
    - mock DAQ counter
    - mock analog input/output，简单即可
11. 支持基础 sync validation：
    - resource exists
    - trigger source/target syntax valid
    - arm receiver before source start
    - average count > 0
    - scan values non-empty
12. 提供 dry-run YAML 示例：
    - `configs/experiments/dry_run_odmr.yaml`
    - `configs/experiments/dry_run_rabi.yaml`
    - 可选：`configs/setups/mock_nv_setup.yaml`
13. 集成测试必须证明：
    - 从 YAML 加载 dry-run Rabi。
    - 构建 mock resources。
    - preflight 通过。
    - executor 运行完成。
    - RunStore 生成 metadata/events/data/points/index。
14. 更新必要文档，说明如何运行 YAML dry-run 实验。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/CONFIG_SCHEMA.md`
4. `docs/DATA_MODEL.md`
5. `docs/HARDWARE_SYNC.md`
6. `docs/ADAPTER_REQUIREMENTS.md`
7. `docs/IMPLEMENTATION_ORDER.md`
8. `workers/core_worker.md`
9. `workers/storage_worker.md`
10. `workers/adapter_worker.md`
11. `workers/sync_worker.md`
12. `workers/qa_worker.md`

同时查看当前实现：

```text
src/qulab/core/
src/qulab/storage/
tests/unit/
tests/integration/
```

重点确认：

- `ActionStep.action` 可以是 callable 或 `"resource.method"` string。
- `ExperimentExecutor` 已经能 resolve resource method。
- `ExperimentContext.resources` 是 resource name 到 object 的 dict。
- `RunStore` 是 EventBus subscriber，core 不依赖 storage。

---

## 当前项目目录

项目根目录：

```text
<QULAB_PROJECT_ROOT>
```

新增代码建议放在：

```text
src/qulab/config/
src/qulab/instruments/
src/qulab/instruments/adapters/
src/qulab/sync/
```

新增测试建议放在：

```text
tests/unit/test_config_parser.py
tests/unit/test_instrument_registry.py
tests/unit/test_sync_validator.py
tests/integration/test_yaml_dry_run.py
```

新增示例：

```text
configs/experiments/dry_run_odmr.yaml
configs/experiments/dry_run_rabi.yaml
configs/setups/mock_nv_setup.yaml
```

不要修改：

```text
../pycontrol
../panel(basic)
```

不要实现真实 pycontrol adapter；这会留给后续 worker。

---

## 推荐实现文件

### Config

```text
src/qulab/config/__init__.py
src/qulab/config/loader.py
src/qulab/config/parser.py
src/qulab/config/refs.py
src/qulab/config/errors.py
src/qulab/config/runner.py
```

### Instruments

```text
src/qulab/instruments/base.py
src/qulab/instruments/capabilities.py
src/qulab/instruments/registry.py
src/qulab/instruments/profiles.py
src/qulab/instruments/adapters/mock.py
src/qulab/instruments/__init__.py
src/qulab/instruments/adapters/__init__.py
```

### Sync

```text
src/qulab/sync/trigger_plan.py
src/qulab/sync/validators.py
src/qulab/sync/__init__.py
```

可以根据实际需要增减文件，但保持职责清晰。

---

## 具体实现要求

### 1. Config Loader

实现：

```python
def load_yaml_config(path: str | Path) -> dict: ...
def load_experiment_config(source: str | Path | dict) -> dict: ...
```

要求：

- 使用 `yaml.safe_load`。
- 空文件或非 dict 顶层要清楚报错。
- 不允许执行任意 Python 表达式。
- 支持数字字符串或科学计数法字符串的温和转换，例如 `"2.87e9"` -> `2870000000.0`，但不要过度猜测普通字符串。

### 2. Config Parser

实现一个高级入口，名字可以调整，但能力要等价：

```python
@dataclass
class ParsedExperiment:
    name: str
    config: dict
    resolved_config: dict
    procedure: Procedure
    context: ExperimentContext
    sync_plan: SyncPlan | None
    validation: SyncValidationResult

def parse_experiment_config(config: dict, registry: InstrumentRegistry | None = None) -> ParsedExperiment: ...
```

解析字段：

```yaml
schema_version: 1
name: rabi
resources: {}
sync: {}
setup: []
procedure: []
cleanup: []
plot: []
storage: {}
```

MVP 重点：

- `resources` -> mock resources -> `ExperimentContext.resources`
- `setup` -> `Procedure.setup`
- `procedure` -> `Procedure.body`
- `cleanup` -> `Procedure.cleanup`
- `sync` -> `SyncPlan`

### 3. Parameter Reference

YAML 中：

```yaml
args:
  freq_hz: ${mw_freq_hz}
```

必须转换为：

```python
P("mw_freq_hz")
```

要求：

- 只支持完整字符串引用：`${name}`。
- 嵌套 dict/list 中也要递归转换。
- 不要支持任意表达式，例如 `${a + b}`。
- 如果需要字符串模板拼接，后续再做。

### 4. Step Parser

支持以下 YAML step：

#### Call

```yaml
- call: mw.set_frequency
  args: { freq_hz: ${mw_freq_hz} }
```

转换为：

```python
ActionStep(name="mw.set_frequency", action="mw.set_frequency", kwargs={"freq_hz": P("mw_freq_hz")})
```

如果有 `save_as`：

```yaml
- call: daq.read_counts
  save_as: counts
```

转换为带 `save_as` 的 `ActionStep`。

#### Scan

```yaml
- scan:
    name: mw_freq_hz
    values: { start: 2.86e9, stop: 2.88e9, points: 101 }
    body: []
```

转换为 `ScanStep`。

#### Average

```yaml
- average:
    name: avg
    count: 100
    body: []
```

转换为 `AverageStep`。

注意：当前 core 的 `AverageStep.count` 是 int；如果 YAML 写 `${averages}`，MVP 可以报错，或者在 parser 阶段只允许 literal int。不要为此大改 core。

#### Measurement

```yaml
- measurement:
    name: rabi_point
    body: []
```

转换为 `MeasurementStep`。`save_raw`、`snapshots` 可以先保存在 step metadata，如果 core 暂无字段，可以暂时忽略并在文档标注后续扩展。

#### Run

```yaml
- run:
    name: readout
    timeout_s: 10
    steps: []
```

转换为 `RunStep(body=steps)`。

### 5. Instrument Capability and Registry

实现轻量 capability base，不要过度抽象。

推荐：

```python
class InstrumentAdapter:
    name: str
    simulation: bool
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def health_check(self) -> dict: ...
    def snapshot(self) -> dict: ...
    def capabilities(self) -> set[str]: ...
```

`InstrumentRegistry`：

```python
class InstrumentRegistry:
    def register(self, adapter_name: str, factory: Callable[..., Any]) -> None: ...
    def create(self, resource_name: str, config: dict) -> Any: ...
```

要求：

- 默认注册 mock adapters。
- 未知 adapter 清楚报错。
- resource config 中的 `adapter` 决定 factory。

### 6. Mock Adapters

实现：

```python
MockMicrowaveSource
MockPulseSequencer
MockDAQCounter
MockAnalogIO
```

它们要足够支持 dry-run ODMR/Rabi YAML。

MockMicrowaveSource：

- `connect()`
- `disconnect()`
- `set_frequency(freq_hz)`
- `set_power(power_dbm)`
- `output_on()`
- `output_off()`
- `snapshot()`

MockPulseSequencer：

- `connect()`
- `disconnect()`
- `load_sequence(path=None, sequence=None)`
- `set_sequence_param(name, value)`
- `compile_sequence()`
- `configure_trigger(...)`
- `arm()`
- `start()`
- `stop()`
- `snapshot()`

MockDAQCounter：

- `connect()`
- `disconnect()`
- `configure_counter(sample_rate=None, samples=None, source=None, trigger=None)`
- `arm()`
- `read_counts()`
- `read_counts_binned()`
- `read_analog()`
- `stop()`
- `snapshot()`

Mock data should be deterministic enough for tests. Example:

- `read_counts()` returns a dict like `{"counts_mean": 1000.0, "photon_bins": [100, 101, 99]}`.
- `read_analog()` returns a small matrix, e.g. `[[0.0, 0.1], [0.2, 0.3]]`.

不要引入 numpy，除非已有项目依赖可以直接用；即使用 numpy，也要确保 JSON-safe 转换已经由 storage 处理。

### 7. Setup Profile

实现基础 `SetupProfile` 或简单 helper：

```python
def build_context_from_resources(resources_config: dict, registry: InstrumentRegistry) -> ExperimentContext: ...
```

要求：

- 为每个 resource 创建 mock adapter。
- 如果 resource config 有 `connect_on_load: true`，可以调用 connect；默认可以不连接。
- 在 `context.resources[name]` 中注册 resource。

### 8. Sync Plan

实现 dataclass：

```python
TriggerEdge(source: str, target: str, edge: str = "rising", purpose: str | None = None)
ExecutionOrder(configure: list[str], arm: list[str], start: list[str], read: list[str])
SyncPlan(master: str | None, triggers: list[TriggerEdge], order: ExecutionOrder | None)
SyncValidationIssue(severity: str, code: str, message: str)
SyncValidationResult(issues: list[SyncValidationIssue])
```

`SyncValidationResult` 需要：

- `ok` property，如果没有 severity error 则 True。
- `errors` / `warnings` 便捷访问可选。

### 9. Sync Validator

实现：

```python
class SyncValidator:
    def validate(self, sync_plan: SyncPlan | None, context: ExperimentContext, procedure: Procedure) -> SyncValidationResult: ...
```

MVP 检查：

- sync plan 为空时返回 warning 或 ok，视实验是否有 run step；不要阻止简单 dry-run。
- master resource 存在。
- trigger source/target 形如 `resource.channel`。
- trigger source/target 的 resource 存在。
- edge 是 `rising`、`falling`、`both` 之一。
- order 中所有 resource 存在。
- 如果 order 有 `arm` 和 `start`，常见接收器如 `daq` 应在 `asg` 前 arm；MVP 可以用 resource name heuristic。
- scan values 不为空。
- average count > 0。

不要做真实硬件线缆检查，不要导入硬件。

### 10. Runner Convenience

实现一个无硬件 helper：

```python
def run_dry_config(
    config_source: str | Path | dict,
    run_root: str | Path,
) -> RunResult: ...
```

建议 `RunResult` 包含：

- `parsed`
- `run_path`
- `executor_state`
- `events`
- `validation`

内部流程：

```text
load config
parse config -> procedure/context/sync_plan
validate sync
if validation has errors: raise ConfigValidationError
open RunStore
subscribe RunStore to EventBus
run ExperimentExecutor
close RunStore
return result
```

重要：这个 helper 可以依赖 storage，但 core 不能依赖 storage。

### 11. Example YAML

#### dry_run_odmr.yaml

必须包含：

- mock mw。
- mock asg。
- mock daq。
- scan `mw_freq_hz`。
- measurement。
- run readout。
- daq.read_counts save_as counts。

#### dry_run_rabi.yaml

必须包含：

- scan `tau_s`。
- asg.set_sequence_param。
- average。
- run readout。
- daq.read_counts save_as counts。

YAML 不需要真实硬件地址。

---

## 严格禁止

- 不要实现 GUI。
- 不要连接真实硬件。
- 不要导入 `nidaqmx`、`pyvisa`、`serial`、ASG DLL 或 `../pycontrol`。
- 不要实现真实 pycontrol adapters。
- 不要让 core 依赖 config/storage/instruments/sync。
- 不要让 parser 执行任意 Python 表达式。
- 不要在测试中写入项目根目录真实 `runs/`。
- 不要吞异常；错误要结构化、可测试。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.config import parse_experiment_config; print(parse_experiment_config.__name__)"
PYTHONPATH=src python -c "from qulab.instruments import InstrumentRegistry; print(InstrumentRegistry.__name__)"
PYTHONPATH=src python -c "from qulab.sync import SyncValidator; print(SyncValidator.__name__)"
```

如果新增了示例 runner，也可以在测试中调用，不要要求真实用户手动跑。

---

## 文档更新要求

完成后至少更新：

```text
docs/CONFIG_SCHEMA.md
docs/ADAPTER_REQUIREMENTS.md
docs/HARDWARE_SYNC.md
docs/IMPLEMENTATION_ORDER.md
README.md
```

README 至少添加一个 dry-run YAML 示例入口，说明：

```python
from qulab.config import run_dry_config
result = run_dry_config("configs/experiments/dry_run_rabi.yaml", run_root="/tmp/qulab-runs")
print(result.run_path)
```

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 实现了哪些 config/instrument/sync 对象。
3. 新增了哪些示例 YAML。
4. 运行了哪些验证命令，结果是什么。
5. 是否保持 core 与 config/storage/instruments 解耦。
6. 还没做什么，明确留给后续 worker。
7. 是否修改了公共 API。

---

## 后续 worker 依赖

这个 worker 完成后，后续 worker 可以继续：

- plotting worker：从 EventBus 或 RunStore 文件绘制 line/heatmap。
- GUI worker：加载 YAML，显示 procedure tree，调用 `run_dry_config` 或更细粒度 runner。
- pycontrol adapter worker：把 mock adapters 替换/扩展为真实 pycontrol adapters。
- sync hardware worker：增强 ASG/NI trigger preflight 和 connection table。

