# Prompt 004: GUI Operator Console Worker

下面这份 prompt 可以直接复制给新的 AI worker。目标是在已有 core + storage + config + mock instruments + sync 的基础上，实现一个可以直观看到效果的 MVP GUI：操作者可以加载 dry-run YAML，查看 procedure tree，编辑常用扫描参数，运行 simulated experiment，看到仪器状态、preflight、实时日志、简单实时图和 run path。这个 worker 仍然不接触真实硬件。

---

## /goal

在当前 `qulab` 项目中实现第一个可视化 MVP：一个无真实硬件依赖、可直接运行的 Operator Console GUI。GUI 必须能加载 `configs/experiments/dry_run_odmr.yaml` 和 `configs/experiments/dry_run_rabi.yaml`，显示 procedure tree、resources、sync/preflight、常用 scan/average 参数，允许用户修改常用参数后启动 dry-run，并通过 EventBus + RunStore 显示实时日志、简单 line/heatmap 预览和最终 run path。完成后必须提供一个可运行入口，例如 `python -m qulab.gui.operator_app`，并有 headless-friendly 测试覆盖 GUI 后端逻辑。完成后 `python -m pytest` 必须通过。

成功标准：

1. 阅读并遵守项目蓝图、Operator UI 文档和 GUI worker 规范。
2. 实现一个能直接打开的 MVP GUI，不要求最终工业美术，但必须清晰、稳定、可用。
3. GUI 默认使用无额外安装依赖的 Python 标准库 Tkinter/ttk；如果本机已有 Qt 也不要强制依赖 Qt。后续 PyQt GUI 可以另做。
4. GUI 不能导入 pycontrol、NI、ASG SDK、pyvisa、serial 或真实硬件依赖。
5. GUI 必须通过已有 `qulab.config`、`qulab.core`、`qulab.storage`、`qulab.sync` 工作，不绕过 executor 直接写数据。
6. 支持选择/加载 dry-run YAML。
7. 支持显示 procedure tree：
   - setup
   - scan
   - measurement
   - average
   - run
   - call
   - cleanup
8. 支持编辑常用参数：
   - scan start/stop/points 或 explicit values
   - average count
   - 资源 connect_on_load/simulation 状态显示即可，MVP 不要求复杂编辑
9. 支持 Prepare/Preflight：
   - parse YAML
   - build mock resources
   - run SyncValidator
   - 显示 warnings/errors
10. 支持 Start：
    - 使用当前 GUI 中修改后的 config
    - 创建 RunStore
    - 运行 ExperimentExecutor
    - 显示 RunStarted、ParameterChanged、MeasurementStarted、DataPoint、MeasurementCompleted、RunCompleted 等事件
    - 显示 run path
11. 支持 Stop 按钮的 MVP 行为：
    - 如果当前 executor 还不支持真正取消，Stop 至少禁用重复 start，并在 log 中说明当前 dry-run 不支持中途取消。
    - 不要假装已经实现可靠 pause/resume。
12. 支持简单 live plot：
    - ODMR/Rabi line plot：x 使用当前 scan coord，y 使用 `counts_mean` 或 DataPoint 中可用 numeric scalar。
    - 如果遇到二维数据，可显示简化 heatmap/table，或至少显示 latest point table；MVP 重点是 ODMR/Rabi line plot。
    - 不要求 matplotlib；可用 Tkinter Canvas 画坐标轴和折线。
13. 提供 tests：
    - config scan parameter extraction/update。
    - procedure tree node model generation。
    - event-to-plot data reducer。
    - GUI app module import 不启动窗口。
    - 可选 integration：用 GUI controller 后端跑 dry-run 并生成 RunStore。
14. 更新 README 和 `docs/OPERATOR_UI.md`，说明如何启动 GUI。

---

## 必须先阅读

worker 开始任何代码修改前，必须阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/OPERATOR_UI.md`
4. `docs/CONFIG_SCHEMA.md`
5. `docs/DATA_MODEL.md`
6. `docs/HARDWARE_SYNC.md`
7. `docs/IMPLEMENTATION_ORDER.md`
8. `workers/gui_worker.md`
9. `workers/qa_worker.md`

同时查看当前实现：

```text
src/qulab/core/
src/qulab/storage/
src/qulab/config/
src/qulab/instruments/
src/qulab/sync/
configs/experiments/dry_run_odmr.yaml
configs/experiments/dry_run_rabi.yaml
```

重点确认：

- `run_dry_config(...)` 已经存在，但为了 GUI 实时日志，可能需要更细粒度地手动组合 parser、EventBus、RunStore、ExperimentExecutor。
- `ExperimentExecutor` 当前是同步执行，GUI 不应在主线程中长时间阻塞。
- core 不支持可靠 pause/resume/stop，GUI 不要虚假承诺。
- storage 测试必须使用临时目录；GUI 默认 run root 可以是用户选择或项目 `runs/`。

---

## 当前项目目录

项目根目录：

```text
<QULAB_PROJECT_ROOT>
```

GUI 代码应放在：

```text
src/qulab/gui/
```

测试应放在：

```text
tests/unit/
tests/integration/
```

不要修改：

```text
../pycontrol
../panel(basic)
```

不要实现真实 hardware adapter。

---

## 推荐实现文件

请创建或更新：

```text
src/qulab/gui/operator_app.py
src/qulab/gui/controller.py
src/qulab/gui/models.py
src/qulab/gui/procedure_tree.py
src/qulab/gui/plot_model.py
src/qulab/gui/__init__.py

tests/unit/test_gui_models.py
tests/unit/test_gui_procedure_tree.py
tests/unit/test_gui_plot_model.py
tests/integration/test_gui_controller_dry_run.py
```

如果需要拆分 Tkinter widgets，可以增加：

```text
src/qulab/gui/tk_views.py
```

但请把非 GUI 逻辑放在 `controller.py` / `models.py` / `plot_model.py`，方便 headless tests。

---

## UI 目标布局

MVP 主界面建议如下：

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Qulab Operator Console                                                     │
├────────────────────┬────────────────────────────┬──────────────────────────┤
│ Experiments         │ Procedure Tree             │ Resources / Preflight    │
│ [dry_run_odmr]      │ setup                      │ mw    mock connected     │
│ [dry_run_rabi]      │  ├─ mw.set_power           │ asg   mock connected     │
│ Load YAML...        │ scan mw_freq_hz            │ daq   mock connected     │
│                     │  └─ measurement point      │                          │
│ Parameters          │      └─ run readout        │ Preflight                │
│ mw_freq_hz start    │          └─ daq.read...    │ ✓ resources exist        │
│ mw_freq_hz stop     │                            │ ✓ sync order ok          │
│ points              │                            │                          │
│ averages            │                            │ Prepare  Start  Stop     │
├────────────────────┴────────────────────────────┴──────────────────────────┤
│ Live Plot                                                                   │
│ counts_mean vs scan coord                                                   │
├────────────────────────────────────────────────────────────────────────────┤
│ Run Log                                                                     │
│ Run path: runs/...                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

用 Tkinter/ttk 实现即可：

- `ttk.Treeview` 显示 procedure tree。
- `ttk.Entry` / `ttk.Spinbox` 编辑参数。
- `ttk.Button` 控制 Prepare/Start/Stop。
- `tk.Text` 显示 log。
- `tk.Canvas` 画简单折线图。

---

## 具体实现要求

### 1. App Entry

提供可运行入口：

```bash
python -m qulab.gui.operator_app
```

模块要求：

- import 不启动窗口。
- 只有 `main()` 调用时才创建 Tk root。
- 支持默认加载 `configs/experiments/dry_run_rabi.yaml`。

示例：

```python
def main() -> None:
    app = OperatorApp()
    app.run()

if __name__ == "__main__":
    main()
```

### 2. GUI Controller

实现非 GUI 后端，方便测试：

```python
class OperatorController:
    def __init__(self, run_root: Path | str = "runs") -> None: ...
    def load_config(self, path: Path | str) -> None: ...
    def get_parameter_edit_model(self) -> list[ParameterEdit]: ...
    def update_parameter(self, path_or_id: str, value: Any) -> None: ...
    def prepare(self) -> PreflightViewModel: ...
    def start_dry_run(self, event_callback: Callable[[Event], None] | None = None) -> RunViewModel: ...
```

要求：

- controller 持有当前 config dict。
- `prepare()` 解析当前 config，运行 sync validation。
- `start_dry_run()` 使用当前 config 创建 `EventBus`、`RunStore`、`ExperimentExecutor`。
- tests 可直接调用 controller，不需要打开 GUI。

### 3. Threading

GUI Start 不要卡住主线程。

MVP 可以：

- 用 `threading.Thread` 在后台运行 executor。
- event callback 把事件放入 `queue.Queue`。
- Tk 主线程用 `after(...)` 定时读取 queue 并更新 log/plot。

注意：

- 不要从后台线程直接操作 Tk widgets。
- RunStore 和 EventBus 在后台线程使用。
- dry-run 很快结束也没关系，但 UI 要能显示最终 log 和 plot。

### 4. Procedure Tree Model

实现从 `Procedure` 或 config 生成树节点模型：

```python
@dataclass
class ProcedureTreeNode:
    label: str
    kind: str
    details: str
    children: list["ProcedureTreeNode"]
```

要求：

- setup/body/cleanup 顶层分组清楚。
- scan 显示参数名和 values summary。
- average 显示 count。
- call 显示 resource.method 和 save_as。
- measurement/run 显示 name。

### 5. Parameter Edit Model

从 config 中提取可编辑项：

- scan start/stop/points。
- scan explicit values，MVP 可以显示为逗号分隔字符串。
- average count。

实现：

```python
@dataclass
class ParameterEdit:
    id: str
    label: str
    value: Any
    value_type: str
    path: tuple[Any, ...]
```

`path` 用于更新 config 中对应字段。

要求：

- 不要用 eval。
- 数字输入支持 int/float/scientific notation。
- 错误输入要在 GUI log 或 messagebox 中提示。

### 6. Resource/Preflight View

Prepare 后显示：

- resource name。
- adapter。
- capabilities。
- simulation/mock。
- health/snapshot 简要信息。

Preflight 显示：

- issue severity。
- code。
- message。

如果有 error，不允许 Start，除非用户显式 override；MVP 不需要实现 override。

### 7. Event Log

把事件变成人可读日志：

示例：

```text
RunStarted dry_run_rabi
ParameterChanged tau_s=2e-08
MeasurementStarted p000001 coords={...}
DataPoint p000001 counts.counts_mean=1000.0
MeasurementCompleted p000001 ok
RunCompleted completed
```

### 8. Plot Model

实现独立于 Tk 的 plot reducer：

```python
class PlotSeries:
    def handle_event(self, event: Event) -> None: ...
    @property
    def points(self) -> list[tuple[float, float]]: ...
```

规则：

- 从 `DataPoint.coords` 中选择第一个 numeric coord 作为 x。
- 从 `DataPoint.data` 中寻找 numeric scalar 作为 y。
- 如果 `DataPoint.data` 是 `{save_as: {"counts_mean": ...}}`，要能递归找到 numeric scalar。
- 如果没有 numeric x，使用点序号。
- 如果没有 numeric y，不添加点。

Canvas 绘图：

- 清空后重画 axes 和 polyline。
- 显示 latest point count。
- 不要求精美，但不能空白。

### 9. RunStore Integration

GUI 运行时必须真的写 RunStore。

用户启动 dry-run 后，log 中显示：

```text
Run path: /.../runs/YYYY-MM-DD/...
```

测试中 run root 使用 `tmp_path`。

### 10. Example Launch

README 中加入：

```bash
PYTHONPATH=src python -m qulab.gui.operator_app
```

也可以说明：

```text
默认加载 configs/experiments/dry_run_rabi.yaml
点击 Prepare
点击 Start
查看 Live Plot 和 Run path
```

---

## 严格禁止

- 不要连接真实硬件。
- 不要导入 `nidaqmx`、`pyvisa`、`serial`、ASG DLL 或 `../pycontrol`。
- 不要实现真实 pycontrol adapters。
- 不要让 core 依赖 GUI。
- 不要让 storage 依赖 GUI。
- 不要在 import `qulab.gui.operator_app` 时自动打开窗口。
- 不要让测试打开真实 GUI 窗口。
- 不要使用需要联网安装的新依赖。
- 不要声称已经实现可靠 pause/resume/stop，如果只是 dry-run placeholder。

---

## 验证命令

完成后运行：

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.gui.operator_app import main; print(main.__name__)"
PYTHONPATH=src python -c "from qulab.gui.controller import OperatorController; print(OperatorController.__name__)"
```

如果环境允许，可以手动启动：

```bash
PYTHONPATH=src python -m qulab.gui.operator_app
```

手动启动不是自动测试要求，但 worker 最终回复中应说明是否尝试启动过。

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

- 当前 GUI 是 Tkinter MVP。
- 当前只支持 mock/dry-run。
- 当前 Stop/Pause 的真实限制。
- 后续如何迁移到 PyQt/pyqtgraph。

---

## 最终回复要求

worker 完成后必须汇报：

1. 改动了哪些文件。
2. 实现了哪些 GUI/controller/model 对象。
3. GUI 如何启动。
4. 能看到什么效果。
5. 运行了哪些验证命令，结果是什么。
6. 是否保持 core/storage/config 与 GUI 解耦。
7. 还没做什么，明确留给后续 worker。
8. 是否修改了公共 API。

---

## 后续 worker 依赖

这个 worker 完成后，后续 worker 可以继续：

- plotting worker：把 Canvas plot 升级为 pyqtgraph/matplotlib 或更完整 heatmap。
- pycontrol adapter worker：把 mock instruments 扩展到真实 pycontrol adapters。
- GUI editor worker：增强 procedure tree 的拖拽编辑、step library、禁用 step。
- hardware sync worker：增强 ASG/NI connection table 和真实 preflight。

