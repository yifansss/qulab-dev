# Prompt 004-followup P8.1: ASG Sequence Panel / Editor Bridge Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在现有 PyQt/PySide Operator Console 基础上，完成 P8.1：把已有 standalone ASG sequence editor 接入 Qulab GUI 的 ASG 子面板。重点是 sequence 文件选择、打开外部 editor、读取/刷新 sequence metadata/hash、显示可扫描参数、提供参数绑定入口，并把 sequence snapshot 暴露给 preflight/metadata。这个 worker 不做真实硬件输出，不实现通用 pulse compiler，不修改 standalone sequence editor。

---

## /goal

在当前 `qulab` 项目中实现 ASG Sequence Panel / Editor Bridge。Qulab GUI 应复用已有 standalone sequence editor，而不是重新实现完整 pulse editor。主 workflow tree 仍只表达宏观 procedure 和 measurement point 内的 `asg.load_sequence`、`asg.set_sequence_param`、`asg.arm`、`asg.start` 等动作，不展开 sequence 内部纳秒/微秒级脉冲。

成功标准：

1. 阅读并遵守项目蓝图、GUI、config、hardware sync、adapter 和 QA 规范。
2. 不连接真实硬件，不启动 ASG，不打开微波输出，不写 NI AO。
3. 不修改 `../pycontrol`。
4. 不修改 `../panel(basic)/sequence_editor/sequence_editor.py`。
5. 新增 import-safe 的 sequence bridge model，能检查 sequence 文件 path、exists、mtime、size、hash、warnings。
6. 支持从 ASG resource config 读取和更新 `sequence_file`、`sequence_params`。
7. PyQt/PySide Operator Console 中提供 ASG sequence controls：sequence file path、Browse/Select、Open Editor、Refresh metadata、hash/status/warnings、sequence params/channel info。
8. `Open Editor` 通过 wrapper 调用已有 standalone editor；missing editor、依赖缺失、启动失败都不能让 Qulab 崩溃。
9. Prepare/preflight 阶段能显示 sequence file 状态，例如 missing、selected、hash available、duration unknown。
10. 能形成 sequence snapshot model，至少包含 path、exists、mtime、size、sha256、warnings。
11. 保存后的 YAML 仍可由 CLI dry-run。
12. 默认 `python -m pytest` 在无 Qt、无硬件、无 pycontrol 环境中通过；Qt widget tests 必须 skip cleanly。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/OPERATOR_UI.md`
4. `docs/IMPLEMENTATION_ORDER.md`
5. `docs/CONFIG_SCHEMA.md`
6. `docs/HARDWARE_SYNC.md`
7. `docs/ADAPTER_REQUIREMENTS.md`
8. `workers/gui_worker.md`
9. `workers/sync_worker.md`
10. `workers/qa_worker.md`

重点阅读：

```text
docs/ARCHITECTURE.md
  - 5.1 Timing Model Boundary
  - 5.2 ASG Sequence Editor Boundary
  - GUI Layer submode rules

docs/OPERATOR_UI.md
  - 3.3 同一界面内的 Submode 切换
  - 5 仪器子面板 / ASG 子面板
  - ASG sequence editor bridge

docs/IMPLEMENTATION_ORDER.md
  - P8.1 ASG Sequence Panel / Editor Bridge

docs/CONFIG_SCHEMA.md
  - Resources 中 sequence_file / sequence_params
  - 10. ASG Sequence File and Parameter Binding
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
src/qulab/instruments/adapters/mock.py
src/qulab/instruments/adapters/pycontrol.py
configs/experiments/dry_run_rabi.yaml
configs/experiments/dry_run_odmr.yaml
```

已有 standalone sequence editor 位于平行项目：

```text
../panel(basic)/sequence_editor/sequence_editor.py
```

注意：这个路径在 Qulab workspace 外，默认不要修改它。只做调用/桥接。

---

## 当前项目目录

项目根目录：

```text
/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab
```

建议新增或更新：

```text
src/qulab/gui/sequence_bridge.py
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
tests/unit/test_sequence_bridge.py
tests/unit/test_asg_sequence_config_model.py
tests/unit/test_operator_parameters_sequence_file.py
tests/unit/test_pyqt_operator_import.py
```

---

## 架构规则

必须遵守：

1. GUI 不直接调用底层硬件 driver。
2. GUI 只能编辑 config/model，或调用 controller/executor/bench 层。
3. ASG sequence editor bridge 不等于 pulse compiler。
4. 主 workflow tree 不展开纳秒/微秒 pulse sequence。
5. sequence 文件属于 ASG resource/instrument panel 管理。
6. 打开 sequence editor 不应自动连接硬件或启动输出。
7. 默认 GUI 启动不能连接硬件。
8. Qt 缺失时 import 不应失败；GUI tests 必须 skip cleanly。
9. 保存后的 YAML 必须能被 CLI dry-run。

---

## 具体实现要求

### 1. Sequence Bridge Model

新增 `src/qulab/gui/sequence_bridge.py`。

推荐对象：

```python
from dataclasses import dataclass

@dataclass
class SequenceFileInfo:
    path: str
    exists: bool
    mtime: float | None
    size_bytes: int | None
    sha256: str | None
    parameters: list[str]
    channels: list[str]
    warnings: list[str]
```

推荐对象：

```python
@dataclass
class SequenceEditorLaunchResult:
    ok: bool
    editor_path: str
    sequence_path: str | None
    message: str
    pid: int | None = None
```

推荐函数：

```python
def inspect_sequence_file(path: str) -> SequenceFileInfo: ...

def open_sequence_editor(
    editor_path: str,
    sequence_path: str | None = None,
) -> SequenceEditorLaunchResult: ...
```

要求：

- `inspect_sequence_file` 必须能在无 Qt、无硬件环境运行。
- 文件存在时计算 stable sha256。
- 文件不存在时返回 `exists=False` 和 warning，不抛出未处理异常。
- 如果暂时无法解析 sequence params/channels，可以返回空列表并给 warning/info。
- `open_sequence_editor` 在测试中必须可 monkeypatch，不实际启动外部 GUI。
- missing editor path 返回 friendly error。
- editor 依赖缺失或启动失败返回 result，不让 Qulab GUI 崩溃。

### 2. Config Model Support

支持 ASG resource 中的 sequence 字段：

```yaml
resources:
  asg:
    adapter: mock_pulse
    capabilities: [pulse_sequencer, trigger_source]
    sequence_file: configs/sequences/rabi.seq
    sequence_params:
      tau_s: ${tau_s}
      laser_width_s: 3e-6
```

要求：

- GUI 可读取 `resources.asg.sequence_file`。
- GUI 可修改 `resources.asg.sequence_file` 并保存 YAML。
- GUI 可读取/显示 `resources.asg.sequence_params`。
- procedure 中仍保留宏观步骤，不展开 pulse sequence。

### 3. PyQt/PySide UI

在现有 PyQt Operator Console 中加入 ASG sequence controls。可以先放在 instrument/resource panel 或右侧 inspector 区域，不要新建独立大应用。

MVP 控件：

- sequence file path text/display。
- Browse / Select sequence file。
- Open Editor。
- Refresh metadata。
- hash/status/warnings display。
- sequence params list。
- channel/trigger info area，如果可解析。

UI 行为：

- 如果 no Qt，模块 import 仍安全。
- 如果 standalone editor 不存在，显示 friendly message。
- 如果 sequence file missing，显示 warning，但允许用户继续编辑 config。
- Browse/Select 只改 config/model，不连接硬件。
- Open Editor 只启动 standalone editor，不执行实验。

### 4. Preflight and Metadata Snapshot

Prepare/preflight 阶段应显示 sequence status：

- sequence file missing。
- sequence file selected。
- hash available。
- estimated duration unknown。

形成 sequence snapshot model：

```json
{
  "resource": "asg",
  "sequence_file": "configs/sequences/rabi.seq",
  "exists": true,
  "mtime": 1234567890.0,
  "size_bytes": 1234,
  "sha256": "...",
  "parameters": ["tau_s"],
  "warnings": []
}
```

如果当前 RunStore metadata 暂不支持写入，可以先在 GUI/controller/preflight view model 中暴露这份 snapshot，并加测试。不要为了此任务大改 storage。

---

## 测试要求

新增或更新：

```text
tests/unit/test_sequence_bridge.py
tests/unit/test_asg_sequence_config_model.py
tests/unit/test_operator_parameters_sequence_file.py
tests/unit/test_pyqt_operator_import.py
```

测试点：

1. sequence file hash 计算稳定。
2. missing sequence file 返回 warning，不崩溃。
3. missing editor path 返回 friendly error。
4. `open_sequence_editor` 可 monkeypatch，不实际打开外部 GUI。
5. config/model 可以读取和修改 `resources.asg.sequence_file`。
6. PyQt import-safe；无 Qt 环境 skip widget tests。
7. 保存后的 YAML 可由 `parse_experiment_config` 解析。

---

## Validation Commands

必须运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.gui.pyqt_operator_app import main; print(main.__name__)"
PYTHONPATH=src python -c "from qulab.gui.sequence_bridge import inspect_sequence_file; print(inspect_sequence_file.__name__)"
```

如果 Qt 不存在，相关 GUI widget tests 必须 skip，不能 fail。

---

## Non-goals

本 worker 不做：

- 不连接真实 ASG。
- 不启动 ASG。
- 不打开微波输出。
- 不写 NI AO。
- 不修改 `../pycontrol`。
- 不修改 `../panel(basic)/sequence_editor/sequence_editor.py`。
- 不复制整个 sequence editor 到 Qulab。
- 不实现通用 pulse compiler。
- 不把 pulse sequence 展开进 workflow tree。
- 不做 Operator Parameters submode 的完整表单；那是 P8.2 worker。
- 不做 Direct Control submode；那是后续 P8.3 worker prompt。

---

## Expected Deliverables

1. `src/qulab/gui/sequence_bridge.py`
2. PyQt Operator Console 中的 ASG sequence controls。
3. sequence file path / hash / warning / params model。
4. external standalone editor launcher wrapper。
5. tests 覆盖 hash、missing file、missing editor、config model、import safety。
6. 如果实现细节改变 config 字段，更新 `docs/CONFIG_SCHEMA.md`。
7. 如果 UI 行为和规划不同，更新 `docs/OPERATOR_UI.md`。
