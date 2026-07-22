# Prompt 004-followup P8.2: Operator Parameters Submode Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在现有 PyQt/PySide Operator Console 基础上，完成 P8.2：新增 `Operator Parameters` submode，让实验现场调参不再依赖逐层展开 workflow tree。`Builder Workflow` 继续保留现有 workflow tree + inspector；本 worker 新增现场快速参数表单，并让表单与 workflow model / YAML 保持同步。

本 worker 不做真实硬件控制，不连接 ASG/NI/MW/AWG，不实现 Direct Control。Direct Control 是后续 P8.3 独立 worker prompt。

---

## /goal

在同一主窗口中增加 submode 切换：

```text
[ Operator Parameters ] [ Builder Workflow ] [ Direct Control ]
```

本 worker 只实现前两者：

- `Operator Parameters`：新增，集中表单快速调参。
- `Builder Workflow`：保留现有 workflow tree + inspector。
- `Direct Control`：只放 disabled/pending placeholder 或不实现，并明确留给 P8.3 worker。

成功标准：

1. 阅读并遵守项目蓝图、GUI、config 和 QA 规范。
2. 不连接真实硬件，不启动 ASG/NI/MW/AWG。
3. 不做 Direct Control，不实现危险动作按钮。
4. 新增 operator parameter model，能从当前 config/workflow 自动发现常用参数。
5. 支持顶层 `operator_parameters` 显式声明。
6. PyQt Operator Console 中能一键切换 `Operator Parameters` 与 `Builder Workflow`。
7. `Operator Parameters` 表单至少支持 scan values、average count、常见 call args、resource `sequence_file`、storage backend。
8. 修改表单后同步更新 workflow model 和 raw YAML config。
9. 保存后的 YAML 能被 `parse_experiment_config` 解析，并能 dry-run。
10. 修改 scan points / average count / call arg 后，dry-run 行为能反映新值。
11. 默认 `python -m pytest` 在无 Qt、无硬件环境中通过；Qt widget tests 必须 skip cleanly。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/OPERATOR_UI.md`
4. `docs/IMPLEMENTATION_ORDER.md`
5. `docs/CONFIG_SCHEMA.md`
6. `workers/gui_worker.md`
7. `workers/qa_worker.md`

重点阅读：

```text
docs/OPERATOR_UI.md
  - 3.3 同一界面内的 Submode 切换
  - 3.4 Operator Parameters Submode
  - 当前 PyQt/PySide Operator Console 限制

docs/IMPLEMENTATION_ORDER.md
  - P8.2 Operator Parameters Submode

docs/CONFIG_SCHEMA.md
  - operator_parameters
  - ASG sequence_file / sequence_params
```

同时查看当前实现：

```text
src/qulab/gui/pyqt_operator_app.py
src/qulab/gui/pyqt_views.py
src/qulab/gui/workflow_model.py
src/qulab/gui/workflow_editor.py
src/qulab/gui/yaml_editor.py
src/qulab/gui/controller.py
src/qulab/gui/qt_compat.py
src/qulab/config/parser.py
configs/experiments/dry_run_rabi.yaml
configs/experiments/dry_run_odmr.yaml
configs/experiments/dry_run_two_mw_scan.yaml
```

---

## 当前项目目录

项目根目录：

```text
<QULAB_PROJECT_ROOT>
```

建议新增或更新：

```text
src/qulab/gui/operator_parameters.py
src/qulab/gui/pyqt_operator_app.py
src/qulab/gui/pyqt_views.py
src/qulab/gui/workflow_model.py
src/qulab/gui/yaml_editor.py
src/qulab/gui/controller.py
docs/OPERATOR_UI.md
docs/CONFIG_SCHEMA.md
```

建议新增测试：

```text
tests/unit/test_operator_parameters_model.py
tests/unit/test_operator_parameters_yaml_roundtrip.py
tests/unit/test_pyqt_operator_import.py
tests/integration/test_gui_edit_dry_run_effect.py
```

---

## 架构规则

必须遵守：

1. GUI 是 config/procedure 的编辑器，不是实验逻辑的唯一载体。
2. GUI 保存的 YAML 必须可被 CLI 运行。
3. `Operator Parameters` 和 `Builder Workflow` 修改同一份 workflow/config model。
4. `Operator Parameters` 不隐藏真实 procedure/config；它只是快速编辑视图。
5. 危险硬件动作不能做成普通参数按钮。
6. 默认 GUI 启动不能连接硬件。
7. Qt 缺失时 import 不应失败；GUI tests 必须 skip cleanly。
8. 不破坏现有 workflow tree + inspector。

---

## 具体实现要求

### 1. Submode Switch

在 PyQt Operator Console 中增加 submode 切换 UI：

```text
Operator Parameters | Builder Workflow | Direct Control
```

要求：

- 左侧实验选择、setup 选择、Prepare/Start/Pause/Stop、run status、日志和 live plot 保持一致。
- `Builder Workflow` 显示现有 workflow tree + inspector。
- `Operator Parameters` 显示新的集中参数表单。
- `Direct Control` 本 worker 可显示 `planned / pending P8.3` placeholder，不实现真实控制。

### 2. Operator Parameter Model

新增 `src/qulab/gui/operator_parameters.py`。

推荐对象：

```python
from dataclasses import dataclass

@dataclass
class OperatorParameterSpec:
    name: str
    label: str
    source: str
    value: object
    unit: str | None = None
    widget: str = "auto"
    minimum: float | None = None
    maximum: float | None = None
    choices: list[object] | None = None
    readonly: bool = False
    warning: str | None = None
```

推荐函数：

```python
def discover_operator_parameters(workflow_model, raw_config) -> list[OperatorParameterSpec]: ...

def apply_operator_parameter(workflow_model, raw_config, spec_name: str, value: object) -> None: ...
```

要求：

- model 层必须可在无 Qt 环境测试。
- 修改参数后同步更新 raw config 和 workflow model。
- 保存 YAML 后可重新 parse。
- source path 错误时给 structured warning，不崩溃。

### 3. Parameter Sources

支持两类参数来源。

#### 自动提取

至少支持：

- scan values：
  - linspace: `start`、`stop`、`points`
  - range: `start`、`stop`、`step`
  - explicit values
- average count。
- 常见 call args：
  - number
  - string
  - bool
  - `${param}` 字符串
- `resources.<name>.sequence_file`。
- `storage.backend` 或 `storage.backends`。

#### 显式声明

支持 config 顶层：

```yaml
operator_parameters:
  - name: tau_start_s
    label: Tau start
    unit: s
    source: procedure.scan[tau_s].values.start
    widget: number
    min: 0

  - name: averages
    label: Averages
    source: procedure.average[avg].count
    widget: integer
    min: 1

  - name: sequence_file
    label: ASG sequence
    source: resources.asg.sequence_file
    widget: file_picker
```

要求：

- 如果显式声明存在，GUI 应优先使用声明顺序。
- 可以补充自动发现参数，但不得重复同一 source。
- `name` 使用 snake_case。
- `source` 指向 YAML/config model 中的字段路径。
- 如果 source 无法解析，显示 warning，不崩溃。

### 4. Supported Widgets

MVP 至少支持：

- number input。
- integer input。
- string input。
- bool checkbox。
- enum/simple choices。
- file path text field，file picker 可延后或复用 P8.1。

表单应显示：

- label。
- unit。
- current value。
- validation error/warning。

典型 Rabi 表单：

```text
tau_start_s       [ 20e-9       ]
tau_stop_s        [ 2e-6        ]
tau_points        [ 101         ]
averages          [ 100         ]
mw_freq_hz        [ 2.870e9     ]
mw_power_dbm      [ -10         ]
sequence_file     [ rabi.seq    ]
storage_backends  [ csv,zarr    ]
```

### 5. YAML Round-trip and Dry-run Effect

要求：

- 从 YAML 加载后生成 operator parameter specs。
- 修改表单后保存 YAML。
- 保存后的 YAML 能被 `parse_experiment_config` 重新解析。
- 修改 `tau_points` 后 dry-run point count 或事件数变化。
- 修改 `average count` 后 dry-run DataPoint 数或相关事件数变化。
- 修改 call arg 后 dry-run 使用新值。
- 修改 `resources.asg.sequence_file` 后 config 更新。

---

## 测试要求

新增或更新：

```text
tests/unit/test_operator_parameters_model.py
tests/unit/test_operator_parameters_yaml_roundtrip.py
tests/unit/test_pyqt_operator_import.py
tests/integration/test_gui_edit_dry_run_effect.py
```

测试点：

1. 从 `dry_run_rabi.yaml` 自动发现 tau scan 和 average count。
2. 从 `operator_parameters` 显式声明读取参数。
3. 修改 `tau_points` 后 YAML round-trip。
4. 修改 `average count` 后 workflow/YAML 同步。
5. 修改 call arg 后 dry-run 使用新值。
6. 修改 `resources.asg.sequence_file` 后 config 更新。
7. Direct Control 标记为 pending，不执行硬件动作。
8. 无 Qt 环境下非 UI model tests 仍运行。

---

## Validation Commands

必须运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.gui.pyqt_operator_app import main; print(main.__name__)"
PYTHONPATH=src python -c "from qulab.gui.workflow_model import WorkflowDocument; print(WorkflowDocument.__name__)"
PYTHONPATH=src python -c "from qulab.gui.operator_parameters import discover_operator_parameters; print(discover_operator_parameters.__name__)"
```

如果 Qt 不存在，相关 GUI widget tests 必须 skip，不能 fail。

---

## Non-goals

本 worker 不做：

- 不做 ASG standalone sequence editor launcher；那是 P8.1 worker。
- 不做 Direct Control；那是 P8.3 worker。
- 不连接真实硬件。
- 不启动 ASG/NI/MW/AWG。
- 不实现完整 bench commissioning。
- 不重写 storage/viewer。
- 不破坏现有 Builder Workflow editor。

---

## Expected Deliverables

1. `src/qulab/gui/operator_parameters.py`
2. PyQt Operator Console 中的 `Operator Parameters` / `Builder Workflow` submode switch。
3. `Operator Parameters` 表单 MVP。
4. 自动参数发现和显式 `operator_parameters` 支持。
5. 参数修改后 workflow/YAML 同步。
6. tests 覆盖 discovery、apply、round-trip、dry-run effect、import safety。
7. 如果实现细节和规划不同，更新 `docs/OPERATOR_UI.md` 或 `docs/CONFIG_SCHEMA.md`。
