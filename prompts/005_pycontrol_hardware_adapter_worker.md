# Prompt 005: Pycontrol Hardware Adapter + Smoke Test Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在已有无硬件闭环和 GUI MVP 的基础上，进入真实硬件准备阶段：实现 pycontrol adapter、真实硬件 config 示例、硬件 smoke test CLI、hardware-marked tests、以及多频率源配置示例。这个 worker 可以一次性做多一点，但必须把默认测试保持为无硬件可通过。

---

## /goal

在当前 `qulab` 项目中实现真实硬件接入的第一阶段：新增 pycontrol adapters，把已有 `../pycontrol` 驱动包装为 qulab capability resources；新增真实硬件配置模板和安全 smoke test CLI，使用户可以在实验台上显式运行连接检查、ASG/NI/MW/AWG 基础动作和 dry-run-to-hardware 配置预检。必须同时增加多频率源 YAML 示例，证明框架支持一个频率源固定另一个扫描、或两个频率源嵌套扫描。默认 `python -m pytest` 仍不得要求真实硬件，必须通过。

成功标准：

1. 阅读并遵守项目蓝图、adapter、sync、hardware 文档。
2. 实现 `src/qulab/instruments/adapters/pycontrol.py` 或拆分为多个 pycontrol adapter 文件。
3. 不修改 `../pycontrol` 源码。
4. pycontrol driver 必须延迟导入：只能在 adapter `connect()` 或显式 hardware probe 中导入，不能让普通 import 因缺硬件 SDK 失败。
5. 默认 tests 仍使用 mock，无硬件也能 `python -m pytest` 通过。
6. 新增 hardware tests，必须标记 `@pytest.mark.hardware`，默认不运行。
7. 新增安全 CLI，例如：
   - `python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --dry-run`
   - `python -m qulab.scripts.hardware_check --config ... --connect-only`
8. CLI 默认必须是安全模式，不输出微波、不启动 ASG 长时间播放、不写危险 AO 电压。
9. 支持 pycontrol adapters：
   - ASG24100 -> `PulseSequencer` + `TriggerSource`
   - NIDAQ -> `DAQCounter` + `AnalogInput` + `AnalogOutput` + `TriggerReceiver`
   - LMX2572 -> `MicrowaveSource`
   - Rigol DG/AWG -> `WaveformGenerator` + optional `TriggerReceiver`
10. 新增 config 模板：
    - `configs/setups/real_nv_setup.template.yaml`
    - `configs/experiments/hardware_odmr.template.yaml`
    - `configs/experiments/dry_run_two_mw_scan.yaml`
11. 多频率源示例必须包含：
    - `mw_drive` fixed + `mw_probe` scanned。
    - 两个资源都用 mock adapter，默认可测试。
    - 文档说明真实硬件时把 adapter 改为 pycontrol adapter。
12. 新增测试覆盖：
    - pycontrol adapter import 不触发硬件导入。
    - registry 能注册 pycontrol adapter factories。
    - hardware config template 能 parse/preflight。
    - multi-MW YAML 能 parse 并 dry-run。
13. 更新 README 和 adapter/sync 文档，说明如何从 mock 切换到 pycontrol，以及如何安全实测。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ADAPTER_REQUIREMENTS.md`
3. `docs/HARDWARE_SYNC.md`
4. `docs/CONFIG_SCHEMA.md`
5. `docs/OPERATOR_UI.md`
6. `workers/adapter_worker.md`
7. `workers/sync_worker.md`
8. `workers/qa_worker.md`

同时查看：

```text
src/qulab/core/
src/qulab/storage/
src/qulab/config/
src/qulab/instruments/
src/qulab/sync/
src/qulab/gui/
../pycontrol/README.md
../pycontrol/PulseGenerator/driver.py
../pycontrol/DataAcquisition/driver.py
../pycontrol/SignalGenerator/driver.py
../pycontrol/AWG/driver.py
```

只需要读取 `../pycontrol` 的公开接口和示例，不要修改它。

---

## 当前项目目录

项目根目录：

```text
/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab
```

新增代码建议放在：

```text
src/qulab/instruments/adapters/pycontrol.py
src/qulab/scripts/hardware_check.py
```

测试：

```text
tests/unit/test_pycontrol_adapter_import.py
tests/unit/test_multi_mw_config.py
tests/integration/test_hardware_templates_parse.py
tests/hardware/test_pycontrol_smoke.py
```

新增示例：

```text
configs/setups/real_nv_setup.template.yaml
configs/experiments/hardware_odmr.template.yaml
configs/experiments/dry_run_two_mw_scan.yaml
```

---

## 具体实现要求

### 1. Adapter 命名

建议 adapter names：

```text
pycontrol_asg
pycontrol_ni
pycontrol_lmx
pycontrol_awg
```

并保持 mock names 已有兼容。

### 2. 延迟导入

严禁在模块顶层导入 pycontrol 真实 driver。

正确：

```python
class PycontrolLMXAdapter:
    def connect(self) -> None:
        from SignalGenerator.driver import LMX2572Driver
        self._driver = LMX2572Driver(...)
```

如果 pycontrol 不在 `sys.path`：

- 支持 config 中 `pycontrol_path`。
- 支持环境变量 `QULAB_PYCONTROL_PATH`。
- 报错必须清楚。

### 3. Base Adapter 行为

每个 adapter 必须提供：

- `connect()`
- `disconnect()`
- `health_check()`
- `snapshot()`
- `capabilities()`
- `simulation` flag

hardware 模式连接失败必须报错。不要静默切换 simulation。

### 4. LMX / MicrowaveSource

包装 pycontrol `LMX2572Driver`。

方法：

- `connect()`
- `disconnect()`
- `set_frequency(freq_hz)`
- `set_power(power_dbm)`，如果 pycontrol power 不是 dBm，文档和 snapshot 里说明。
- `output_on()`
- `output_off()`
- `snapshot()`

config 示例：

```yaml
mw_drive:
  adapter: pycontrol_lmx
  capabilities: [microwave_source]
  port: COM5
  baudrate: 921600
  output_type: RFH
  simulation: false
  pycontrol_path: ../pycontrol
```

### 5. ASG / PulseSequencer

包装 pycontrol `ASG24100Driver`。

方法：

- `connect()`
- `disconnect()`
- `load_sequence(path=None, sequence=None, code=None)`
- `set_sequence_param(name, value)`，MVP 可以只记录参数，后续由 sequence template 应用。
- `compile_sequence()`，MVP 可以 no-op 或返回 current code。
- `configure_trigger(...)`
- `arm()`
- `start()`
- `stop()`
- `sequence_snapshot()`
- `snapshot()`

安全要求：

- `start()` 在 smoke CLI 中默认不调用，除非用户传 `--allow-output`。
- 如果要调用 ASG 输出，必须明确提醒并要求 CLI flag。

### 6. NI / DAQ

包装 pycontrol `NIDAQDriver`。

方法：

- `connect()`
- `disconnect()`
- `configure_counter(sample_rate, samples, source=None, trigger=None)`
- `arm()`，MVP 可记录 armed 状态，真实 NI task 可能在 read 时创建。
- `read_counts()`
- `read_counts_binned()`
- `read_analog()`
- `set_voltage(channel, voltage)`，只在 explicit allow flag 下用于 smoke。
- `stop()`
- `snapshot()`

安全要求：

- 默认 smoke 不输出 AO 电压。
- 如果 config 有 AO 写入，hardware_check 默认拒绝，除非 `--allow-ao`。

### 7. AWG / WaveformGenerator

包装 pycontrol `RigolDG5504Driver`。

方法：

- `connect()`
- `disconnect()`
- `upload_waveform(name, data, sample_rate=None)`
- `play(name)`
- `stop()`
- `snapshot()`

MVP 可以只实现 connect/snapshot/disconnect，其他方法抛 `InstrumentUnsupportedOperation` 或清楚 NotImplemented。

### 8. Registry

默认 `InstrumentRegistry(register_defaults=True)` 可以注册 pycontrol adapters，但导入 registry 不能导入真实 pycontrol。

可以在 `register_defaults()` 中注册 adapter class/factory；只要 factory 创建对象时仍不连接硬件即可。

### 9. Hardware Config Templates

`real_nv_setup.template.yaml` 要明确是模板，不含真实危险默认值。

示例结构：

```yaml
resources:
  mw_drive:
    adapter: pycontrol_lmx
    capabilities: [microwave_source]
    port: COM5
    output_type: RFH
    simulation: false
    pycontrol_path: ../pycontrol

  asg:
    adapter: pycontrol_asg
    capabilities: [pulse_sequencer, trigger_source]
    address: auto
    simulation: false
    pycontrol_path: ../pycontrol

  daq:
    adapter: pycontrol_ni
    capabilities: [daq_counter, analog_input, analog_output, trigger_receiver]
    device: Dev2
    simulation: false
    pycontrol_path: ../pycontrol
```

`hardware_odmr.template.yaml` 应使用低风险流程，默认可以 parse/preflight，但不应默认打开输出。

### 10. Multi-Frequency Source Example

`dry_run_two_mw_scan.yaml` 必须使用 mock：

```yaml
resources:
  mw_drive:
    adapter: mock_microwave
    capabilities: [microwave_source]
    simulation: true
  mw_probe:
    adapter: mock_microwave
    capabilities: [microwave_source]
    simulation: true
```

流程包含：

- setup 固定 `mw_drive`。
- scan `probe_freq_hz` 设置 `mw_probe`。
- 可选再提供 nested scan `drive_freq_hz` + `probe_freq_hz`。

测试必须证明：

- config parser 接受两个 microwave resources。
- dry-run 产生两个频率坐标或至少正确调用两个 resources。

### 11. Hardware Check CLI

提供：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --connect-only
```

功能：

- 加载 config。
- 创建 registry/resources。
- `--dry-run` 只 parse、preflight、打印资源，不连接。
- `--connect-only` 只 connect + health_check + snapshot + disconnect。
- 默认禁止输出动作。
- `--allow-output` 才允许 ASG/AWG/MW output。
- `--allow-ao` 才允许 NI AO。

CLI 输出必须清楚列出：

- resource name。
- adapter。
- capabilities。
- simulation/hardware。
- connect status。
- snapshot。
- warnings/errors。

### 12. Hardware Tests

默认测试不能碰硬件。

hardware tests 必须：

```python
import pytest

pytestmark = pytest.mark.hardware
```

并且需要环境变量才运行：

```text
QULAB_HARDWARE_CONFIG=/path/to/real_nv_setup.yaml
```

没有环境变量时 skip。

---

## 严格禁止

- 不要修改 `../pycontrol`。
- 不要在 import 阶段连接硬件。
- 不要在默认测试中连接硬件。
- 不要默认打开微波输出、ASG 输出、AWG 输出、NI AO。
- 不要静默 fallback 到 simulation。
- 不要让 GUI/core/storage 依赖 pycontrol。
- 不要把 vendor DLL、SDK、真实数据提交到项目。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.instruments.adapters.pycontrol import PycontrolLMXAdapter; print(PycontrolLMXAdapter.__name__)"
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/dry_run_two_mw_scan.yaml --dry-run
```

不要在没有用户明确许可时运行 connect-only 或 allow-output。

如果用户在实验台上明确要求实测，才运行：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <real-config> --connect-only
```

---

## 文档更新要求

完成后至少更新：

```text
README.md
docs/ADAPTER_REQUIREMENTS.md
docs/HARDWARE_SYNC.md
docs/CONFIG_SCHEMA.md
docs/IMPLEMENTATION_ORDER.md
workers/adapter_worker.md
```

必须说明：

- 多频率源如何配置。
- mock -> pycontrol 如何切换。
- hardware_check 的安全默认值。
- 真实硬件实测前 checklist。

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 实现了哪些 pycontrol adapters。
3. 新增了哪些 hardware/multi-MW config 示例。
4. 运行了哪些验证命令，结果是什么。
5. 是否保持默认测试无硬件依赖。
6. 是否保证 import 阶段不导入 pycontrol/hardware SDK。
7. 哪些真实硬件动作仍需用户授权后才能运行。
8. 还没做什么，明确留给后续 worker。

