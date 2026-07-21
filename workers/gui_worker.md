# GUI Worker Specification

## Mission

实现轻量 GUI，让用户可以编辑 setup、procedure、仪器面板并运行实验。

## Must Read

- `docs/CONFIG_SCHEMA.md`
- `docs/ARCHITECTURE.md`

## GUI Principle

GUI 是 config/procedure 的编辑器，不是实验逻辑的唯一载体。GUI 保存的 YAML 必须可被 CLI 运行。

MVP 阶段 GUI 不是可选项。必须先实现最小可用的操作者运行 UI 和 procedure tree editor。

## Deliverables

1. `gui/main_window.py`
2. `gui/setup_editor.py`
3. `gui/procedure_editor.py`
4. `gui/run_monitor.py`
5. `gui/data_browser.py`
6. `gui/instrument_panels/`

## Required Views

- operator run console。
- setup profile panel。
- resource connection status。
- instrument subpanel。
- procedure tree。
- live plot area。
- run log。
- start/stop/pause controls。

## MVP Operator Run Console

必须包含：

1. experiment selector。
2. setup profile selector。
3. common parameter editor。
4. instrument connection/status list。
5. preflight check panel。
6. start、pause、stop、prepare controls。
7. live plot area。
8. run log。
9. current run path display。

当前 Tkinter MVP 已实现：

- 入口：`PYTHONPATH=src python -m qulab.gui.operator_app`。
- 后端：`qulab.gui.controller.OperatorController`，可在 headless tests 中加载 config、编辑参数、Prepare 和 Start dry-run。
- 模型：`ParameterEdit`、`ProcedureTreeNode`、`PlotSeries`、resource/preflight/run view models。
- UI：实验选择、YAML 加载、常用参数编辑、procedure tree、resource/preflight 面板、Prepare/Start/Stop、Canvas line plot、run log、run path。
- 约束：只使用 Tkinter/ttk 和 mock adapters，不导入真实硬件依赖。

当前限制和后续方向：

- Stop 只记录请求，不实现可靠 pause/resume/cancel。
- Procedure tree 目前是显示和常用参数编辑，不支持拖拽、禁用 step、复杂 call args 编辑或保存新 YAML。
- Live Plot 是基础 Canvas line plot；后续可迁移到 PyQt/pyqtgraph 并增加 heatmap。

## PyQt/PySide Operator Console

当前新增推荐 GUI：

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

Qt binding 策略：

- 优先 `PySide6`。
- fallback 到 `PyQt6`。
- 如果都不存在，模块 import 仍安全，启动命令输出友好错误；默认 pytest 不依赖 Qt 或 display。

新增后端/视图：

- `qulab.gui.qt_compat`：可选 Qt binding 探测。
- `qulab.gui.workflow_model`：独立 workflow tree 编辑模型。
- `qulab.gui.yaml_editor`：YAML dump/save/parse round-trip helper。
- `qulab.gui.pyqt_operator_app`：PyQt/PySide 启动入口，import 不开窗口。
- `qulab.gui.pyqt_views`：白色主色三栏 operator console。

当前 workflow editor 支持：

- 显示 setup/procedure/cleanup 和 scan/measurement/average/run/call。
- 编辑 scan linspace/range/explicit values。
- 编辑 average count。
- 编辑 call string、simple scalar args、`${param}` 引用和 save_as。
- 编辑 enabled checkbox，保存为 step 顶层 `enabled: false` 或 `enabled: true`。
- 对 scan/average/call 做 MVP add/duplicate/delete。
- 保存后的 YAML 可被 `parse_experiment_config` 解析并 dry-run。

后续方向：

- 拖拽排序、step library、禁用显示优化和复杂 args/schema validator。
- 专业 2D heatmap、run browser、历史 run 打开。
- executor 级可靠 stop/pause/resume。

## Advanced Data Viewer

Prompt 008 followup requires a read-only viewer path that supports both mandatory
CSV and optional Zarr advanced storage:

- Provide a backend selector: Auto / CSV / Zarr.
- Provide a run-folder selector in the viewer side panel. Launching on a parent
  directory should discover child run folders with `dataset_manifest.json`; the
  user can select one and load it in-place.
- The viewer path argument is optional; without one, default to `runs/`.
- Provide a plot type selector for scalar data: Line Slice / Heatmap. Datasets
  with `time_s` use Trace mode.
- Plot type availability must be derived from manifest/data spec semantics
  (`kind`, `dims`, trace axis), not from data key names such as `photon_bins`.
- Trace grids may provide reduced mean Line/Heatmap overview modes in addition
  to point Trace mode.
- Selector widgets must only show hidden dimensions that define the current
  slice position, not every dimension in the dataset.
- GUI calls `RunReader`, `DatasetModel`, and `SliceController`; it must not
  hard-code backend-specific parsing.
- CSV must work without optional dependencies.
- Zarr should be preferred by Auto when present and should fail with a clear
  optional dependency error when explicitly requested but unavailable.
- The viewer must never rewrite JSONL audit files, CSV tables, or Zarr arrays.
- Prefer pyqtgraph for large interactive plots, fall back to Matplotlib Qt canvas,
  and keep simple Qt painting only as a dependency fallback.
- Selecting a data key should use metadata-only loading where available, so Zarr
  does not load full arrays before the user requests a slice.
- The Operator Console should embed the reusable viewer panel rather than
  reimplement data browsing controls. After Start completes, it opens the
  completed run path in that panel.
- Storage backend writing is controlled by YAML config (`storage.backends`);
  the viewer backend selector is a read-time choice only.

## MVP Procedure Tree Editor

必须支持显示和基础编辑：

- setup。
- scan。
- average。
- run。
- call。
- cleanup。

每个节点需要显示：

- step type。
- human name。
- key parameters。
- enabled/disabled。

高级拖拽可以延后，但 MVP 必须能从 GUI 修改常用参数并保存回 YAML。

## Instrument Subpanel Rules

1. 子面板配置单个仪器。
2. 子面板可以暴露厂商高级参数。
3. 主流程只引用 capability 方法。
4. 子面板保存参数到 setup profile 或 resource config。

## Design Rules

1. 实验操作界面优先清晰、紧凑、可靠。
2. 不做营销式 landing page。
3. 按钮使用清晰 icon 和 tooltip。
4. 避免嵌套卡片。
5. 移动端不是优先目标，桌面实验控制是优先目标。
