# Prompt 001: Core Foundation Worker

下面这份 prompt 可以直接复制给一个新的 AI worker。目标是完成 `qulab` 的第一步工程地基：核心流程模型、dry-run executor、事件流和测试。这个 worker 不应该接触真实硬件，不应该实现 GUI，不应该实现 pycontrol adapter。

---

## /goal

在当前 `qulab` 项目中实现第一阶段核心基础：建立可测试、无硬件依赖的实验流程核心层，使框架能够用 Python 对象表达 `setup -> scan -> measurement -> average -> run -> cleanup`，并能在 dry-run 模式下执行一个一维/二维扫描，产生带 `point_id` 的结构化事件流。完成后必须有单元测试覆盖核心行为，且 `python -m pytest` 通过。

成功标准：

1. 阅读并遵守项目蓝图和 worker 规范。
2. 实现 `src/qulab/core/` 下的核心模块。
3. 不导入 PyQt、pycontrol、NI、ASG SDK 或任何真实硬件依赖。
4. 支持 scan、average、measurement、action、run、cleanup 的基础模型。
5. 每个 measurement point 生成稳定唯一 `point_id`。
6. 能 dry-run 执行嵌套二维扫描，并产生事件：
   - `RunStarted`
   - `RunCompleted`
   - `StepStarted`
   - `StepCompleted`
   - `ParameterChanged`
   - `MeasurementStarted`
   - `MeasurementCompleted`
   - `DataPoint`
   - `ErrorRaised`，出错时
7. 支持参数引用，例如 `P("mw_freq_hz")`。
8. 支持 mock action callable，不需要真实仪器。
9. 增加单元测试，覆盖二维扫描、平均、measurement point、参数引用、错误事件、cleanup。
10. 更新必要文档，说明本阶段实现的对象和限制。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读以下文件：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/CONFIG_SCHEMA.md`
4. `docs/DATA_MODEL.md`
5. `docs/IMPLEMENTATION_ORDER.md`
6. `workers/core_worker.md`
7. `workers/qa_worker.md`

阅读时重点确认：

- `MeasurementStep` 是扫描点内部的完整测量子流程。
- 框架不能假设一个扫描点只产生一个 scalar。
- core 层不能依赖硬件、GUI 或 storage。
- executor 通过事件流描述运行过程。

---

## 当前项目目录

项目根目录：

```text
<QULAB_PROJECT_ROOT>
```

核心代码应放在：

```text
src/qulab/core/
```

测试应放在：

```text
tests/unit/
```

不要修改：

```text
../pycontrol
../panel(basic)
```

不要实现真实硬件 adapter。

---

## 推荐实现文件

请创建或更新以下文件：

```text
src/qulab/core/parameter.py
src/qulab/core/events.py
src/qulab/core/procedure.py
src/qulab/core/context.py
src/qulab/core/executor.py
src/qulab/core/__init__.py

tests/unit/test_parameter.py
tests/unit/test_procedure.py
tests/unit/test_executor_dry_run.py
```

可以根据实际需要增加：

```text
src/qulab/core/errors.py
src/qulab/core/types.py
```

---

## 具体实现要求

### 1. Parameter Model

实现：

```python
Parameter
ParameterRef
P(name: str) -> ParameterRef
ScanValues
```

要求：

- `Parameter` 至少包含 `name`、`value`、`unit`、`metadata`。
- `ParameterRef` 用于延迟引用当前 context 中的参数值。
- `P("mw_freq_hz")` 返回 `ParameterRef("mw_freq_hz")`。
- `ScanValues` 支持：
  - explicit list
  - linspace: start/stop/points
  - range: start/stop/step，可选

测试：

- `P("x")` 能从 context 参数中解析。
- linspace 生成正确数量的点。

### 2. Event Model

实现结构化事件，推荐用 dataclass：

```python
Event
RunStarted
RunCompleted
StepStarted
StepCompleted
ParameterChanged
MeasurementStarted
MeasurementCompleted
DataPoint
ErrorRaised
LogMessage
```

要求：

- 每个事件有 `type`、`timestamp`。
- 事件能转成 dict，方便后续 storage 写 jsonl。
- `DataPoint` 支持：
  - `point_id`
  - `coords`
  - `data`
  - `metadata`
- `ErrorRaised` 包含 error type、message、step id。

实现 `EventBus`：

- `emit(event)`
- `subscribe(callback)`
- `events` list，用于测试和 dry-run。

测试：

- subscriber 能收到事件。
- event dict 可 JSON 序列化。

### 3. Procedure Model

实现基础 step：

```python
Step
ActionStep
ScanStep
AverageStep
MeasurementStep
RunStep
CleanupStep
Procedure
```

基础要求：

- 每个 step 有稳定 `id` 和 `name`。
- 每个 step 有 `enabled`。
- 每个 composite step 有 `body`。
- 不要在构造 step 时执行任何动作。

语义：

- `ActionStep`：执行一个 callable 或 resource method 占位。
- `ScanStep`：遍历一个参数的多个值，并把当前值写入 context。
- `AverageStep`：重复执行 body，可以先不实现复杂 reducer，但必须记录 average index。
- `MeasurementStep`：生成 `point_id`，发出 MeasurementStarted/Completed，执行 body。
- `RunStep`：表示一个硬件运行单元；在本阶段只作为 composite step dry-run 执行 body。
- `CleanupStep`：出错或结束时执行。

测试：

- 嵌套 scan 顺序正确。
- disabled step 不执行。
- measurement 内多个 action 共享同一个 point_id。

### 4. ExperimentContext

实现：

```python
ExperimentContext
```

要求：

- 保存当前 parameters。
- 保存当前 coords。
- 保存 current_point_id。
- 保存 arbitrary resources/mock resources。
- 提供 `resolve(value)`：
  - 如果是 ParameterRef，返回当前参数值。
  - 如果是 dict/list，递归解析。
  - 其他值原样返回。
- 提供 point id 生成器。

测试：

- 参数引用解析。
- point_id 单调唯一。

### 5. Executor

实现：

```python
ExperimentExecutor
```

要求：

- 接收 `Procedure`、`ExperimentContext`、`EventBus`。
- 支持 `dry_run=True`。
- 执行状态至少包括：
  - `created`
  - `running`
  - `completed`
  - `failed`
- 发出 run started/completed。
- 每个 step 发出 started/completed。
- 出错时发出 ErrorRaised。
- 出错时仍执行 cleanup。
- 不要实现线程、GUI、真实 pause/resume，这些后续再做。

ActionStep 执行策略：

- 如果 action 是 Python callable，调用它。
- callable 参数需要通过 context.resolve 解析。
- callable 可以返回：
  - `None`
  - scalar
  - dict
- 如果 ActionStep 有 `save_as`，把返回值打包成 DataPoint event。

示例：

```python
def mock_counts(freq, tau):
    return {"counts_mean": 1234.0, "raw_bins": [1, 2, 3]}
```

测试：

- dry-run 一维 scan。
- dry-run 二维 scan。
- measurement point 事件数量正确。
- ActionStep save_as 产生 DataPoint。
- action 抛异常后状态为 failed，cleanup 被执行。

---

## 推荐最小 API 示例

实现后，下面这种测试代码应该可行：

```python
from qulab.core import (
    ActionStep,
    AverageStep,
    ExperimentContext,
    ExperimentExecutor,
    MeasurementStep,
    Procedure,
    RunStep,
    ScanStep,
    ScanValues,
    EventBus,
    P,
)

def set_frequency(freq_hz):
    return None

def set_tau(tau_s):
    return None

def read_counts(freq_hz, tau_s):
    return {"counts_mean": freq_hz * 0 + tau_s * 0 + 1000}

procedure = Procedure(
    name="dry_run_rabi_2d",
    body=[
        ScanStep(
            name="mw_freq_hz",
            values=ScanValues.linspace(2.86e9, 2.88e9, 3),
            body=[
                ActionStep(
                    name="set_mw",
                    action=set_frequency,
                    kwargs={"freq_hz": P("mw_freq_hz")},
                ),
                ScanStep(
                    name="tau_s",
                    values=ScanValues.linspace(20e-9, 100e-9, 5),
                    body=[
                        MeasurementStep(
                            name="point",
                            body=[
                                ActionStep(
                                    name="set_tau",
                                    action=set_tau,
                                    kwargs={"tau_s": P("tau_s")},
                                ),
                                AverageStep(
                                    name="avg",
                                    count=2,
                                    body=[
                                        RunStep(
                                            name="readout",
                                            body=[
                                                ActionStep(
                                                    name="read_counts",
                                                    action=read_counts,
                                                    kwargs={
                                                        "freq_hz": P("mw_freq_hz"),
                                                        "tau_s": P("tau_s"),
                                                    },
                                                    save_as="counts",
                                                )
                                            ],
                                        )
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        )
    ],
)

bus = EventBus()
ctx = ExperimentContext()
executor = ExperimentExecutor(procedure, ctx, bus, dry_run=True)
executor.run()

assert executor.state == "completed"
assert any(event.type == "DataPoint" for event in bus.events)
```

不要求完全照这个 API，但最终能力必须等价，并且测试中要展示类似用法。

---

## 严格禁止

- 不要实现 GUI。
- 不要连接真实硬件。
- 不要导入 `nidaqmx`、`pyvisa`、`serial`、ASG DLL 或 `../pycontrol`。
- 不要把 storage/HDF5 做进 executor。
- 不要让 plotting 依赖 executor 内部细节。
- 不要用全局变量保存实验状态。
- 不要吞异常。
- 不要写入 `runs/` 或 `data/`，测试用临时目录或纯内存。

---

## 验证命令

完成后运行：

```bash
PYTHONPATH=src python -c "import qulab; print(qulab.__version__)"
python -m pytest
```

如果新增了格式化或 lint 工具，也可以运行，但不要要求网络安装依赖。

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 实现了哪些对象。
3. 运行了哪些验证命令，结果是什么。
4. 还没做什么，明确留给后续 worker。
5. 是否修改了公共 API。

---

## 后续 worker 依赖

这个 worker 完成后，后续 worker 才能继续：

- adapter worker：把 mock callable 替换为 capability/resource 调用。
- storage worker：订阅 EventBus，把事件写入 run store。
- config worker：把 YAML 解析为 Procedure。
- gui worker：把 Procedure 显示为 procedure tree。

