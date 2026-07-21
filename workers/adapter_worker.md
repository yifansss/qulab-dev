# Adapter Worker Specification

## Mission

实现 `src/qulab/instruments` 和 pycontrol adapters，使实验流程依赖 capability，而不是具体厂商型号。

## Must Read

- `PROJECT_BLUEPRINT.md`
- `docs/ADAPTER_REQUIREMENTS.md`
- `docs/HARDWARE_SYNC.md`

## Deliverables

1. `instruments/base.py`
2. `instruments/capabilities.py`
3. `instruments/registry.py`
4. `instruments/profiles.py`
5. `instruments/adapters/pycontrol_asg.py`
6. `instruments/adapters/pycontrol_ni.py`
7. `instruments/adapters/pycontrol_lmx.py`
8. `instruments/adapters/pycontrol_awg.py`
9. mock adapters for tests

## Adapter Rules

1. 不修改 `../pycontrol`。
2. 不在模块 import 阶段导入硬件 SDK。
3. `connect()` 内部导入具体驱动。
4. simulation 必须显式开启。
5. hardware 模式连接失败必须报错。
6. 所有 adapter 必须实现 `snapshot()`。

## pycontrol Mapping

ASG：

- wraps `PulseGenerator.driver.ASG24100Driver`
- provides `PulseSequencer`
- provides `TriggerSource`

NI：

- wraps `DataAcquisition.driver.NIDAQDriver`
- provides `DAQCounter`
- provides `AnalogInput`
- provides `AnalogOutput`
- provides `TriggerReceiver`

LMX：

- wraps `SignalGenerator.driver.LMX2572Driver`
- provides `MicrowaveSource`

AWG：

- wraps `AWG.driver.RigolDG5504Driver`
- provides `WaveformGenerator`
- provides `TriggerReceiver`

## Tests

必须提供 simulation/mock 测试，不要求真实硬件。

硬件测试放入 `tests/hardware`，默认不自动运行。

## Current Pycontrol Adapter Notes

已实现的第一阶段 adapter 集中在 `src/qulab/instruments/adapters/pycontrol.py`：

- `pycontrol_asg` -> `PycontrolASGAdapter`
- `pycontrol_ni` -> `PycontrolNIAdapter`
- `pycontrol_lmx` -> `PycontrolLMXAdapter`
- `pycontrol_awg` -> `PycontrolAWGAdapter`

重要约束：

- 不要在模块顶层导入 `PulseGenerator.driver`、`DataAcquisition.driver`、`SignalGenerator.driver`、`AWG.driver`、`nidaqmx`、`serial` 或 `pyvisa`。
- driver import、SDK 加载和设备枚举只能发生在 `connect()` 或显式硬件 probe 中。
- `pycontrol_path` 来自 resource config 或 `QULAB_PYCONTROL_PATH`；缺失时给清楚错误。
- `qulab.scripts.hardware_check --dry-run` 是默认安全预检入口。
- `--connect-only` 可以在实验台上验证连接，但仍不应打开 MW/ASG/AWG 输出或写 NI AO。

多频率源示例见 `configs/experiments/dry_run_two_mw_scan.yaml`。真实硬件迁移时保持 resource 名称和 procedure 不变，逐个把 `mock_microwave` 改为 `pycontrol_lmx` 并补齐端口。
