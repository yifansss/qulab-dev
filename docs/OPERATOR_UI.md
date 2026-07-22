# Operator UI

> P11 transactional loading, historical read-only replay, schema-driven
> workflow composition, and guided sequence authoring are documented in
> `docs/P11_AUTHORING_DIAGNOSTICS_HISTORY.md`.

本文档描述实际实验设置完成后，操作者每天使用的界面。这个界面是 MVP 的一部分，不是后期附加品。

## 1. 设计目标

操作者应该能在不写代码的情况下完成：

1. 选择实验。
2. 选择当前硬件 setup。
3. 修改常用参数。
4. 检查仪器连接。
5. 检查 procedure tree。
6. 运行 preflight。
7. 开始、暂停、停止实验。
8. 查看实时图和日志。
9. 找到本次实验数据目录。

## 2. 主界面布局

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Qulab Run Console                         Experiment: Rabi   Setup: Main  │
├───────────────┬───────────────────────────────┬────────────────────────────┤
│ Experiment    │ Procedure Tree                │ Instruments / Controls     │
│ ODMR          │ setup                         │ MW    connected   RF on    │
│ Rabi          │  ├─ mw.set_power              │ ASG   connected   armed    │
│ Ramsey        │  ├─ mw.output_on              │ DAQ   connected   ready    │
│ Pulsed ODMR   │  ├─ asg.load_sequence         │ AWG   unused               │
│               │ scan tau_s                    │                            │
│ Parameters    │  ├─ asg.set_sequence_param    │ Preflight                  │
│ tau_start_s   │  └─ average 100               │ ✓ resources                │
│ tau_stop_s    │      └─ run readout           │ ✓ trigger plan             │
│ tau_points    │          ├─ daq.arm           │ ✓ data path                │
│ averages      │          ├─ asg.arm           │                            │
│               │          ├─ asg.start         │ Prepare  Start  Pause Stop │
│               │          └─ daq.read_counts   │                            │
├───────────────┴───────────────────────────────┴────────────────────────────┤
│ Live Plot                                                                   │
│ counts                                                                      │
│  ^                                                                          │
│  |       *                                                                  │
│  |   *       *                                                              │
│  | *           *                                                            │
│  +----------------------------> tau_s                                       │
├────────────────────────────────────────────────────────────────────────────┤
│ Run Log                                                                     │
│ 15:30:12 loaded config rabi.yaml                                            │
│ 15:30:15 connected mw/asg/daq                                               │
│ 15:30:17 running point 18/101 average 42/100                                │
│ Run path: runs/2026-06-26/20260626_153012_rabi                              │
└────────────────────────────────────────────────────────────────────────────┘
```

## 3. 两种用户模式

### 3.1 Operator Mode

面向日常实验操作者。

可做：

- 改常用参数。
- 选择实验模板。
- 选择 setup profile。
- 连接仪器。
- start/pause/stop。
- 看图和日志。

不可做或默认隐藏：

- 编辑底层 adapter。
- 改复杂 sync internals。
- 改危险硬件参数。

### 3.2 Builder Mode

面向高级用户和 AI worker。

可做：

- 编辑 procedure tree。
- 增加 scan/average/run step。
- 修改 call step。
- 编辑 sync plan。
- 打开仪器高级子面板。
- 保存新实验模板。

### 3.3 同一界面内的 Submode 切换

Operator mode 和 builder mode 不需要做成两个独立面板或两个独立应用。推荐在同一个主窗口中，对当前中间工作区和右侧 inspector/control 区做一键切换：

```text
[ Operator Parameters ] [ Sequence Sweep ] [ Builder Workflow ] [ Direct Control ]
```

切换原则：

- 顶部 toolbar 的 Load/Save/Prepare/Start/Stop 保持一致。
- 主内容区应支持 `Control`、`Live Run`、`Data Viewer` 三个 page/tab，避免控制面板、日志和 viewer 在上下分割中互相挤压。
- `Control` page 放实验选择、resource preview、submode 和 preflight。
- 实验选择区不使用固定按钮列表；应从 `configs/experiments/` 动态扫描 YAML/YML，并用 table/list 一行一个实验显示。实验列表、resource table、sequence preview 应在左侧用可拖动 splitter 调整上下空间。
- `Live Run` page 放实验中的 live plot、point/event preview 和 run log。
- `Data Viewer` page 复用已有 viewer 子面板打开已完成 run。
- `Builder Workflow` 显示当前 workflow tree 和 node inspector，用于搭流程。
- `Operator Parameters` 用表单集中显示现场常调参数，用于跑实验前快速修改。
- `Sequence Sweep` 管理 sequence family/template、固定与扫描参数、pulse target/link、preview 和 bundle materialization。
- `Direct Control` 显示仪器手动控制和状态，用于连接、只读查询、低风险配置和受授权的单步控制。
- 四个 submode 都必须修改同一份 config/model；保存后的 YAML 必须仍可由 CLI 执行。

### 3.4 Operator Parameters Submode

现场调参不应该依赖逐层展开 workflow tree。Operator Parameters submode 应把常用参数集中成表单，适合实验前快速检查和修改。

典型 Rabi 参数区：

```text
tau_start_s       [ 20e-9       ]
tau_stop_s        [ 2e-6        ]
tau_points        [ 101         ]
averages          [ 100         ]
mw_freq_hz        [ 2.870e9     ]
mw_power_dbm      [ -10         ]
sequence_file     [ rabi.seq    ] [Open Editor]
storage_backends  [ csv,zarr    ]
```

参数来源可以分两级：

1. 自动提取：从 scan、average、常见 call args、storage config 和 resource config 中发现常用字段。
2. 显式声明：实验模板可用 `operator_parameters` 声明哪些字段显示、单位、范围、widget 类型和对应 config 路径。

示例：

```yaml
operator_parameters:
  - name: tau_start_s
    label: Tau start
    unit: s
    source: procedure.scan[tau_s].values.start
  - name: averages
    label: Averages
    source: procedure.average[avg].count
  - name: sequence_file
    label: ASG sequence
    source: resources.asg.sequence_file
    widget: file_picker
```

要求：

- 修改表单后，workflow tree 和 YAML model 同步更新。
- 表单必须显示单位、范围和 validation error。
- 危险参数默认不放入 operator 参数区，除非模板明确声明并带安全提示。
- 对于扫描参数，表单应支持 start/stop/points、step、explicit values 三类常见输入。
- ASG sequence 的现场设置分两层：`resources.<name>.sequence_file` 表示 resource 默认 sequence；每个 file-backed `asg.load_sequence` occurrence 可用独立 `args.sequence_file`/`args.path`/`args.sequence_path` 覆盖。legacy `args.sequence` 字符串只是旧式 sequence 名称，不自动作为 file picker 出现。
- 多个 `asg.load_sequence` 参数显示时必须带 occurrence 编号和 workflow 位置，例如 `asg.load_sequence #2 file - procedure/0/...`，避免多行看起来同名。
- `file_picker` 类型参数应提供 Open Editor 入口，并在 editor 依赖缺失时显示友好提示，而不是让 standalone editor traceback 泄露给用户。

### 3.5 Guided Sequence Sweep Submode

Sequence Sweep 用于把 P9 bundle runtime 变成现场可用的 sequence scan authoring。详细架构见
`docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`。

推荐布局：

```text
Family / Template
  provider | template file | Open Editor | refresh

Parameters
  name | fixed/linspace/range/explicit | values | unit | points | validation

Targets and Timing Links (generic/advanced)
  parameter | channel/pulse | start/duration/end/gap | propagation/anchor

Preview and Build
  first/current/last timing | point count | plan hash | cache/build | preflight
```

要求：

- 常用 Rabi/Ramsey/Echo family 由 provider 声明有物理意义的参数，现场修改范围不需要编辑 generator source。
- 通用 template mode 可选择一个或多个 channel/pulse property，并选择只改目标、本通道后续、所有通道后续、named group 或 anchor constraint。
- 每个生成点从 immutable base template 重新计算，不能由上一个点递增修改。
- 参数编辑写入顶层 `sequence_plans`；GUI 不要求用户手写 manifest、bundle declaration 或 load action。
- Preview 只生成 first/current/last 等代表点；完整 bundle 只在 Prepare 时 materialize。
- standalone editor 修改 base template 后，旧 plan/cache 失效，targets 重新验证，必须重新 Prepare。
- Prepare 在任何 hardware connect/output 前完成 provider validation、generation、P9.1 loader 和 P9.2 preflight。
- Sequence 参数同步出现在 Operator Parameters、point coords 和 RunStore provenance。

### 3.6 Direct Control Submode

Direct Control submode 用于实验台调试和临时手动控制，例如查看仪器状态、连接设备、配置只读采集、或在明确授权下打开某个 ASG 通道常开。

典型能力：

- 显示每个 resource 的 connection、health、snapshot。
- MW：读取/设置频率和功率；`output_on` 默认禁用，必须显式授权。
- ASG：选择 sequence、查看通道状态、arm/stop；通道常开、start/output 类动作默认需要授权。
- NI：查看 device、PFI、counter/AI/AO 配置；AO 写入默认需要 `allow_ao`。
- AWG：查看 waveform 和 trigger；play/output 类动作默认需要授权。

安全规则：

- 默认只允许 `connect`、`health_check`、`snapshot`、`read_only` 和 `configure_no_output` 动作。
- `output_on`、`asg.start`、`awg.play`、ASG 通道常开、NI AO 写电压等动作必须明确显示风险并要求授权。
- Direct Control 不能绕过 adapter、bench workflow 或 event logging 直接调用底层 driver。
- 所有手动动作都应该记录到 run log 或 bench log，便于复现实验台状态。

## 4. Procedure Tree Editor

树节点类型：

- `setup`
- `scan`
- `average`
- `run`
- `call`
- `cleanup`

节点示例：

```text
scan tau_s: 20 ns -> 2 us, 101 points
  call asg.set_sequence_param(name="tau_s", value=${tau_s})
  average count=100 reducer=mean
    run readout timeout=10s
      call daq.arm()
      call asg.arm()
      call asg.start()
      call daq.read_counts() -> counts
```

MVP 编辑能力：

- 修改 scan start/stop/points。
- 修改 average count。
- 修改 call args。
- 启用/禁用 step。
- 保存 YAML。

后续增强：

- 拖拽重排。
- step library。
- 参数依赖图。
- diff view。

## 5. 仪器子面板

每个仪器有自己的子面板。

ASG 子面板：

- 左侧 resource 区只放 sequence preview：每个 resource 下所有 sequence references 的 path、exists、hash、mtime/size、可检测 params/channels、warnings。
- sequence file 的选择、编辑和 Open Editor 入口放在 `Operator Parameters` 或 `Builder Workflow` 的设置区域。
- 显示通道映射。
- 显示可扫描 sequence params。
- 将 scan/operator 参数绑定到 sequence params。
- 设置 trigger mode。
- 估算 sequence duration，用于 preflight。
- 生成 sequence snapshot/hash，写入 metadata。

ASG sequence editor bridge：

- Qulab 不重新实现完整 pulse editor。
- GUI 应优先复用项目内 vendored standalone sequence editor：`tools/sequence_editor/sequence_editor.py`。如需临时测试其它 editor，可通过 `QULAB_SEQUENCE_EDITOR_PATH` 覆盖。
- sequence 文件属于 ASG 仪器子面板和资源配置；主 workflow tree 只通过 `asg.load_sequence`、`asg.set_sequence_param`、`asg.arm`、`asg.start` 等步骤引用它。
- 如果 sequence editor 独立进程或独立窗口打开，Qulab 仍需在返回后刷新 sequence 文件路径、mtime、hash 和可扫描参数列表。
- standalone sequence editor 当前依赖 PyQt5；Qulab wrapper 在启动前应检测依赖，缺失时返回 friendly message，不能把 `ModuleNotFoundError: PyQt5` traceback 当作正常 GUI 体验。
- 如果 PyQt5 安装在另一个 Python 环境中，可用 `QULAB_SEQUENCE_EDITOR_PYTHON=/path/to/python` 指定启动 editor 的解释器。
- Qulab 通过自己的 launcher 打开 standalone editor：launcher 会把当前 `sequence_file` 载入 editor 并设置为 active file，使 editor 内部 Save 能写回同一路径。
- Qulab 应监听当前 sequence 文件变化并刷新 preview；editor 退出时如果 stdout 返回 JSON sequence，也应写回当前 `sequence_file` 并刷新主面板。
- 一次实验可多次使用 `asg.load_sequence`。Operator Parameters 应为每个 workflow occurrence 暴露独立 file picker；主面板 preview 和 run metadata 应显示/保存所有 sequence references，而不是假定只有一个固定导入文件。
- Builder Workflow 右侧的 `ASG Sequence Settings` 只在选中 `asg.load_sequence` step 时显示；普通 scan/average/call 不应显示这个设置区。
- 主面板 preview 不嵌入外部 PyQt5 editor widget；当前先用 Qulab 自己的解析器显示 JSON sequence 的 channel/pulse 摘要。后续如需图形波形预览，应把 sequence editor 的 model/canvas 抽成可复用 Qt6/PySide6 组件。

UI 统一规划：

1. 短期：Qulab 主面板和 Data Viewer 使用同一个 Qt stylesheet，风格参考 standalone sequence editor 的 classic white/gray theme；外部 editor 仍单独进程运行，但由 launcher 做文件、错误和主题参数桥接。
2. 中期：从 standalone editor 抽出纯 sequence model、JSON IO 和 preview canvas adapter，Qulab 主面板可复用 preview，不直接嵌完整编辑器。
3. 长期：把 sequence editor 迁移到 PySide6/Qt6 或 qtpy 兼容层，成为 Qulab 同一设计系统下的子面板；旧 PyQt5 editor 作为兼容启动器保留一段时间。

PySide/PyQt 说明：

- PySide6 和 PyQt6 都是 Qt6 的 Python binding，Qt stylesheet 大部分兼容；当前视觉差异主要来自 Qulab 自己的 stylesheet 和控件布局，不是 PySide/PyQt 本身。
- Qulab main panel 和 Data Viewer 通过同一个 `qt_compat` 选择 binding。默认优先 `PySide6`，可用 `QULAB_QT_API=PySide6` 或 `QULAB_QT_API=PyQt6` 强制统一。
- 现有 standalone sequence editor 写死 PyQt5，短期作为外部进程通过 launcher 调用；它不能和 PySide6 主窗口原生嵌成同一个 widget，除非后续迁移到 Qt6/qtpy。

NI 子面板：

- device name。
- counter source。
- PFI trigger。
- sample rate。
- samples。
- AI/AO channel。

MW 子面板：

- frequency。
- power。
- output on/off。
- reference clock。

AWG 子面板：

- waveform list。
- sequence mode。
- trigger source。

## 6. UI 和底层框架关系

GUI 只生成和编辑 config：

```text
GUI edits -> YAML config -> parser -> procedure graph -> executor
```

GUI 运行实验时：

```text
Start button -> executor.start()
Executor events -> GUI run log + live plot + storage
```

GUI 不允许绕过 executor 直接调用硬件。

## 7. MVP 验收

MVP UI 完成标准：

1. 可以加载 dry-run ODMR 和 Rabi。
2. 可以显示 procedure tree。
3. 可以修改 scan 范围和 average count。
4. 可以运行 preflight。
5. 可以 start/stop dry-run。
6. 可以看到实时 line plot 或 heatmap。
7. 可以看到 run path 和 events log。

后续 GUI 验收应增加：

1. `Direct Control` 能显示仪器状态并执行安全分级动作，危险动作默认禁用。
2. GUI 保存的 config 仍可由 CLI dry-run 执行。

## 8. 当前 Tkinter MVP

当前实现提供一个无额外 GUI 依赖的 Tkinter Operator Console：

```bash
PYTHONPATH=src python -m qulab.gui.operator_app
```

默认加载 `configs/experiments/dry_run_rabi.yaml`，也可在界面中切换到
`configs/experiments/dry_run_odmr.yaml` 或手动选择 YAML。

已实现能力：

- 显示 `setup`、`procedure`、`cleanup` 分组下的 `scan`、`measurement`、`average`、`run`、`call` 树节点。
- 编辑常用扫描参数：`start`、`stop`、`points`、显式 values，以及 `average count`。
- Prepare 时通过 `qulab.config.parse_experiment_config(...)` 构造 mock resources，并运行 `SyncValidator`。
- Start 时使用 `EventBus`、`RunStore` 和 `ExperimentExecutor` 执行 dry-run，实时显示事件日志和简单 line plot。
- 显示 resource adapter、capabilities、connected、simulation 状态，以及最终 run path。

当前限制：

- 只支持 mock/dry-run，不连接真实硬件，不导入 pycontrol、NI、ASG SDK、pyvisa 或 serial。
- Stop 是 MVP 占位行为：会阻止重复 start 并在日志中说明当前 executor 不支持可靠中途取消。
- Live Plot 使用 Tk Canvas 画一维折线；二维 heatmap、run browser 和更完整 procedure 编辑留给后续 GUI/plotting worker。
- 后续可在保持 `OperatorController` 后端不变的情况下迁移到 PyQt + pyqtgraph。

## 9. 当前 PyQt/PySide Operator Console

当前新增一个更接近实验操作台的 PyQt/PySide GUI，推荐入口：

```bash
PYTHONPATH=src python -m qulab.gui.pyqt_operator_app
```

启动时优先使用 `PySide6`，如果不可用则尝试 `PyQt6`。如果两者都没有安装，模块 import 不会失败，启动命令会输出清楚提示；默认测试不依赖 Qt 或 display server。

已实现能力：

- 加载 `dry_run_rabi.yaml`、`dry_run_odmr.yaml`、`dry_run_two_mw_scan.yaml`。
- 白色/浅灰主色，少量蓝色 accent，三栏实验操作台布局。
- 同一主窗口内提供 `Operator Parameters`、`Sequence Sweep`、`Builder Workflow`、`Direct Control` submode；`Direct Control` 当前为 P8.3 disabled placeholder。
- `Operator Parameters` 自动发现 scan values、average count、常见 call args、ASG `sequence_file` 和 storage backend，并支持顶层 `operator_parameters` 显式声明。
- 左侧 ASG sequence 区只显示 preview；`sequence_file` 选择和 Open Editor 入口位于 `Operator Parameters` 和 `Builder Workflow` 设置区。
- Workflow tree 显示 `setup`、`procedure`、`cleanup`，以及 `scan`、`measurement`、`average`、`run`、`call`。
- Inspector 可编辑 scan name、linspace/range/explicit values。
- Inspector 可编辑 average name/count。
- Inspector 可编辑 call string、args table、`${param}` 引用和 `save_as`。
- Inspector 可编辑 measurement/run name，run `timeout_s`，以及 common `enabled` checkbox。
- Workflow MVP 操作：新增、复制、删除 `scan`、`average`、`call` step。
- Save YAML 后可重新 `parse_experiment_config`，并可 dry-run。
- Prepare 显示 resource table 和 preflight issue table。
- Start 在后台线程执行 dry-run，通过 `EventBus + RunStore` 更新 run log、run path、line plot 和 point table。
- `Sequence Sweep` 是唯一的九阶段 guided authoring 入口：Resource & Mode、Source、Channel Roles、Fixed Parameters、Sweep Parameters、Targets & Propagation、Preview & Compare、Validate & Prepare、Provenance。
- Curated、Generic Template Sweep 与 Standalone Editor 共用同一 canonical `sequence_plans` 配置。参数控件来自 provider descriptor；fixed/linspace/range/explicit、sampling order、pulse target、propagation 与 anchor constraint 均不要求手写 JSON。
- First/Current/Last 及 first/last Overlay/Difference 使用真实 pulse timeline；问题表显示 severity/code/location/hint，并可跳转到负责阶段。
- Standalone Editor 在后台运行并消费 versioned protocol；只有 hash 校验成功的 saved artifact 会被接受。Prepare 同样在后台运行，并以 authoring revision 防止过期结果覆盖新编辑。
- 成功 Prepare 后可查看 plan/bundle/manifest/provider/template hash、compiled workflow 和预期 RunStore provenance；任何编辑都会把旧结果标为 stale。
- Controller提供plan CRUD、parameter/target/constraint更新、target fingerprint、estimate、preview和compiled workflow preview。修改会使prepared结果stale并禁止静默复用。
- `Operator Parameters` 同步发现sequence plan的fixed/range/explicit字段；保存仍只写authoring YAML。

当前限制：

- 仍然只支持 mock/dry-run，不连接真实硬件。
- Stop 仍是诚实占位：记录请求并阻止重复 Start，不承诺可靠中途取消。
- P10.6 Live Run 已提供真实 line、multi-series overlay、heatmap、vector/matrix trace 和诊断 table；Raw/Derived checkbox 只影响显示，不改变模块 `save` policy。
- Workflow editor 还没有拖拽排序、完整 step library、复杂 schema validation 或 run browser。
- 还没有完整的 `Direct Control` submode；真实硬件手动控制需要先接入 bench safety workflow。
- ASG sequence bridge 当前只做 resource `sequence_file` 编辑、外部 editor 启动和 metadata/hash 预览；不实现 pulse compiler，也不连接或启动真实硬件。
- Live Run 已接入 raw/derived catalog、saved/live-only/waiting/error 状态、line/heatmap/trace selection model、module queue/latency 状态和只读 sequence context；公式仍只存在于 analysis modules。
- Guided Sequence 的 preview/validate 不连接硬件，只有显式 Prepare 才 materialize bundle；物理 trigger cable/output safety 仍必须在实验台确认。Windows 125% scaling 与真实 standalone editor 生命周期仍需按 manual acceptance 表做现场复核。

Live View renderer 按 pyqtgraph、Matplotlib、原生 Qt 的顺序 fallback，并与 Data Viewer 共用入口。Pause/clear 只暂停重绘或清空有界显示 buffer，采集与 RunStore 不受影响。无显式 trace 轴时使用 `sample_index`。硬件实验台启动前可先运行 `configs/experiments/live_view_showcase.yaml`，详见 `docs/LIVE_VIEW.md`。

P9/P10 GUI 汇合规划见 `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`：

- `Control / Sequence Sweep` 负责 Curated Family、Template Sweep、Generic Sweep 的编辑、preview、materialization 和 preflight。
- `Live Run` 只读显示当前 sequence plan/bundle/entry/hash/coords，并提供 raw/derived key、plot/dimension selector 和 compute module status。
- `Data Viewer` 读取已保存 raw、live-derived 和版本化 post-run recompute groups；live-only derived 不应出现在 completed run catalog。
- P10.3 必须在 P9.3C 完成后接入共享 controller/Qt views，不能创建第二套 Sequence Sweep panel。

Async live compute 的 lag/drop 只表示 derived 结果滞后或被策略跳过，不表示 raw 数据丢失。线程 backend 无法强杀卡死的任意 Python 模块；drain timeout 后会标记 hung 并停止接受其迟到事件，建议对不可信或可能长期阻塞的算法使用 post-run recompute。
