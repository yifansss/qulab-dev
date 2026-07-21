# Prompt 006: Bench Commissioning + Hardware Workflow Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在已有 pycontrol adapters、hardware_check CLI、GUI Operator Console 的基础上，推进到“实验台实测前最后一公里”：建立分阶段 bench commissioning 工作流、GUI 硬件检查面板、sequence template 参数展开、read-only/dark-count 安全测试、以及需要显式授权的低风险 hardware run planner。这个 worker 可以一次性做较多内容，但默认测试和默认命令仍然绝不能要求真实硬件或打开输出。

---

## /goal

在当前 `qulab` 项目中实现实验台联调准备版：新增 bench commissioning 工作流，把硬件实测拆成 `dry-run -> connect-only -> identify/read-only -> configure-only -> dark-count/readout-only -> armed-output` 多个安全阶段；增强 hardware_check CLI 和 GUI Operator Console，使操作者能在 GUI 中选择硬件 config、查看 checklist、执行 dry-run/connect-only/read-only 级检查；新增 ASG sequence template 参数展开能力，使 YAML 中的 scan 参数能生成/预览单点脉冲代码；新增低风险硬件 smoke tests 和文档。默认 `python -m pytest` 必须无硬件通过；任何真实连接和输出都必须由用户显式命令或 CLI flag 授权。

成功标准：

1. 阅读并遵守项目蓝图、hardware sync、adapter、GUI、QA 文档。
2. 不修改 `../pycontrol`。
3. 默认 import、默认 pytest、GUI 默认打开都不连接硬件。
4. 新增 `bench` 或 `commissioning` 层，描述和执行分阶段硬件检查。
5. 增强 `hardware_check` CLI，支持：
   - `--dry-run`
   - `--connect-only`
   - `--identify`
   - `--configure-only`
   - `--read-only`
   - `--dark-count`
   - `--plan-run`
   - `--allow-output`
   - `--allow-ao`
6. `--identify` 只做连接、health_check、snapshot、可选 IDN/status 查询，不输出微波、不启动 ASG/AWG、不写 AO。
7. `--configure-only` 允许设置低风险静态配置，例如 DAQ counter config、MW frequency/power value 写入但不 output_on、ASG load/compile sequence 但不 start。
8. `--read-only` 允许读取状态或已有输入，不产生输出。
9. `--dark-count` 只能在无激光/无 ASG 输出的安全假设下读 NI/APD 背景计数；如果实现不确定，必须保持为 plan/placeholder 并要求明确 user flag。
10. `--plan-run` 生成即将执行的硬件动作清单，但不执行。
11. 新增 bench checklist 数据结构和文档，列出实验台真实运行前必须确认的事项。
12. GUI Operator Console 增加 Bench/Hardware 面板：
    - 加载 hardware config。
    - 显示 resources。
    - 显示 sync plan。
    - 显示 safety checklist。
    - 按钮：Dry Run、Connect Only、Identify、Plan Run。
    - 默认禁用任何 output/ao 操作。
13. 新增 sequence template 模块：
    - 支持简单文本模板或 Python format-style placeholder。
    - 能把 `${tau_s}` / `{tau_s}` 这类参数展开成 ASG code preview。
    - 支持 sequence hash/snapshot。
    - 不要求完整通用时序编译器。
14. 新增示例：
    - `configs/sequences/asg_odmr_readout.template.seq`
    - `configs/sequences/asg_rabi_readout.template.seq`
    - `configs/experiments/hardware_rabi.template.yaml`
    - `configs/experiments/bench_dark_count.template.yaml`
15. 新增 tests：
    - 默认无硬件测试覆盖 run plan、安全门、sequence template 展开、GUI bench controller。
    - hardware tests 标记 `@pytest.mark.hardware`，无 `QULAB_HARDWARE_CONFIG` 时 skip。
16. 更新文档，清楚说明到什么程度可以实测，以及每个阶段需要哪些人工确认。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/HARDWARE_SYNC.md`
3. `docs/ADAPTER_REQUIREMENTS.md`
4. `docs/OPERATOR_UI.md`
5. `docs/CONFIG_SCHEMA.md`
6. `docs/DATA_MODEL.md`
7. `workers/adapter_worker.md`
8. `workers/sync_worker.md`
9. `workers/gui_worker.md`
10. `workers/qa_worker.md`

同时查看当前实现：

```text
src/qulab/scripts/hardware_check.py
src/qulab/instruments/adapters/pycontrol.py
src/qulab/gui/controller.py
src/qulab/gui/operator_app.py
src/qulab/config/
src/qulab/sync/
configs/setups/real_nv_setup.template.yaml
configs/experiments/hardware_odmr.template.yaml
configs/experiments/dry_run_two_mw_scan.yaml
```

重点确认：

- pycontrol adapters 已延迟导入。
- hardware_check 目前已有 `--dry-run` 和 `--connect-only`。
- GUI 当前是 Tkinter MVP，已有 controller/model/test。
- core executor 当前同步执行，不支持可靠 stop/pause。
- 所有真实硬件动作必须通过显式 CLI/GUI intent 执行。

---

## 当前项目目录

项目根目录：

```text
/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab
```

建议新增代码：

```text
src/qulab/bench/
src/qulab/sequences/
src/qulab/scripts/hardware_check.py
src/qulab/gui/bench_controller.py
src/qulab/gui/operator_app.py
```

建议新增测试：

```text
tests/unit/test_bench_plan.py
tests/unit/test_bench_safety.py
tests/unit/test_sequence_templates.py
tests/unit/test_gui_bench_controller.py
tests/integration/test_hardware_check_modes.py
tests/integration/test_hardware_run_plan_templates.py
tests/hardware/test_bench_connect_identify.py
```

建议新增示例：

```text
configs/sequences/asg_odmr_readout.template.seq
configs/sequences/asg_rabi_readout.template.seq
configs/experiments/hardware_rabi.template.yaml
configs/experiments/bench_dark_count.template.yaml
configs/checklists/nv_bench_checklist.yaml
```

---

## 具体实现要求

### 1. Bench Workflow Model

新增 `src/qulab/bench/`。

推荐对象：

```python
@dataclass
class BenchAction:
    resource: str
    method: str
    args: dict[str, Any]
    safety_class: str
    description: str

@dataclass
class BenchPlan:
    mode: str
    config_path: str | None
    actions: list[BenchAction]
    warnings: list[str]
    errors: list[str]
    requires_allow_output: bool = False
    requires_allow_ao: bool = False

@dataclass
class BenchResult:
    mode: str
    ok: bool
    resources: dict[str, Any]
    snapshots: dict[str, Any]
    messages: list[str]
```

Safety classes：

```text
read_only
connect
configure_no_output
output
analog_output
unknown
```

原则：

- plan 和 execute 分离。
- plan-run 永远不执行硬件。
- execute 前必须检查 safety flags。

### 2. Hardware Action Classifier

从 procedure/config 中提取硬件动作，并分类：

```python
class HardwareActionClassifier:
    def classify_call(resource_name: str, method_name: str) -> str: ...
```

默认分类：

read_only：

- `snapshot`
- `health_check`
- `status`
- `read_counts`
- `read_counts_binned`
- `read_analog`

configure_no_output：

- `set_frequency`
- `set_power`
- `load_sequence`
- `set_sequence_param`
- `compile_sequence`
- `configure_counter`
- `configure_ai`
- `configure_trigger`
- `configure_trigger_input`
- `configure_trigger_output`
- `arm`，注意：对某些设备 arm 可能接近运行，MVP 可以 warning。

output：

- `output_on`
- `start`
- `play`

analog_output：

- `set_voltage`
- `set_waveform`

unknown：

- 其他。

unknown 默认阻止真实执行，除非显式 `--allow-unknown`，MVP 可不实现 allow-unknown。

### 3. Enhanced hardware_check CLI

扩展：

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --plan-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --connect-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --identify
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --configure-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --read-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <config> --dark-count
```

Mode semantics：

`--dry-run`：

- parse + preflight + print resources。
- no connect。

`--plan-run`：

- parse procedure。
- classify actions。
- print action table。
- no connect。

`--connect-only`：

- connect + health_check + snapshot + disconnect。
- no procedure actions。

`--identify`：

- connect。
- try `identify()` / `idn()` / status-like method if adapter supports it。
- health_check + snapshot。
- disconnect。
- no output。

`--configure-only`：

- connect。
- execute only configure_no_output actions.
- reject output and analog_output actions unless explicit flags are present, but even with flags MVP should prefer to refuse output in configure-only。
- disconnect。

`--read-only`：

- connect。
- execute read_only actions only.
- no output。

`--dark-count`：

- connect DAQ only if possible。
- configure counter/read counts without ASG/MW output。
- save result via RunStore if implemented。
- if current adapter cannot safely do this, print clear “not implemented safely” and exit nonzero or skip。

### 4. GUI Bench Panel

Extend Tkinter GUI without requiring new dependencies.

Can be a new tab/section or side panel.

Must show:

- hardware config path。
- mode buttons:
  - Dry Run
  - Plan Run
  - Connect Only
  - Identify
- resource table:
  - name
  - adapter
  - capabilities
  - simulation/hardware
  - connected
- safety checklist:
  - laser path safe
  - microwave output disabled initially
  - ASG outputs disabled initially
  - NI AO disabled
  - APD/DAQ connected
  - trigger cable ASG -> NI
  - emergency stop known
- action plan table。
- output log。

Important:

- GUI must not execute output actions in this worker。
- If user clicks an unavailable dangerous mode, show message/log explaining CLI flag/manual step required。
- Tests should cover controller logic, not open real GUI window。

### 5. Checklist

Add YAML checklist:

```yaml
name: nv_bench_checklist
items:
  - id: mw_output_disabled
    label: Microwave output disabled before connect
    required: true
  - id: asg_output_disabled
    label: ASG output disabled before run
    required: true
  - id: ni_ao_disabled
    label: NI AO disabled or safe voltage confirmed
    required: true
  - id: trigger_cable_checked
    label: ASG trigger/gate connected to NI PFI
    required: true
```

MVP can load/display/check this in GUI model and CLI plan output.

### 6. Sequence Template Module

新增 `src/qulab/sequences/`。

Goal：不是做通用时序编译器，而是支持把 YAML scan 参数传入已有 ASG code template。

推荐 API：

```python
class SequenceTemplate:
    @classmethod
    def from_file(cls, path: Path | str) -> "SequenceTemplate": ...
    def render(self, params: dict[str, Any]) -> str: ...
    def hash(self, rendered: str | None = None) -> str: ...
    def variables(self) -> set[str]: ...
```

支持 placeholder：

```text
{tau_ns}
{laser_width_ns}
{readout_width_ns}
```

可选支持 `${tau_ns}`，但不要执行 Python 表达式。

Add example ASG templates:

```text
configs/sequences/asg_odmr_readout.template.seq
configs/sequences/asg_rabi_readout.template.seq
```

Example content can be simple ASG-like placeholder code, not necessarily final vendor syntax:

```text
w1 = Seq_Gen(L,{laser_delay_ns},H,{laser_width_ns},L,{readout_delay_ns})
s1 = ASG_SEQ([w1(1)])
ASG_OUT[1] = s1
w5 = Seq_Gen(L,{gate_delay_ns},H,{gate_width_ns},L,{tail_ns})
s5 = ASG_SEQ([w5(1)])
ASG_OUT[5] = s5
```

### 7. Config Integration for Sequence Templates

Support YAML pattern:

```yaml
setup:
  - call: asg.load_sequence
    args:
      template: configs/sequences/asg_rabi_readout.template.seq
      params:
        laser_delay_ns: 100
        laser_width_ns: 200
        tau_ns: 100
        gate_delay_ns: 400
        gate_width_ns: 200
        tail_ns: 400
```

If current pycontrol ASG adapter expects `sequence` or `code`, worker can implement a preprocessor in config/bench layer that renders template to `code` before calling `asg.load_sequence`.

Do not break existing `asg.load_sequence(sequence=...)`.

### 8. Hardware Rabi Template

Add `hardware_rabi.template.yaml`:

- mw_drive pycontrol_lmx。
- asg pycontrol_asg。
- daq pycontrol_ni。
- scan `tau_ns` or `tau_s`。
- use sequence template.
- no `output_on` in default setup.
- no ASG `start` unless documentation makes clear it requires `--allow-output` for actual run。

It should parse/preflight in default tests without hardware.

### 9. Tests

Default tests:

- `python -m pytest` must pass with no hardware。
- no test should connect hardware unless marked hardware and env-gated。

Required coverage:

- action classifier classifies output/AO/read/config correctly。
- plan-run for hardware_odmr.template produces output-required actions and blocks execution by default。
- connect-only mode planning contains only connect actions。
- sequence template renders params and hash is stable。
- missing sequence param raises clear error。
- multi-frequency config remains parseable。
- GUI bench controller loads checklist and plan。
- hardware_check `--dry-run` and `--plan-run` work on templates。

Hardware tests:

- mark with `@pytest.mark.hardware`。
- require `QULAB_HARDWARE_CONFIG`。
- default skip。
- only run connect/identify unless user sets `QULAB_ALLOW_OUTPUT=1`。

### 10. Documentation

Update:

```text
README.md
docs/HARDWARE_SYNC.md
docs/ADAPTER_REQUIREMENTS.md
docs/OPERATOR_UI.md
docs/IMPLEMENTATION_ORDER.md
workers/sync_worker.md
workers/gui_worker.md
```

Must include staged bench workflow:

```text
Stage 0: YAML dry-run
Stage 1: connect-only
Stage 2: identify/read-only
Stage 3: configure-only
Stage 4: dark-count/readout-only
Stage 5: armed output run, requires explicit operator authorization
```

Clearly state what can be done now and what still needs manual lab confirmation.

---

## 严格禁止

- 不要修改 `../pycontrol`。
- 不要在 import 阶段连接硬件。
- 不要在 default pytest 中连接硬件。
- 不要默认打开 microwave output。
- 不要默认 start ASG/AWG。
- 不要默认写 NI AO。
- 不要实现假 pause/resume。
- 不要声称 full autonomous real experiment is safe until staged checks exist and user has provided real config。
- 不要用 eval/render arbitrary Python in sequence templates。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/hardware_odmr.template.yaml --plan-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/hardware_rabi.template.yaml --dry-run
PYTHONPATH=src python -c "from qulab.sequences import SequenceTemplate; print(SequenceTemplate.__name__)"
PYTHONPATH=src python -c "from qulab.bench import BenchPlan; print(BenchPlan.__name__)"
```

Do not run real `--connect-only` unless the user explicitly says the bench is ready and provides the real hardware config.

If user later authorizes hardware connection:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <real-config.yaml> --connect-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config <real-config.yaml> --identify
```

Still do not run output modes unless explicitly authorized.

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 新增了哪些 bench/sequence/GUI/CLI 能力。
3. 现在最多能安全实测到哪个阶段。
4. 哪些命令已经验证，结果是什么。
5. 是否保持默认测试无硬件依赖。
6. 哪些真实硬件动作仍然需要用户明确授权。
7. 还没做什么，明确留给后续 worker。

