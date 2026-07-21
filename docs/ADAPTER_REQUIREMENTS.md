# Adapter Requirements

adapter 是本项目最重要的长期扩展点。所有 worker 实现 adapter 前必须阅读本文件。

## 1. 基本原则

1. adapter 包装已有驱动，不复制驱动。
2. adapter 暴露能力，不暴露厂商全部细节。
3. 厂商特有功能可以通过 `advanced` namespace 暴露，但实验模板不能依赖它。
4. import 阶段不能强制连接硬件。
5. import 阶段不能强制加载 Windows-only DLL。
6. hardware 模式不能静默 fallback 到 simulation。
7. simulation 模式必须显式开启。

## 1.1 已有驱动命名一致是否等于抽象

如果现有驱动已经在各个型号 class 中维持了相似的方法名，例如 `connect()`、`disconnect()`、`start()`、`stop()`、`set_frequency()`，这已经是很好的驱动层抽象，但还不完全等于 qulab 需要的实验框架抽象。

驱动层抽象解决：

- 如何连接某个型号。
- 如何调用这个型号的 SDK。
- 如何设置这个型号支持的参数。
- 如何处理这个型号的底层通信。

adapter/capability 层解决：

- 实验模板需要什么能力，而不是需要什么型号。
- 不同型号单位、参数名、返回值、异常行为如何统一。
- 一个仪器如何声明自己能扮演哪些角色，例如 `PulseSequencer`、`TriggerSource`、`DAQCounter`。
- 如何提供 `snapshot()`、`health_check()`、`simulation`、`preflight` 所需信息。
- 如何让 GUI 自动生成基础控制面板。
- 如何让 storage 记录统一的仪器状态。

因此，即使已有驱动命名已经比较统一，也建议保留 adapter 层。adapter 可以很薄，但这个边界很重要。

推荐结构：

```text
pycontrol driver:
  ASG24100Driver.upload_and_run(...)
  NIDAQDriver.get_photon_counts(...)
  LMX2572Driver.set_frequency(...)

qulab adapter:
  PycontrolASGAdapter implements PulseSequencer + TriggerSource
  PycontrolNIAdapter implements DAQCounter + AnalogInput + AnalogOutput + TriggerReceiver
  PycontrolLMXAdapter implements MicrowaveSource

experiment procedure:
  uses PulseSequencer, DAQCounter, MicrowaveSource
```

结论：

- 继续保持和改进驱动 class 的统一命名。
- 额外保留 adapter 层。
- 不在实验模板中直接依赖 pycontrol 具体 class。
- 新驱动开发时可以提供 driver template，但 driver template 不替代 adapter。

## 2. 必需方法

每个 adapter 必须提供：

```python
class InstrumentAdapter:
    name: str
    model: str
    vendor: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def health_check(self) -> HealthStatus: ...
    def snapshot(self) -> dict: ...
    def capabilities(self) -> set[str]: ...
```

## 3. 能力接口

### 3.1 MicrowaveSource

必须：

- `set_frequency(freq_hz: float)`
- `set_power(power_dbm: float)`, 如果硬件不是真 dBm，应在 docstring 和 snapshot 说明单位。
- `output_on()`
- `output_off()`

应该：

- `get_frequency()`
- `get_power()`

### 3.2 PulseSequencer

必须：

- `load_sequence(sequence)`
- `set_sequence_param(name, value)`
- `compile_sequence()`，如果该仪器需要软件编译；如果由厂商软件/硬件处理，可为空实现或返回已有 sequence id。
- `configure_trigger(...)`
- `arm()`
- `start()`
- `stop()`

应该：

- `estimate_duration()`
- `is_running()`
- `sequence_snapshot()`

### 3.3 DAQCounter

必须：

- `configure_counter(sample_rate, samples, source=None, trigger=None)`
- `arm()`
- `read_counts(timeout=None)`
- `stop()`

应该：

- `read_counts_binned()`
- `snapshot_task_config()`

### 3.7 TriggerSource

必须：

- `configure_trigger_output(channel, mode, edge=None, level=None)`
- `trigger_snapshot()`

### 3.8 TriggerReceiver

必须：

- `configure_trigger_input(channel, edge="rising")`
- `arm()`
- `trigger_snapshot()`

### 3.4 AnalogInput

必须：

- `configure_ai(channels, sample_rate, samples, terminal_config=None)`
- `read_analog(timeout=None)`

### 3.5 AnalogOutput

必须：

- `set_voltage(channel, voltage)`
- `set_waveform(channel, waveform, sample_rate)`, 可选。

### 3.6 WaveformGenerator

必须：

- `upload_waveform(name, data, sample_rate=None)`
- `play(name)`
- `stop()`

## 4. pycontrol 适配要求

Qulab 默认随项目携带一份 pycontrol driver tree：

```text
drivers/pycontrol/
```

它来自原先的外部 pycontrol driver tree，用于保证换电脑或移动项目目录后 adapter 仍能找到驱动。默认运行只使用项目内 `drivers/pycontrol`；若实验室需要临时测试另一份 pycontrol，可通过 resource 里的 `pycontrol_path` 或环境变量 `QULAB_PYCONTROL_PATH` 显式覆盖默认路径。

`drivers/pycontrol` 当前包含：

- `PulseGenerator.driver.ASG24100Driver`
- `DataAcquisition.driver.NIDAQDriver`
- `SignalGenerator.driver.LMX2572Driver`
- `AWG.driver.RigolDG5504Driver`

适配策略：

- 在 adapter 的 `connect()` 内部导入 pycontrol driver。
- pycontrol 路径默认使用项目根目录下的 `drivers/pycontrol`；也可通过 config 或环境变量覆盖，不写死绝对路径。
- 如果导入失败，hardware 模式报错，simulation 模式使用 mock。
- adapter 不修改 pycontrol 源码。

## 5. Snapshot 要求

每个 adapter 的 `snapshot()` 至少返回：

```python
{
    "name": "mw",
    "adapter": "pycontrol_lmx",
    "vendor": "Peking University",
    "model": "LMX2572 RF6G",
    "connected": True,
    "simulation": False,
    "capabilities": ["microwave_source"],
    "settings": {
        "frequency_hz": 2870000000.0,
        "power": 10,
        "output": True
    }
}
```

## 6. 错误处理

错误必须分类：

- `InstrumentConnectionError`
- `InstrumentConfigurationError`
- `InstrumentTimeoutError`
- `InstrumentSafetyError`
- `InstrumentUnsupportedOperation`

不得：

- `except Exception: pass`
- 返回 `False` 但不说明原因。
- 自动忽略硬件设置失败。

## 7. 当前 pycontrol Adapter 名称

默认 registry 注册以下硬件 adapter：

- `pycontrol_asg`：包装 `PulseGenerator.driver.ASG24100Driver`，提供 `pulse_sequencer` 和 `trigger_source`。
- `pycontrol_ni`：包装 `DataAcquisition.driver.NIDAQDriver`，提供 `daq_counter`、`analog_input`、`analog_output` 和 `trigger_receiver`。
- `pycontrol_lmx`：包装 `SignalGenerator.driver.LMX2572Driver`，提供 `microwave_source`。
- `pycontrol_awg`：包装 `AWG.driver.RigolDG5504Driver`，提供 `waveform_generator` 和 `trigger_receiver`。

这些 adapter 可以被 import 和注册，但只有 `connect()` 会导入 pycontrol driver、加载 SDK、打开串口/VISA/NI 资源或搜索 ASG。路径优先级为：resource `pycontrol_path`、`QULAB_PYCONTROL_PATH`、项目内 `drivers/pycontrol`。相对路径优先按 Qulab 项目根目录解析。

mock 切换到真实硬件的最小变化：

```yaml
mw_drive:
  adapter: pycontrol_lmx
  capabilities: [microwave_source]
  port: COM5
  baudrate: 921600
  output_type: RFH
  simulation: false
  pycontrol_path: drivers/pycontrol
```

不要把 `simulation: true` 用在 pycontrol adapter 上；真实硬件失败必须暴露真实错误。无硬件测试和 GUI dry-run 继续使用 `mock_*` adapter。
