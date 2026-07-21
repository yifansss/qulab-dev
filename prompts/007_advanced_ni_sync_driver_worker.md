# Prompt 007: Advanced NI Sync Driver + Qulab Adapter Integration Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是专门解决 NI 板卡同步能力不足的问题：在平行目录 `../pycontrol` 中新增一个更完整的 NI 同步驱动，不破坏原有 `DataAcquisition/driver.py`；同时更新 `qulab` 的 pycontrol NI adapter，使其可以选择使用新驱动。这个 worker 需要同时理解 NI master、ASG master、mixed mode、AO 慢变量、AI/Counter 高速采集、1 点对多点采集这些实验模式。

重要：`../pycontrol` 是当前 `qulab` 项目的平行目录，可能不在当前 worker 的默认可写 root 中。如果写入 `../pycontrol` 被沙箱阻止，worker 必须请求写权限或明确把 patch 写在 `qulab` 内供用户应用；不要偷偷改旧 driver，不要破坏现有 pycontrol API。

---

## /goal

在 `../pycontrol/DataAcquisition/` 中新增一个高级 NI 同步驱动，保留原有 `driver.py` 不动；该新驱动必须支持外部 trigger 下的 AI/counter 采集、NI 内部 AO/AI 同步、AO 慢更新 + AI 高速采集、ASG master / NI master / mixed mode 三种同步模式，以及 1 点对多点采集。随后更新 `qulab` 的 `PycontrolNIAdapter`，允许通过 config 选择旧 `NIDAQDriver` 或新高级驱动。默认 `python -m pytest` 仍必须无硬件通过；真实 NI/ASG 硬件测试必须使用 `@pytest.mark.hardware` 和环境变量显式启用。

成功标准：

1. 不修改 `../pycontrol/DataAcquisition/driver.py` 原文件。
2. 新增高级 driver，例如：
   - `../pycontrol/DataAcquisition/sync_driver.py`
   - class `NISyncDAQDriver`
3. 新 driver 顶层 import 不应强制要求 NI 硬件存在；可以延迟 import `nidaqmx` 到 `__init__` 或 `connect()`，并提供清楚错误。
4. 支持三种同步模式：
   - `asg_master`
   - `ni_master`
   - `mixed`
5. 支持外部 trigger AI 采集：
   - start trigger from PFI
   - optional external sample clock from PFI
   - finite samples
   - multi-channel AI
6. 支持外部 trigger counter/bin 采集：
   - APD/count source terminal
   - sample clock terminal from ASG PFI or internal counter
   - optional start trigger
   - return binned counts
7. 支持 NI 内部 AO/AI 同步：
   - AO waveform and AI acquisition start together
   - support AO rate and AI rate distinction where possible
   - if hardware requires same sample clock for a specific mode, document and validate
8. 支持 AO 慢变量 + AI 高速采集：
   - set AO static value per point
   - wait settle time
   - acquire N AI samples at high rate
   - return full trace and summary
9. 支持 1 点对多点采集：
   - one scan point can return vector/matrix data
   - result shape and channel metadata included
10. 更新 `qulab` adapter：
    - config 可选择新 driver，例如 `driver: sync` 或 `driver_class: DataAcquisition.sync_driver.NISyncDAQDriver`
    - 默认仍兼容旧 `DataAcquisition.driver.NIDAQDriver`
    - 新 adapter methods 暴露 configure/arm/read/stop 的状态式 API
11. 新增 YAML 示例：
    - ASG master counter readout
    - NI master AO/AI sweep
    - mixed AO slow setpoint + ASG pulse readout
12. 新增 tests：
    - 无硬件 unit tests 使用 fake nidaqmx 或 monkeypatch，验证 task configuration intent
    - qulab adapter import 不导入硬件
    - config parse/preflight
    - hardware tests 默认 skip
13. 更新文档：
    - 什么时候 ASG master
    - 什么时候 NI master
    - 什么时候 mixed mode
    - 需要怎么接线
    - 当前 driver 限制

---

## 必须先阅读

worker 开始前必须阅读：

```text
PROJECT_BLUEPRINT.md
docs/HARDWARE_SYNC.md
docs/ADAPTER_REQUIREMENTS.md
docs/CONFIG_SCHEMA.md
workers/adapter_worker.md
workers/sync_worker.md
workers/qa_worker.md
../pycontrol/README.md
../pycontrol/DataAcquisition/driver.py
src/qulab/instruments/adapters/pycontrol.py
src/qulab/sync/
```

重点理解：

- 当前 `PycontrolNIAdapter` 通过 `pycontrol_path` 或环境变量 `QULAB_PYCONTROL_PATH` 延迟导入外部 `../pycontrol`。
- 目前 NI adapter 默认导入旧 driver：`DataAcquisition.driver.NIDAQDriver`。
- 旧 driver 仍需保留，因为现有程序可能依赖它。
- 新 driver 是新增能力，不是替换旧文件。

---

## 当前调用关系解释

当前 qulab 不是把 pycontrol 复制进来，而是通过外部路径调用：

```yaml
daq:
  adapter: pycontrol_ni
  device: Dev2
  pycontrol_path: ../pycontrol
```

adapter 在 `connect()` 时做：

```python
import DataAcquisition.driver
driver_cls = NIDAQDriver
```

新 worker 应改成可配置：

```yaml
daq:
  adapter: pycontrol_ni
  driver: sync
  device: Dev2
  pycontrol_path: ../pycontrol
```

或：

```yaml
daq:
  adapter: pycontrol_ni
  driver_class: DataAcquisition.sync_driver.NISyncDAQDriver
```

默认不写 `driver` 时继续使用旧 `DataAcquisition.driver.NIDAQDriver`。

---

## 同步模式定义

### 1. ASG Master

适合：

- Rabi/Ramsey/Echo。
- APD gate readout。
- ASG 控制 laser/MW/readout gate。
- NI 只负责在 ASG trigger/gate/sample clock 下采集。

物理关系：

```text
ASG TTL channel -> NI PFI start trigger / sample clock / gate
APD TTL         -> NI counter source PFI
```

软件顺序：

```text
configure NI task
arm NI
arm ASG
start ASG
NI acquires/counts from hardware timing
read NI
```

Driver methods should support：

```python
configure_counter_external_clock(
    counter_channel="ctr0",
    count_source="/Dev2/PFI0",
    sample_clock="/Dev2/PFI1",
    samples=1000,
    start_trigger="/Dev2/PFI2" | None,
    edge="rising",
)

configure_ai_external_trigger(
    channels=["ai0", "ai1"],
    sample_rate=1e6,
    samples=1000,
    start_trigger="/Dev2/PFI0",
    sample_clock=None | "/Dev2/PFI1",
)
```

### 2. NI Master

适合：

- NI AO 输出扫描电压。
- NI AI 多通道同步采集。
- 不涉及 ASG 精密 pulse sequence 的连续扫描。

物理关系：

```text
NI AO and AI share internal start trigger / sample clock strategy
```

软件顺序：

```text
configure AO waveform
configure AI acquisition
start AI first if waiting on AO start trigger
start AO
read AI
```

Driver methods should support：

```python
configure_ao_ai_sync(
    ao_channels=["ao0"],
    ai_channels=["ai0", "ai1"],
    ao_waveform=[...],
    ao_rate=1000,
    ai_rate=100000,
    ai_samples_per_ao_point=100,
    mode="step_and_sample" | "shared_clock",
)
```

Important：

- 如果 AO 和 AI 必须共享同一 sample clock，则 AO rate == AI rate。
- 如果要 AO 慢、AI 快，不要强行一一对应；应使用 step-and-sample 模式：
  - AO 设置一个点。
  - 等待 settle。
  - AI 高速采 N 个点。
  - 重复。

### 3. Mixed Mode

适合：

- NI AO 设置慢变量，例如磁场、压电、电压。
- 每个 AO 点内由 ASG 执行 pulse sequence。
- NI counter/AI 在 ASG gate/trigger 下采集。

软件顺序：

```text
for ao_value in scan:
    NI set AO static value
    wait settle
    configure/arm NI counter or AI
    arm ASG
    start ASG
    read NI trace/counts
```

Driver support：

```python
set_ao_static(channel, voltage)
wait_settle(seconds)
configure_counter_external_clock(...)
arm()
read()
```

---

## 新 pycontrol driver 设计

新增文件：

```text
../pycontrol/DataAcquisition/sync_driver.py
```

推荐 class：

```python
class NISyncDAQDriver:
    def __init__(self, verbose: bool = True, strict_hardware: bool = True):
        ...
```

### Required public API

Connection:

```python
connect(device_name: str = "Dev2") -> bool
disconnect() -> bool
is_connected
snapshot() -> dict
health_check() -> dict
```

Task lifecycle:

```python
clear_tasks() -> None
arm() -> bool
start() -> bool
read(timeout: float | None = None) -> dict
stop() -> bool
```

ASG master:

```python
configure_counter_external_clock(...)
configure_counter_start_trigger(...)
configure_ai_external_trigger(...)
```

NI master:

```python
configure_ao_ai_shared_clock(...)
configure_ao_ai_step_and_sample(...)
run_ao_ai_step_and_sample(...)
```

Mixed:

```python
set_ao_static(channel: str, voltage: float) -> bool
configure_point_readout(...)
run_point_readout(...)
```

Convenience:

```python
read_counts_binned(...)
read_analog_trace(...)
```

### Return format

Return dicts, not only raw arrays:

```python
{
    "kind": "counter_bins",
    "data": {
        "counts_mean": 123.4,
        "photon_bins": [...],
        "time_axis_s": [...]
    },
    "metadata": {
        "sample_rate": 1000000.0,
        "samples": 1000,
        "count_source": "/Dev2/PFI0",
        "sample_clock": "/Dev2/PFI1",
        "start_trigger": "/Dev2/PFI2"
    }
}
```

For AI:

```python
{
    "kind": "analog_trace",
    "data": {
        "analog_trace": [[...], [...]],
        "analog_channels": ["ai0", "ai1"],
        "time_axis_s": [...]
    },
    "metadata": {...}
}
```

This maps cleanly to Qulab `DataPoint` and RunStore.

---

## Qulab adapter integration

Update:

```text
src/qulab/instruments/adapters/pycontrol.py
```

Current `PycontrolNIAdapter.connect()` loads:

```text
DataAcquisition.driver.NIDAQDriver
```

Add selection:

```python
driver_mode = config.get("driver", "legacy")
if driver_mode == "sync":
    module = "DataAcquisition.sync_driver"
    cls = "NISyncDAQDriver"
else:
    module = "DataAcquisition.driver"
    cls = "NIDAQDriver"
```

Also support explicit:

```yaml
driver_class: DataAcquisition.sync_driver.NISyncDAQDriver
```

Adapter should expose:

```python
configure_counter(...)
configure_counter_external_clock(...)
configure_ai(...)
configure_ai_external_trigger(...)
configure_ao_ai_sync(...)
configure_ao_ai_step_and_sample(...)
set_voltage(...)
set_ao_static(...)
arm()
read_counts()
read_analog()
read()
stop()
snapshot()
```

For legacy driver, unsupported advanced methods should raise `InstrumentUnsupportedOperation` with clear message.

---

## YAML examples to add

### 1. ASG master counter

```text
configs/experiments/hardware_asg_master_counter.template.yaml
```

Contains:

```yaml
resources:
  asg:
    adapter: pycontrol_asg
    pycontrol_path: ../pycontrol
  daq:
    adapter: pycontrol_ni
    driver: sync
    device: Dev2
    pycontrol_path: ../pycontrol

sync:
  master: asg
  triggers:
    - source: asg.ch5
      target: daq.PFI1
      edge: rising
      purpose: counter_sample_clock

procedure:
  - measurement:
      name: asg_master_point
      body:
        - call: daq.configure_counter_external_clock
          args:
            counter_channel: ctr0
            count_source: PFI0
            sample_clock: PFI1
            samples: 1000
        - run:
            name: readout
            steps:
              - call: daq.arm
              - call: asg.arm
              - call: asg.start
              - call: daq.read
                save_as: counts
```

### 2. NI master AO/AI step-and-sample

```text
configs/experiments/hardware_ni_master_ao_ai.template.yaml
```

Contains AO slow points and AI high samples per point.

### 3. Mixed mode

```text
configs/experiments/hardware_mixed_ao_asg_counter.template.yaml
```

Contains:

```yaml
scan ao_voltage:
  set daq AO static
  wait settle
  arm NI
  arm ASG
  start ASG
  read NI
```

If no wait step exists in core, implement a simple mock/adapter method `daq.wait_settle(seconds)` or add a safe `SleepStep` only if it does not complicate core. Prefer adapter method for now.

---

## Tests

Default tests must not require nidaqmx.

Use fake module/class monkeypatching for pycontrol new driver import if needed.

Required tests:

```text
tests/unit/test_ni_sync_driver_api_contract.py
tests/unit/test_pycontrol_ni_driver_selection.py
tests/unit/test_ni_sync_config_templates.py
tests/integration/test_ni_sync_yaml_dry_run.py
tests/hardware/test_ni_sync_hardware.py
```

Hardware tests:

- marked `@pytest.mark.hardware`
- skip unless `QULAB_HARDWARE_CONFIG` set
- connect/read-only only unless `QULAB_ALLOW_OUTPUT=1`

---

## Documentation updates

Update:

```text
README.md
docs/HARDWARE_SYNC.md
docs/ADAPTER_REQUIREMENTS.md
docs/CONFIG_SCHEMA.md
workers/adapter_worker.md
```

Must explain:

1. Current qulab adapter calls external `../pycontrol` via `pycontrol_path` / `QULAB_PYCONTROL_PATH`.
2. Legacy NI driver remains available.
3. New sync NI driver is selected by `driver: sync`.
4. ASG master wiring examples.
5. NI master AO/AI examples.
6. Mixed mode examples.
7. AO slow / AI fast rationale.
8. 1 point -> many samples storage mapping.

---

## Safety

Strictly forbidden:

- Do not modify old `../pycontrol/DataAcquisition/driver.py`.
- Do not require real NI hardware in default tests.
- Do not open ASG/MW output.
- Do not write NI AO in default tests.
- Do not connect hardware unless user explicitly runs hardware test/CLI with real config.
- Do not silently fall back from hardware to simulation.

---

## Validation commands

Run:

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.instruments.adapters.pycontrol import PycontrolNIAdapter; print(PycontrolNIAdapter.__name__)"
PYTHONPATH=../pycontrol python -c "from DataAcquisition.sync_driver import NISyncDAQDriver; print(NISyncDAQDriver.__name__)"
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/hardware_asg_master_counter.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/hardware_ni_master_ao_ai.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/hardware_mixed_ao_asg_counter.template.yaml --dry-run
```

If writing to `../pycontrol` needs approval, request it before editing. If approval is unavailable, create a patch file under:

```text
docs/patches/pycontrol_advanced_ni_sync_driver.patch
```

and report that it must be applied to `../pycontrol`.

---

## Final response requirements

Worker must report:

1. Whether it wrote directly to `../pycontrol` or produced a patch.
2. New driver file/class.
3. Qulab adapter selection behavior.
4. Supported sync modes.
5. New YAML examples.
6. Tests and validation commands.
7. Hardware actions still requiring explicit authorization.

