# Hardware Sync

## 1. 设计目标

`qulab` 不在 Python 中完成精密时序。Python 只负责：

- 配置仪器。
- 生成/加载序列。
- arm 设备。
- start master。
- 读取结果。
- 检查和记录同步关系。

纳秒到微秒级同步必须由硬件完成。

## 2. 默认硬件中心

默认以国仪量子 ASG24100 和 NI DAQ 为中心：

- ASG：主脉冲发生器和触发源。
- NI：计数、模拟采集、AO 输出、内部 counter routing。
- MW：微波源，通常慢速设置频率/功率，或通过 ASG 控制开关。
- AWG：波形发生器，通常由外部触发启动。

## 2.1 谁负责发采集信号

推荐默认架构是：ASG 负责发出硬件级 timing signal，NI 负责按该信号采集或计数。

典型情况：

1. Python/executor 先配置 NI 的采集任务，例如 counter、AI、sample rate、samples、trigger source。
2. Python/executor 让 NI 进入 armed/waiting 状态。
3. Python/executor 配置并 arm ASG。
4. Python/executor start ASG。
5. ASG 在 pulse sequence 中输出 TTL gate/trigger 到 NI PFI 或 counter source。
6. NI 在硬件层响应 ASG 信号并完成采集。
7. Python/executor 从 NI 读取结果。

也就是说，Python 不在每个精密时间点“命令 NI 采一下”。Python 只负责让 NI 准备好，真正的采集窗口、门控、触发边沿由 ASG/NI 硬件完成。

可接受变体：

- NI 使用内部 counter routing 产生采样时钟，ASG 提供 gate 或 start trigger。
- ASG 触发 AWG，AWG 输出模拟波形，NI 同步采集。
- 慢速扫描参数由 Python 设置，例如微波频率、磁场电压、温控设定。

不推荐：

- 用 Python `sleep` 对齐 laser、MW、DAQ readout。
- 在纳秒/微秒尺度反复从 Python 发命令触发采集。

## 2.2 大流程时序与单点内脉冲

框架中有两类“时序”，必须分开：

### A. Experiment Procedure Timing

这是宏观实验流程，属于 `core/procedure`：

```text
scan mw_freq
  scan tau_s
    measurement point
      mw.set_frequency
      asg.set_sequence_param(tau_s)
      daq.configure_or_arm
      asg.arm
      asg.start
      daq.read_counts
```

它描述“先做什么、后做什么”，时间尺度通常是毫秒到秒。

### B. Pulse Sequence Timing

这是单个 measurement point 内部的精密脉冲，属于 ASG/AWG 仪器子面板、sequence editor 和 `PulseSequencer` capability：

```text
laser init pulse
wait
mw pi/2 pulse
free evolution tau
mw pi pulse
free evolution tau
mw pi/2 pulse
laser readout pulse
APD gate / NI trigger
```

它描述 shot 内部的纳秒/微秒/毫秒级硬件时序。

在运行时，procedure 不展开每个纳秒脉冲。procedure 只设置 sequence 参数并触发 sequence：

```text
asg.set_sequence_param("tau_s", 500e-9)
daq.arm()
asg.arm()
asg.start()
daq.read_counts()
```

ASG 的 sequence 负责在正确时间输出激光、微波开关、NI gate/trigger 等 TTL。

## 2.3 单点测量的推荐执行单元

一个复杂 measurement point 推荐分成：

```text
Point Prepare:
  - set slow parameters: mw frequency, power, coil voltage
  - update sequence parameters: tau, readout delay, pulse width
  - optionally upload/compile sequence

Point Arm:
  - configure DAQ task
  - arm DAQ receiver
  - arm ASG/AWG source

Point Run:
  - start ASG master
  - hardware sequence emits triggers/gates
  - NI acquires/counts

Point Read:
  - read NI result
  - read optional analog trace
  - record point snapshots

Point Save:
  - emit raw arrays
  - emit scalar summary
  - mark point completed
```

这就是 `MeasurementStep`、`RunStep`、`SyncPlan` 的协作边界。

## 3. SyncPlan

SyncPlan 必须表达：

```python
SyncPlan(
    master="asg",
    triggers=[
        TriggerEdge(
            source="asg.ch5",
            target="daq.PFI0",
            edge="rising",
            purpose="readout_gate",
        )
    ],
    order={
        "configure": ["mw", "asg", "daq"],
        "arm": ["daq", "asg"],
        "start": ["asg"],
        "read": ["daq"],
    },
    safety_shutdown=["mw.output_off", "asg.stop", "daq.stop"],
)
```

## 4. Preflight Checks

MVP 必须检查：

1. 所有 sync resource 存在。
2. trigger source 和 target 字符串合法。
3. `arm` 顺序中 receiver 先于 source。
4. DAQ timeout 大于预计序列时间。
5. sample rate 和 samples 对应采样窗口合理。
6. average count 为正整数。
7. 扫描点数不为 0。

可用版增加：

1. 物理线缆 connection table。
2. NI PFI 通道占用冲突。
3. ASG 通道用途冲突。
4. 外部参考时钟检查。

### 4.1 Sequence Bundle Static Preflight

P9.2 在任何 executor/hardware action 前检查 `load_sequence_from_bundle`：外层 workflow
scan coverage、manifest trigger channel 与 `sync.triggers[].source`、DAQ start trigger 与
`sync.triggers[].target`/edge，以及 literal `samples / sample_rate` acquisition window。

Entry duration metadata 优先使用 `required_acquisition_s`，其次 `readout_window_s`，最后
`duration_s`。窗口小于需求是 error；metadata 或 literal args 不足时是 warning。trigger
channel 对明确 DAQ start-trigger workflow 缺失时是 error，仅作为 metadata hint 时是
warning。

这些检查不能推断物理线缆是否连接，也不建立虚构的 NI 型号 routing table。真实 PFI
route、极性、电平和设备吞吐仍必须通过 NI-DAQmx 与实验台测量确认。Prepare 不 connect、
arm、start 或打开输出。

## 5. Safety

任何失败必须执行 safety shutdown：

1. 停 ASG。
2. 停 AWG。
3. 关微波输出。
4. close DAQ task。
5. 写入 error event。

不得为了继续扫描而忽略硬件异常。

## 6. Safe Hardware Smoke Flow

第一阶段真实硬件接入使用 `qulab.scripts.hardware_check` 做显式 smoke check：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/setups/real_nv_setup.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config path/to/real_nv_setup.yaml --connect-only
```

默认 `--dry-run` 只加载 YAML、创建 adapter 对象和运行 preflight，不连接硬件。`--connect-only` 只执行 `connect()`、`health_check()`、`snapshot()`、`disconnect()`，不执行实验 procedure。

安全默认值：

- 不打开微波输出。
- 不启动 ASG/AWG 长时间播放。
- 不写 NI AO 电压。
- 配置中如果包含输出动作，必须在实验台上显式加 `--allow-output`。
- 配置中如果包含 AO 写入，必须显式加 `--allow-ao`。

真实实验运行前仍需要检查：ASG 到 NI 的触发线、NI PFI 名称、reference clock、微波负载/衰减器、激光和探测器保护、以及 cleanup 中是否包含 `mw.output_off`、`asg.stop`、`daq.stop`。

## 7. Advanced NI Sync Driver

`drivers/pycontrol/DataAcquisition/sync_driver.py` 提供 `NISyncDAQDriver`，用于一个 measurement point 返回分箱计数、模拟 trace、或 AO/AI trace 矩阵的同步实验。原有 `DataAcquisition/driver.py` 仍是默认 driver，不能被替换或改写。

在 qulab config 中选择新 driver：

```yaml
resources:
  daq:
    adapter: pycontrol_ni
    driver: sync
    device: Dev2
    pycontrol_path: drivers/pycontrol
```

或显式指定 class：

```yaml
driver_class: DataAcquisition.sync_driver.NISyncDAQDriver
```

### 7.1 判断标准：谁决定快时间轴

同步模式的选择首先看“快时间轴”由谁决定：

- ASG 决定 readout window、pulse sequence、APD gate、MW/laser TTL：用 ASG master。
- NI 输出连续 AO waveform，同时 AI 采响应：用 NI master shared-clock。
- AO 是慢变量，每个 AO 点内 AI 采多个高速点：用 NI master step-and-sample。
- AO 是慢变量，但点内还有 ASG pulse/readout：用 mixed mode。
- 想记录 ASG pulse 期间的完整模拟波形：AO setpoint 后，用 ASG trigger 启动 AI finite trace，AI 采完整过程。

注意区分两种时间：

```text
慢时间：Python/executor 设置参数、写 AO 静态值、等待 settle、进入下一点。
快时间：NI/ASG 硬件 sample clock、start trigger、counter gate、ASG pulse sequence。
```

只有快时间由硬件 trigger/sample clock/内部 route 决定时，才是纳秒到微秒级的硬件同步。Python `sleep` 只能用于慢变量 settle，不应用来对齐 pulse 或采样边沿。

### 7.2 ASG Master：NI 在 ASG 控制下采集

ASG master 适合 Rabi、Ramsey、Echo、APD gate readout，以及任何由 ASG 决定 laser/MW/readout gate 的实验。

典型接线：

```text
ASG TTL sample/gate channel -> NI PFI sample clock 或 start trigger
APD TTL output              -> NI PFI counter source
```

执行顺序：

```text
configure NI counter/AI
arm NI，让 NI 等 ASG trigger/clock
arm ASG
start ASG
ASG 输出 TTL
NI 按 ASG TTL 采集或计数
read NI
```

Counter readout 使用：

```python
configure_counter_external_clock(
    counter_channel="ctr0",
    count_source="PFI0",
    sample_clock="PFI1",
    start_trigger="PFI2",
    samples=1000,
    sample_rate=1e6,
)
```

返回格式：

```python
{
    "kind": "counter_bins",
    "data": {
        "counts_mean": 123.4,
        "photon_bins": [120, 130, 118],
        "time_axis_s": [0.0, 1e-6, 2e-6],
    },
    "metadata": {
        "count_source": "/Dev2/PFI0",
        "sample_clock": "/Dev2/PFI1",
        "start_trigger": "/Dev2/PFI2",
        "samples": 1000,
    },
}
```

AI readout 使用：

```python
configure_ai_external_trigger(
    channels=["ai0", "ai1"],
    sample_rate=1e6,
    samples=5000,
    start_trigger="PFI0",
    sample_clock=None,
)
```

如果只给 `start_trigger`，ASG 决定 AI 何时开始，NI 内部 sample clock 决定采样间隔。如果同时给 `start_trigger` 和 `sample_clock`，ASG 或外部 TTL 同时决定开始时刻和每个 sample 的采样节拍，同步更强。

### 7.3 NI Master Shared-Clock：AO Waveform 与 AI 内部硬件同步

shared-clock 适合 NI 输出 AO waveform，同时 AI 采响应，例如 triangle/ramp sweep 和 photodiode trace。

典型内部关系：

```text
AO task start
AI start trigger <- /Dev2/ao/StartTrigger
AI sample clock  <- /Dev2/ao/SampleClock
```

这属于 NI 内部硬件同步。AO 和 AI 使用同一个有效 sample clock，因此 AO rate 和 AI rate 必须一致，AI sample count 也应与 AO waveform 点数对应。

适合：

```text
AO: 输出 1000 点 ramp/triangle waveform
AI: 同步采 1000 点响应
```

不适合：

```text
AO: 每个静态点 1 kHz 更新
AI: 每个 AO 点内采 100 个 100 kHz 点
```

后一种应使用 step-and-sample。

### 7.4 NI Master Step-And-Sample：AO 一个点，AI 采多个点

step-and-sample 适合慢变量扫描，例如磁场线圈、PZT、laser power control、DC bias。

执行顺序：

```text
set AO static value
wait settle_time
AI 用 NI 内部 sample clock 高速采 N 点
保存该 AO 点对应的一段 AI trace
进入下一个 AO 点
```

这里 AI 的 N 个采样点之间由 NI 硬件 sample clock 定时，因此 AI trace 内部是硬件定时。AO 写静态值、等待 settle、启动 AI 之间是慢时间流程控制，一般不是纳秒/微秒级硬件同步；对慢变量扫描通常足够。

返回格式：

```python
{
    "kind": "ao_ai_step_and_sample",
    "data": {
        "ao_points": [[0.0, 0.1, 0.2]],
        "analog_traces": [
            [[...], [...]],  # AO point 0: ai0 trace, ai1 trace
            [[...], [...]],  # AO point 1
            [[...], [...]],  # AO point 2
        ],
        "analog_channels": ["ai0", "ai1"],
        "summary": [
            {"mean": [...], "std": [...]},
            {"mean": [...], "std": [...]},
            {"mean": [...], "std": [...]},
        ],
    },
    "metadata": {
        "sync_mode": "step_and_sample",
        "ai_rate": 100000.0,
        "ai_samples_per_ao_point": 200,
        "settle_time": 0.002,
    },
}
```

shape 约定：

```text
analog_traces[ao_point_index][channel_index][sample_index]
```

### 7.5 Mixed Mode：AO 慢变量，ASG 控制点内采集

mixed mode 适合 NI AO 设置慢变量，但每个点内仍由 ASG 执行 pulse sequence。例如：

```text
AO 设置磁场或 PZT 电压
ASG 执行 laser/MW/readout pulse
NI counter 或 AI 在 ASG gate/trigger 下采集
```

典型流程：

```text
daq.set_ao_static("ao0", voltage)
daq.wait_settle(0.002)
daq.configure_point_readout(kind="counter" or "ai", ...)
daq.arm()
asg.arm()
asg.start()
daq.read()
```

如果 point readout 是 AI，可以有两种常见方式：

```text
start_trigger only:
  ASG 决定 AI 何时开始。
  NI 内部 sample clock 决定之后的采样间隔。

start_trigger + sample_clock:
  ASG 或外部 TTL 同时决定 AI 开始时刻和每个采样点节拍。
```

### 7.6 AO Setpoint + AI 采完整 ASG 过程

如果目标是“AO 输出一个点，AI 维持采集，ASG 给 laser/MW/AWG 等设备发脉冲，AI 记录整段过程数据”，推荐让 AI finite task 等待 ASG start trigger：

```text
daq.set_ao_static(...)
daq.wait_settle(...)
daq.configure_ai_external_trigger(
    channels=["ai0"],
    sample_rate=1e6,
    samples=50000,
    start_trigger="PFI0",
)
daq.arm()
asg.arm()
asg.start()
daq.read()
```

这样 AI trace 的起点由 ASG TTL 边沿决定，trace 内部由 NI sample clock 定时。ASG 在 trace 窗口内输出 laser/MW/AWG trigger，AI 记录完整响应。

如果 AI 先自由开始采集，然后 Python 再 start ASG，二者起点只靠软件顺序接近，不是严格硬件同步。需要可复现实验相位时，应使用共同 start trigger。

### 7.7 多通道 AI 同时采集与返回 shape

多通道 AI 应放在同一个 NI task 中：

```python
channels = ["ai0", "ai1", "ai2"]
sample_rate = 1e6
samples = 1000
```

返回格式：

```python
{
    "kind": "analog_trace",
    "data": {
        "analog_channels": ["ai0", "ai1"],
        "analog_trace": [
            [ai0_sample0, ai0_sample1],
            [ai1_sample0, ai1_sample1],
        ],
        "time_axis_s": [0.0, 1e-6],
    },
    "metadata": {
        "sample_rate": 1000000.0,
        "samples": 1000,
        "start_trigger": "/Dev2/PFI0",
    },
}
```

shape 约定：

```text
analog_trace[channel_index][sample_index]
```

对于常见多路复用 NI AI 卡，多个 AI channel 共享采样资源，总吞吐约为：

```text
total_rate ~= channel_count * per_channel_sample_rate
```

因此增加通道数时必须检查设备最大采样率、terminal configuration、输入量程和抗混叠设置。

### 7.8 Quick Selection Table

| 实验需求 | 推荐模式 | 快时间轴来源 | 硬件同步边界 |
| --- | --- | --- | --- |
| ASG pulse/readout gate 下 APD 分箱计数 | ASG master counter | ASG TTL sample clock/gate | counter bin 由 ASG/TTL 决定 |
| ASG 触发 AI 采一段模拟 trace | ASG master AI | ASG start trigger，可选外部 sample clock | start 由 ASG 决定；sample clock 可由 NI 或外部决定 |
| NI AO waveform 与 AI trace 同步 | NI master shared-clock | NI AO SampleClock/StartTrigger | AO/AI 共用 NI 内部硬件 timing |
| AO 慢变量，每点 AI 高速采多点 | NI master step-and-sample | AI 内部 sample clock | AI trace 内部硬件定时；AO 点间是慢流程 |
| AO 慢变量，每点 ASG pulse readout | mixed | AO 慢流程 + ASG 快 pulse | 点内采集由 ASG/NI trigger/clock 决定 |
| AO setpoint 后 AI 记录完整 ASG pulse 过程 | mixed AI trace | ASG start trigger + NI sample clock | trace 起点硬件同步，trace 内采样硬件定时 |

### Current limitations

- `nidaqmx` is imported only in `connect()`, so config parsing and default tests do not require NI hardware.
- Shared-clock AO/AI validates one effective sample rate. Use step-and-sample for AO slow variables with faster AI traces.
- Counter external-clock mode expects the external sample clock to provide the bin cadence; if no ASG/TTL clock is wired, use the legacy internal-counter method or configure an NI-generated clock explicitly.
- The driver records task intent in `snapshot()`, but it does not infer physical cable correctness. Verify PFI names and trigger polarity at the bench.
- Hardware tests are marked `hardware` and require explicit environment variables; default `python -m pytest` must stay hardware-free.
