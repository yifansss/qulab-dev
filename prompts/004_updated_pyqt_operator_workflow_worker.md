# Prompt 004-updated: PyQt Operator Console + Workflow Tree Editor Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在现有 Tkinter GUI MVP 的基础上，做一个更好看、更好用、更接近真实实验软件的 PyQt/PySide 操作者面板。重点不是硬件实测，而是把 GUI 体验、workflow/procedure tree 编辑、YAML round-trip、dry-run 运行和 RunStore 可视化做好。这个 worker 可以一次多做一些内容，但默认测试必须仍然无硬件、无 GUI display 依赖地通过。

---

## /goal

在当前 `qulab` 项目中实现一个清爽白色主色的 PyQt/PySide Operator Console，并加入可编辑的 workflow/procedure tree 面板。该 GUI 必须能加载已有 dry-run YAML，显示和编辑实验流程树、常用扫描参数、average、call step、resources、preflight、run log、run path 和实时 plot；能保存修改后的 YAML；能启动 dry-run 并通过 EventBus + RunStore 更新 UI。必须保留现有 Tkinter MVP，不破坏已有 API 和测试。完成后 `python -m pytest` 必须通过；如果当前环境没有 PyQt/PySide，默认测试仍要通过，GUI 启动命令应给出清楚提示而不是 import 崩溃。

成功标准：

1. 阅读并遵守项目蓝图、Operator UI、GUI worker 规范和当前 GUI 实现。
2. 新增 PyQt/PySide GUI，不删除现有 Tkinter `operator_app.py`。
3. GUI 风格：白色主色、清爽、实验控制台风格、信息密度适中、控件对齐规整。
4. 优先支持 `PySide6`，如果没有则尝试 `PyQt6`，再没有则 GUI 启动时输出友好错误。不要要求联网安装依赖。
5. 默认 tests 不能因为没有 Qt 失败。Qt 相关窗口测试必须 `pytest.importorskip` 或只测试非 Qt model/controller。
6. 支持入口：
   - `python -m qulab.gui.pyqt_operator_app`
   - import 该模块不能自动打开窗口。
7. 支持加载：
   - `configs/experiments/dry_run_odmr.yaml`
   - `configs/experiments/dry_run_rabi.yaml`
   - `configs/experiments/dry_run_two_mw_scan.yaml`
8. 支持 workflow/procedure tree 编辑：
   - 显示 setup / procedure / cleanup。
   - 显示 scan / measurement / average / run / call。
   - 编辑 scan start/stop/points 或 explicit values。
   - 编辑 average count。
   - 编辑 call args 中的简单 scalar 和 `${param}` 引用。
   - 启用/禁用 step，如果 core 暂无 disabled YAML 字段，需要在 parser/serializer 中补齐或在文档中明确实现方式。
   - 支持 add/duplicate/delete step 的 MVP 版本，至少支持对 scan、average、call 的增删复制。
9. 支持 YAML round-trip：
   - GUI 加载 YAML -> 编辑 -> 保存 YAML。
   - 保存后的 YAML 能被 `parse_experiment_config` 解析。
   - 保存后的 YAML 能 dry-run。
10. 支持 Prepare：
    - parse config。
    - build mock resources。
    - run SyncValidator。
    - 显示 resource table 和 preflight issue table。
11. 支持 Start dry-run：
    - 后台线程运行 executor。
    - RunStore 保存数据。
    - UI 实时显示事件 log、progress、run path。
    - plot 根据 DataPoint 更新。
12. 支持 Stop 的诚实 MVP 行为：
    - 如果 core executor 暂无取消机制，不要假装可靠 stop。
    - UI 可禁用重复 Start，并显示“当前 dry-run 不支持中途取消”。
13. 增强 plot：
    - 一维 line plot 必须可见、非空。
    - 对二维扫描，至少显示 point table 或简易 heatmap grid；如果实现 heatmap，保持简洁。
    - 不强制 matplotlib/pyqtgraph；可用 Qt painting 或 QGraphicsView。如果 pyqtgraph 已可用，可选使用，但不能成为默认硬依赖。
14. 增加 tests：
    - workflow tree YAML model round-trip。
    - edit scan values 后 dry-run 点数变化。
    - edit average count 后 dry-run DataPoint 数或事件数变化。
    - call args `${param}` 保存/解析正确。
    - pyqt module import does not launch window。
    - no Qt installed 时 fallback/error message 行为可测试。
15. 更新 README、docs/OPERATOR_UI.md、docs/IMPLEMENTATION_ORDER.md、workers/gui_worker.md，说明新 PyQt GUI、当前限制和启动方式。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/OPERATOR_UI.md`
4. `docs/CONFIG_SCHEMA.md`
5. `docs/DATA_MODEL.md`
6. `docs/IMPLEMENTATION_ORDER.md`
7. `workers/gui_worker.md`
8. `workers/qa_worker.md`

同时查看当前实现：

```text
src/qulab/core/
src/qulab/storage/
src/qulab/config/
src/qulab/instruments/
src/qulab/sync/
src/qulab/gui/controller.py
src/qulab/gui/models.py
src/qulab/gui/procedure_tree.py
src/qulab/gui/plot_model.py
src/qulab/gui/operator_app.py
configs/experiments/dry_run_odmr.yaml
configs/experiments/dry_run_rabi.yaml
configs/experiments/dry_run_two_mw_scan.yaml
```

重点确认：

- 现有 Tk GUI 是 MVP，不要破坏。
- `OperatorController` 已有加载/Prepare/Start dry-run 的能力，可以复用或扩展。
- `ProcedureTreeNode` 和 `ParameterEdit` 已存在，可以作为新 GUI 的后端模型基础。
- `parse_experiment_config` 是 YAML -> Procedure 的权威入口。
- `RunStore` 是数据保存入口。

---

## 当前项目目录

项目根目录：

```text
/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab
```

建议新增或更新：

```text
src/qulab/gui/qt_compat.py
src/qulab/gui/pyqt_operator_app.py
src/qulab/gui/pyqt_views.py
src/qulab/gui/workflow_editor.py
src/qulab/gui/workflow_model.py
src/qulab/gui/yaml_editor.py
src/qulab/gui/controller.py
src/qulab/gui/__init__.py
```

建议新增测试：

```text
tests/unit/test_workflow_model.py
tests/unit/test_workflow_yaml_roundtrip.py
tests/unit/test_pyqt_operator_import.py
tests/unit/test_gui_edit_dry_run_effect.py
tests/integration/test_pyqt_controller_roundtrip.py
```

如果写 Qt widget 测试：

```text
tests/gui/test_pyqt_views_optional.py
```

但必须在没有 Qt 时 skip。

---

## UI 设计目标

做成一个“实验操作台”，不是 demo 玩具。

视觉要求：

- 主色白色和浅灰。
- 少量蓝色作为 primary accent。
- 状态颜色：
  - ok：绿色
  - warning：橙色
  - error：红色
  - inactive：灰色
- 字体大小克制，避免大标题。
- 分栏清楚，控件不要拥挤。
- 不要使用花哨渐变、深色背景、装饰性卡片。

推荐布局：

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Qulab Operator Console                     [Load] [Save] [Prepare] [Start] │
├────────────────────┬──────────────────────────────┬────────────────────────┤
│ Experiments         │ Workflow / Procedure Tree    │ Inspector              │
│ - dry_run_odmr      │ setup                        │ selected step details  │
│ - dry_run_rabi      │ procedure                    │ scan start/stop/points │
│ - two_mw_scan       │  ├─ scan tau_s               │ call args editor       │
│                     │  │   └─ measurement point    │ enabled checkbox       │
│ Resources           │  │       └─ run readout      │                        │
│ mw/asg/daq status   │ cleanup                      │ Preflight Issues       │
├────────────────────┴──────────────────────────────┴────────────────────────┤
│ Live Plot / Data Preview                                                    │
├────────────────────────────────────────────────────────────────────────────┤
│ Run Log                                                                     │
│ Run path: ...                                                               │
└────────────────────────────────────────────────────────────────────────────┘
```

控件建议：

- `QMainWindow`
- `QSplitter`
- `QTreeView` or `QTreeWidget`
- `QTableWidget` for resources/preflight/data preview
- `QFormLayout` for inspector
- `QPlainTextEdit` for logs
- `QGraphicsView` / custom QWidget for plot
- Toolbar buttons: Load, Save, Prepare, Start, Stop

---

## PyQt/PySide Compatibility

实现 `qt_compat.py`：

```python
QT_AVAILABLE = False
QT_API = None

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    QT_AVAILABLE = True
    QT_API = "PySide6"
except ImportError:
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
        QT_AVAILABLE = True
        QT_API = "PyQt6"
    except ImportError:
        QtCore = QtGui = QtWidgets = None
```

要求：

- `import qulab.gui.pyqt_operator_app` 不因 Qt 缺失失败。
- `main()` 中如果 Qt 不可用，打印清楚说明并返回非零或 raise SystemExit。
- tests 可以验证 fallback。

---

## Workflow Model

GUI 编辑不要直接乱改 widgets。请做独立 model。

推荐：

```python
@dataclass
class WorkflowNode:
    id: str
    kind: str
    label: str
    path: tuple[Any, ...]
    enabled: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    children: list["WorkflowNode"] = field(default_factory=list)
```

功能：

```python
def build_workflow_tree(config: dict) -> WorkflowNode: ...
def get_node(config: dict, path: tuple[Any, ...]) -> Any: ...
def update_node(config: dict, path: tuple[Any, ...], patch: dict) -> dict: ...
def add_step(config: dict, parent_path: tuple[Any, ...], step: dict) -> dict: ...
def delete_step(config: dict, path: tuple[Any, ...]) -> dict: ...
def duplicate_step(config: dict, path: tuple[Any, ...]) -> dict: ...
```

要求：

- 所有修改返回新的 config 或明确原地修改并测试覆盖。
- path 设计要稳定，能定位 YAML 中的 step。
- 支持 setup/procedure/cleanup 三个根。
- 保存时使用 `yaml.safe_dump`。

---

## Inspector 编辑能力

选中不同节点时，右侧 inspector 提供：

### Scan

- name
- values type: explicit / linspace / range
- start
- stop
- points
- step
- explicit values

### Average

- name
- count

### Call

- call string
- args table
- save_as

Args table MVP：

- key
- value
- type string/number/ref

`"${tau_s}"` 这类参数引用必须保存为 YAML 中的 `${tau_s}`，再次 parse 后变成 `P("tau_s")`。

### Measurement / Run

- name
- timeout_s for run

### Common

- enabled checkbox。

如果当前 parser/core 还没有 enabled YAML 支持，worker 应补充：

- parser 读取 `enabled: false`。
- Step.enabled 设置对应值。
- serializer 保存 enabled。
- tests 覆盖 disabled step 不执行。

---

## Controller Integration

可以扩展 `OperatorController`，也可以新增 `QtOperatorController`，但避免重复核心逻辑。

必须支持：

```python
controller.load_config(path)
controller.current_config
controller.prepare()
controller.start_dry_run(event_callback=...)
controller.save_config(path)
```

新增：

```python
controller.update_workflow_node(...)
controller.add_workflow_step(...)
controller.delete_workflow_step(...)
controller.duplicate_workflow_step(...)
```

Start 运行：

- 后台线程。
- 事件进入 queue。
- UI 主线程 timer 刷新。

不要从 worker thread 直接更新 Qt widgets。

---

## Plot / Preview

当前 `PlotSeries` 可复用。

PyQt GUI 需要：

- line plot widget。
- 数据点计数显示。
- latest x/y 显示。
- 如果二维扫描，MVP 可以显示 data preview table：
  - point_id
  - coords
  - scalar y

如果实现 heatmap：

- 用简单颜色矩形即可。
- 不要求高级交互。

---

## YAML Round-trip

必须保证：

1. Load original YAML。
2. GUI model 修改 scan points/average count/call arg。
3. Save YAML。
4. Reload YAML。
5. `parse_experiment_config` 成功。
6. dry-run 成功。

测试必须覆盖至少：

- Rabi 修改 `tau_s` points。
- Rabi 修改 average count。
- Two-MW 修改 `probe_freq_hz` points。
- call arg `${tau_s}` 保存不变形。

---

## Optional Qt Launch Verification

worker 可以尝试：

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

但如果窗口会阻塞当前自动会话，不要强行保持运行。可以只验证 import 和 main availability。

如果环境无 Qt，最终回复说明：

```text
Qt binding not installed; GUI code is present and import-safe, tests cover non-Qt models.
```

不要联网安装 Qt。

---

## 严格禁止

- 不要删除 Tkinter GUI。
- 不要连接真实硬件。
- 不要导入 `nidaqmx`、`pyvisa`、`serial`、ASG DLL 或 `../pycontrol`。
- 不要让 core/storage/config 依赖 Qt。
- 不要在 import 时打开窗口。
- 不要让 default tests 需要 display server。
- 不要使用 eval。
- 不要用需要联网安装的新依赖。
- 不要做虚假的真实 stop/pause。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.gui.pyqt_operator_app import main; print(main.__name__)"
PYTHONPATH=src python -c "from qulab.gui.workflow_model import build_workflow_tree; print(build_workflow_tree.__name__)"
PYTHONPATH=src python -c "from qulab.gui.qt_compat import QT_AVAILABLE, QT_API; print(QT_AVAILABLE, QT_API)"
```

如果 Qt available，可以额外说明是否手动启动过：

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

---

## 文档更新要求

完成后至少更新：

```text
README.md
docs/OPERATOR_UI.md
docs/IMPLEMENTATION_ORDER.md
workers/gui_worker.md
```

说明：

- Tkinter MVP 仍保留。
- PyQt/PySide GUI 是新的推荐 operator console。
- 如何启动。
- 如果 Qt 没安装如何处理。
- 当前 workflow editor 支持哪些编辑。
- 当前限制：真实硬件连接、可靠 stop/pause、复杂 step library、专业 heatmap 等留给后续。

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 使用了 PySide6 / PyQt6 / fallback 中的哪种。
3. GUI 如何启动。
4. 现在能在 GUI 中编辑哪些 workflow 内容。
5. YAML round-trip 测试覆盖了什么。
6. 运行了哪些验证命令，结果是什么。
7. 是否保持默认测试无硬件、无 display 依赖。
8. 还没做什么，明确留给后续 worker。

