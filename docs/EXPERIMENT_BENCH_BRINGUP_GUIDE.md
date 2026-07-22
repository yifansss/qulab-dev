# Qulab Experiment Bench Bring-up Guide

本文档用于把 Qulab 搬到实验台电脑，并按安全顺序测试面板、driver、NI、ASG、PSE detector、微波源和组合扫描模式是否可用。

当前建议目标不是“一上来跑完整真实实验”，而是先完成：

```text
文件迁移 -> Python/硬件驱动环境 -> YAML 参数检查 -> dry-run/preflight
-> connect-only -> read-only detector/NI tests -> AO loopback
-> ASG TTL scope tests -> ASG/NI trigger tests -> mixed mode plan
```

真实 armed-output 和手动 Direct Control 仍建议等 bench commissioning / P8.3 safety layer 完成后再放入日常 GUI 操作。

---

## 1. 需要拷到实验台电脑的文件和文件夹

推荐直接拷贝整个 Qulab 项目目录：

```text
qulab/
```

至少必须包含：

```text
pyproject.toml
README.md
PROJECT_BLUEPRINT.md

src/qulab/
drivers/
  README.md
  pycontrol/
configs/
  experiments/
  setups/
  sequences/
docs/
  BENCH_TEST_CONFIGS.md
  EXPERIMENT_BENCH_BRINGUP_GUIDE.md
tests/
```

重点文件：

```text
drivers/pycontrol/
```

这是项目内 vendored driver tree。现在 Qulab adapter 默认优先使用这个目录，不再依赖实验台电脑上必须存在平行目录 `../pycontrol`。

可以不拷贝或后续自动生成：

```text
runs/
data/
.pytest_cache/
__pycache__/
*.pyc
```

不要只拷贝 `src/`，否则会丢失：

- `drivers/pycontrol` 真实硬件 driver。
- `configs/experiments/bench_*.template.yaml` 测试配置。
- `configs/sequences/operator_sequence.json` ASG 测试 sequence。
- `docs/BENCH_TEST_CONFIGS.md` 和本指南。

---

## 2. 实验台电脑需要安装的环境

### 2.1 操作系统建议

真实硬件测试建议使用 Windows 实验台电脑，因为：

- NI-DAQmx 官方驱动通常在 Windows 环境最完整。
- 国仪 ASG SDK 可能包含 Windows DLL。
- Rigol AWG / VISA / 串口环境通常也在 Windows 上更容易配置。

开发 dry-run 可以在 macOS/Linux 上做，但真实 hardware connect/output 推荐在实验台 Windows 环境。

### 2.2 Python

推荐：

```text
Python 3.10 - 3.12
```

先确认：

```bash
python --version
python -m pip --version
```

建议创建独立环境，例如 conda：

```bash
conda create -n qulab-bench python=3.12
conda activate qulab-bench
```

或 venv：

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2.3 Qulab 基础依赖

在项目根目录运行：

```bash
python -m pip install -e .
python -m pip install pytest
```

Qulab 核心依赖很少：

```text
numpy
pyyaml
```

### 2.4 pycontrol / 硬件 Python 依赖

项目内已有 driver 代码：

```text
drivers/pycontrol/
```

为了安装硬件依赖，可以运行：

```bash
python -m pip install -e drivers/pycontrol
```

这会安装 pycontrol 声明的常见依赖，包括：

```text
numpy
matplotlib
pyyaml
pyserial
pyvisa
pyvisa-py
nidaqmx
hightime
nitypes
```

如果实验台电脑不能联网，可以提前下载 wheel 或用实验室已有环境安装这些包。

### 2.5 NI 必需软件

仅安装 Python `nidaqmx` 包不够。实验台电脑还需要 NI 官方驱动：

```text
NI-DAQmx Runtime / Driver
NI MAX
```

安装后用 NI MAX 确认设备名，例如：

```text
Dev2
```

如果 NI MAX 里不是 `Dev2`，必须修改所有 config 里的：

```yaml
device: Dev2
```

### 2.6 ASG 必需 SDK

国仪 ASG driver 可能需要厂商 SDK 文件，例如：

```text
asglib.py
ASG24100_SDK_x64.dll
```

按照 pycontrol driver 要求放入：

```text
drivers/pycontrol/PulseGenerator/
drivers/pycontrol/PulseGenerator/x64/
```

具体位置以当前 `drivers/pycontrol/PulseGenerator/driver.py` 的 import/ctypes 查找逻辑为准。

### 2.7 LMX 微波源和串口

需要：

```text
pyserial
正确 COM 口
正确 baudrate，当前模板默认 921600
```

Windows 设备管理器里确认 COM 口，例如：

```text
COM5
```

### 2.8 AWG / VISA

如果要测 Rigol AWG，需要：

```text
NI-VISA 或可用 VISA runtime
pyvisa
```

并确认 VISA 地址，例如：

```text
TCPIP0::192.168.31.193::inst0::INSTR
```

### 2.9 GUI 可选依赖

如果要打开 PyQt/PySide Operator Console：

```bash
python -m pip install PySide6
```

或：

```bash
python -m pip install PyQt6
```

高级 viewer 可选：

```bash
python -m pip install matplotlib pyqtgraph zarr
```

注意：GUI 能打开不等于可以安全执行真实 hardware output。真实手动控制还需要 bench commissioning / Direct Control safety layer。

---

## 3. 先在实验台电脑做软件自检

在 Qulab 项目根目录：

```bash
python -m pytest
```

期望：

```text
大部分测试 passed
硬件测试 skipped
```

如果只想快速检查关键路径：

```bash
python -m pytest tests/unit/test_pycontrol_adapter_import.py
python -m pytest tests/unit/test_pycontrol_ni_driver_selection.py
python -m pytest tests/integration/test_bench_templates_parse.py
```

检查 Qulab 能找到项目内 driver：

```bash
python -c "from qulab.instruments.adapters.pycontrol import _resolve_pycontrol_path; print(_resolve_pycontrol_path({}))"
```

应输出类似：

```text
...\qulab\drivers\pycontrol
```

检查 NI sync driver 可被 import，但不连接硬件：

```bash
python -c "import sys; sys.path.insert(0, 'drivers/pycontrol'); from DataAcquisition.sync_driver import NISyncDAQDriver; print(NISyncDAQDriver.__name__)"
```

---

## 4. 哪些参数必须按实验台实际连接修改

不要直接改原始模板。建议复制一份：

```bash
copy configs\experiments\bench_00_inventory_connect.template.yaml configs\experiments\local_bench_00_inventory_connect.yaml
```

macOS/Linux:

```bash
cp configs/experiments/bench_00_inventory_connect.template.yaml configs/experiments/local_bench_00_inventory_connect.yaml
```

### 4.1 通用 resource 参数

所有真实硬件 config 中重点检查：

```yaml
pycontrol_path: drivers/pycontrol
simulation: false
```

通常保留：

```yaml
pycontrol_path: drivers/pycontrol
```

如果要临时使用另一份 driver，可改成绝对路径，或设置：

```bash
set QULAB_PYCONTROL_PATH=D:\path\to\pycontrol
```

### 4.2 NI DAQ 参数

检查：

```yaml
device: Dev2
```

按 NI MAX 修改为实际设备名。

PSE detector 模拟输入当前默认：

```yaml
channels: [ai1]
terminal_config: DIFF
```

如果 PSE 输出接到别的通道，修改：

```yaml
channels: [ai0]
```

或：

```yaml
channels: [ai2]
```

如果接线不是差分，需要按实际情况改：

```yaml
terminal_config: RSE
```

或：

```yaml
terminal_config: NRSE
```

常用采样参数：

```yaml
sample_rate: 100000
samples: 2000
```

如果 trace 太短/太长，调整：

```yaml
sample_rate
samples
timeout_s
```

### 4.3 PSE detector 参数和接线

当前 PSE 测试假设：

```text
PSE analog output -> NI Dev2/ai1
```

需要确认：

- PSE 输出是模拟电压还是 TTL。
- PSE 模式、增益、带宽、偏置是否正确。
- 电压范围是否在 NI AI 输入范围内。
- 接地/参考是否符合 terminal configuration。

第一步一定用示波器看 PSE analog output，再接入 NI AI1。

### 4.4 NI AO 参数

AO loopback 默认：

```yaml
channel: ao0
values: {start: -0.1, stop: 0.1, points: 5}
```

如果 AO0 接到真实器件，必须先确认电压范围安全。不要一开始就接 PZT、线圈、激光功率控制等敏感输入。

建议先做：

```text
NI AO0 -> NI AI1 loopback
```

或者：

```text
NI AO0 -> 万用表/示波器
```

### 4.5 ASG 参数和接线

默认 sequence：

```yaml
sequence_file: configs/sequences/operator_sequence.json
```

ASG address：

```yaml
address: auto
```

如果自动搜索不稳定，改为具体设备地址，具体格式以 `drivers/pycontrol/PulseGenerator/driver.py` 为准。

当前 PSE AI trace bench 的实际触发连接：

```text
ASG ch1 -> NI PFI1 作为 AI start_trigger
```

对应 AI YAML：

```yaml
start_trigger: PFI1
```

Counter bench 使用独立的 sample-clock/count-source 接线，不应直接套用这条 AI start-trigger 连接。

如果实际接线不同，要同步修改：

```yaml
sync.triggers
daq.configure_ai_external_trigger.args.start_trigger
daq.configure_counter_external_clock.args.sample_clock
daq.configure_counter_external_clock.args.start_trigger
```

示波器先确认：

- TTL 电平。
- 脉宽。
- 极性。
- 哪个 ASG 物理通道对应 YAML 里的 trigger source。

### 4.6 微波源 LMX 参数

检查：

```yaml
port: COM5
baudrate: 921600
output_type: RFH
```

按实际串口修改：

```yaml
port: COM3
```

低风险配置测试不打开 RF：

```yaml
bench_08_mw_lmx_config_no_rf.template.yaml
```

它只调用：

```text
set_frequency
set_power
output_off
```

不调用：

```text
output_on
```

### 4.7 AWG 参数

检查：

```yaml
address: TCPIP0::192.168.31.193::inst0::INSTR
```

如果暂时不用 AWG，可以先只测不包含 AWG 的 bench configs。

---

## 5. 测试配置文件总览

测试配置位于：

```text
configs/experiments/bench_*.template.yaml
```

推荐顺序：

1. `bench_00_inventory_connect.template.yaml`
   - 资源 inventory 和 connect-only。
   - 无输出，无 AO。

2. `bench_01_pse_ai1_dark_trace.template.yaml`
   - PSE analog output -> NI AI1。
   - 只读 AI trace。

3. `bench_02_ni_ao0_to_ai1_loopback.template.yaml`
   - NI AO0 -> NI AI1 loopback。
   - 需要 `--allow-ao`。

4. `bench_03_asg_ttl_scope_smoke.template.yaml`
   - ASG TTL -> 示波器。
   - 需要 `--allow-output`。

5. `bench_04_asg_to_ni_counter_ttl.template.yaml`
   - ASG TTL -> NI PFI counter。
   - 需要 `--allow-output`。

6. `bench_05_pse_ai1_asg_triggered_trace.template.yaml`
   - ASG trigger -> NI AI start。
   - PSE analog -> AI1。
   - 需要 `--allow-output`。

7. `bench_06_pse_ai1_manual_slow_scan.template.yaml`
   - 手动条件扫描，Qulab 只读 AI1。
   - 无输出，无 AO。

8. `bench_07_mixed_ao0_slow_asg_pse_ai1.template.yaml`
   - NI AO 慢变量 + ASG 快触发 + PSE AI1 trace。
   - 需要 `--allow-output --allow-ao`。

9. `bench_08_mw_lmx_config_no_rf.template.yaml`
   - MW frequency/power configure-only。
   - 不打开 RF。

10. `bench_09_low_power_odmr_pse_ai1_plan.template.yaml`
    - MW frequency scan + ASG-triggered PSE AI1 trace。
    - 不调用 `mw.output_on`。
    - ASG timing 需要 `--allow-output`。

---

## 6. 具体测试顺序和命令

下面命令都在 Qulab 项目根目录执行。

### Step 0: 软件和 YAML 自检

```bash
python -m pytest tests/integration/test_bench_templates_parse.py
```

期望：

```text
passed
```

### Step 1: inventory dry-run

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --dry-run
```

期望：

- preflight ok。
- resources 列出 `mw_drive`、`asg`、`daq`、`awg`。
- connected 全部是 false。
- 没有输出动作执行。

如果这里失败，先修 YAML，不要连接硬件。

### Step 2: connect-only

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --connect-only
```

期望：

- 每个 resource connect status ok。
- health_check 有返回。
- snapshot 有返回。
- 最后 disconnect ok。

如果某个仪器失败：

- 检查 `port`、`device`、`address`、SDK、NI MAX、VISA、串口权限。
- 先只保留一个 resource 测试，避免多设备错误混在一起。

### Step 3: PSE detector AI1 dark trace dry-run

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_01_pse_ai1_dark_trace.template.yaml --dry-run
```

这一步只检查配置安全。真正读取 AI trace 需要后续 bench runner 或你手动用 driver/API 执行。接线检查：

```text
PSE analog output -> NI AI1
PSE reference/ground -> NI reference/ground
示波器 CH1 -> PSE analog output
```

示波器期望：

- dark baseline 稳定。
- 不饱和。
- 噪声幅度合理。
- 手动改变光输入时电压变化方向符合预期。

### Step 4: NI AO0 -> AI1 loopback

先接线：

```text
NI AO0 -> NI AI1
NI AO GND/reference -> AI reference
示波器 CH1 -> AO0
示波器 CH2 -> AI1
```

先 dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_02_ni_ao0_to_ai1_loopback.template.yaml --dry-run --allow-ao
```

这个配置会写 AO，所以真正执行前必须确认：

- AO0 没接到敏感设备。
- 电压范围 `-0.1 V` 到 `0.1 V` 安全。
- AI1 量程和接法正确。

期望：

- AO0 慢速阶跃。
- AI1 trace 均值跟随 AO0。
- viewer/storage 能看到每个 `ao_voltage` 的 trace。

### Step 5: ASG TTL 示波器测试

先只接示波器，不接 NI、激光、微波开关：

```text
ASG selected channel -> oscilloscope CH1
ASG trigger/readout channel -> oscilloscope CH2
```

dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_03_asg_ttl_scope_smoke.template.yaml --dry-run --allow-output
```

真正输出前确认：

- ASG 输出只接示波器或安全 dummy input。
- TTL 电平不会损坏后级。
- 通道对应关系已确认。

示波器期望：

- 看到 `configs/sequences/operator_sequence.json` 对应的脉冲。
- 通道、脉宽、延迟、极性符合预期。

### Step 6: ASG -> NI counter TTL routing

接线：

```text
Detector/APD TTL or test TTL source -> NI PFI0 count_source
ASG ch5 -> NI PFI1 sample_clock
ASG ch6 -> NI PFI2 start_trigger
```

示波器：

```text
CH1 -> ASG ch5
CH2 -> ASG ch6
CH3 -> detector/test TTL
```

dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_04_asg_to_ni_counter_ttl.template.yaml --dry-run --allow-output
```

期望：

- ASG sample clock/start trigger 到达 NI PFI。
- counter bins 只在 sample clock 边沿存在时更新。
- 如果 count source 没信号，计数应接近 0 或稳定背景。

### Step 7: PSE AI1 ASG-triggered trace

接线：

```text
PSE analog output -> NI AI1
ASG ch1 -> NI PFI1 AI start_trigger
示波器 CH1 -> ASG relevant gate/pulse
示波器 CH2 -> ASG ch1 trigger
示波器 CH3 -> PSE analog output
```

dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml --dry-run --allow-output
```

期望：

- AI trace 起点与 ASG trigger 对齐。
- PSE response 出现在预期 delay。
- 如果没有光输入，应看到 triggered dark baseline。

### Step 8: 手动慢变量 scan

这个配置不驱动输出，适合测试 storage/viewer：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_06_pse_ai1_manual_slow_scan.template.yaml --dry-run
```

执行思路：

```text
manual_condition = dark / dim / bright
每个条件由操作者手动改变
Qulab 记录 AI1 trace
```

期望：

- viewer 能按 manual_condition 查看 trace。
- trace 幅度随手动条件变化。

### Step 9: mixed mode

只有在 Step 4 和 Step 7 都确认后再做。

接线：

```text
NI AO0 -> safe slow-control input 或 loopback target
PSE analog output -> NI AI1
ASG ch1 -> NI PFI1 AI start_trigger
示波器 CH1 -> AO0
示波器 CH2 -> ASG ch1
示波器 CH3 -> PSE analog output
```

dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_07_mixed_ao0_slow_asg_pse_ai1.template.yaml --dry-run --allow-output --allow-ao
```

期望：

- AO0 是慢阶跃。
- 每个 AO 点 settle 后 ASG 触发一次 AI trace。
- 数据以 `ao_voltage x time_s` 形式可浏览。

### Step 10: MW configure-only

这一步不打开 RF：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_08_mw_lmx_config_no_rf.template.yaml --dry-run
```

如果后续通过真实执行路径运行，期望：

- LMX 接受频率/功率命令。
- RF output 保持 off。

### Step 11: low-power ODMR plan

只有在以下都确认后再考虑：

- PSE AI1 ok。
- ASG TTL scope ok。
- ASG-triggered AI trace ok。
- MW configure-only ok。
- 微波衰减、负载、样品、激光、探测器保护确认。

dry-run safety：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_09_low_power_odmr_pse_ai1_plan.template.yaml --dry-run --allow-output
```

注意：

- 这个 config 不调用 `mw_drive.output_on`。
- RF 真正打开应等 Direct Control / bench safety layer，或非常明确的人工授权流程。

---

## 7. GUI 使用建议

当前 GUI 可用于：

- 打开 dry-run configs。
- 查看 workflow tree。
- 使用 Operator Parameters 快速修改参数。
- 查看 ASG sequence preview/hash。
- dry-run Start。
- 查看 run data / viewer。

当前不建议用 GUI 直接执行真实硬件 output，因为：

- `Direct Control` 目前仍是 P8.3 pending/placeholder。
- 可靠 stop/pause/resume 还未完成。
- 完整 bench commissioning runner 还未完成。

推荐 GUI 使用方式：

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

在 GUI 里先检查：

- config 是否能加载。
- Operator Parameters 是否显示正确。
- ASG sequence path/hash 是否正确。
- workflow tree 是否符合预期。

真实硬件连接/输出阶段先用 CLI `hardware_check`，不要直接用 GUI Start。

---

## 8. 常见问题排查

### 8.1 找不到 pycontrol driver

检查：

```bash
python -c "from qulab.instruments.adapters.pycontrol import _resolve_pycontrol_path; print(_resolve_pycontrol_path({}))"
```

应指向：

```text
drivers/pycontrol
```

如果不是，检查是否设置了错误的：

```text
QULAB_PYCONTROL_PATH
```

### 8.2 nidaqmx import 失败

需要同时安装：

- NI-DAQmx 官方驱动。
- Python 包 `nidaqmx`。

确认：

```bash
python -c "import nidaqmx; print(nidaqmx.__name__)"
```

### 8.3 NI device name 错误

在 NI MAX 里确认设备名，把 YAML 里的：

```yaml
device: Dev2
```

改成实际名字。

### 8.4 ASG SDK 缺失

检查厂商 SDK 文件是否在 pycontrol driver 期望位置，例如：

```text
drivers/pycontrol/PulseGenerator/asglib.py
drivers/pycontrol/PulseGenerator/x64/ASG24100_SDK_x64.dll
```

### 8.5 LMX 串口错误

检查 Windows 设备管理器，把：

```yaml
port: COM5
```

改成实际端口。

### 8.6 pyvisa / AWG 连接失败

检查：

- VISA runtime。
- 仪器 IP。
- 防火墙。
- `TCPIP0::...::INSTR` 地址。

### 8.7 safety check 阻止运行

如果 config 包含：

```text
asg.start
mw.output_on
awg.play
```

需要：

```bash
--allow-output
```

如果 config 包含：

```text
daq.set_voltage
daq.set_ao_static
daq.set_waveform
```

需要：

```bash
--allow-ao
```

不要为了通过检查随便加 flag。加 flag 之前必须确认接线和负载安全。

---

## 9. 当前仍建议补齐的前序能力

在把 Qulab 当作日常真实硬件面板前，建议继续实现：

1. Bench commissioning runner
   - `dry-run`
   - `connect-only`
   - `identify/read-only`
   - `configure-only`
   - `dark-count/readout-only`
   - `armed-output`

2. P8.3 Direct Control Submode
   - resource/action list。
   - safety class。
   - output/AO/unknown 默认禁用。
   - 显式授权。
   - 所有动作写 bench log。

3. 可靠 stop/pause/resume 和 cleanup
   - ASG stop。
   - AWG stop。
   - MW output_off。
   - NI task close。
   - AO 回零或安全值。

4. 真实硬件 smoke tests
   - 只在实验台显式环境变量和 config 存在时运行。
   - 默认 pytest 仍保持硬件 free。

---

## 10. 最短安全路线

## 9.1 Generated Sequence Family Ladder

在Bench05通过后依次使用Bench10–12：先离线Prepare/检查manifest和first/middle/last
preview，再把ASG TTL只接示波器，然后验证ASG ch6到NI PFI，最后才允许低功率MW。
每一步都必须显式授权输出、确认channel/PFI/电平并保留cleanup。family metadata和静态
preflight不会自动开启输出，也不能证明物理接线。当前这些模板均未做真实硬件验证。

Legacy ASG JSON可先运行：

```bash
PYTHONPATH=src python -m qulab.scripts.sequence_plan_from_template existing.json \
  --resource asg --plan-id imported --output imported_sequence_plan.yaml
```

工具不会猜测MW/laser/readout物理角色；导入后必须显式绑定target。

如果只想今天快速判断“面板和 driver 是否具备上台基础”，按这个最短路线：

```bash
python -m pytest tests/unit/test_pycontrol_adapter_import.py
python -m pytest tests/unit/test_pycontrol_ni_driver_selection.py
python -m pytest tests/integration/test_bench_templates_parse.py
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --connect-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_01_pse_ai1_dark_trace.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_03_asg_ttl_scope_smoke.template.yaml --dry-run --allow-output
```

通过后，再开始接示波器和真实信号线。
