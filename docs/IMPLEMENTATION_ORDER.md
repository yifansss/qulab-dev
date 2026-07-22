# Implementation Order

本文件给 AI worker 提供明确优先级。除非用户明确改变目标，否则按顺序推进。

## P0 Foundation

目标：项目可以作为 Python 包安装、导入、测试。

任务：

1. 创建 `pyproject.toml`。
2. 创建 `src/qulab/__init__.py`。
3. 添加 pytest 基础配置。
4. 添加 README 快速说明。
5. 添加 `.gitignore`。

验收：

```bash
python -m pytest
python -c "import qulab; print(qulab.__version__)"
```

## P1 Core Model

目标：无硬件情况下能表达并执行实验流程。

任务：

1. `core/parameter.py`
2. `core/procedure.py`
3. `core/context.py`
4. `core/events.py`
5. `core/executor.py`

验收：

- 单参数 scan dry-run。
- 二维 scan dry-run。
- average dry-run。
- event stream 正确。

## P2 Config Parser

目标：YAML config 可转成 Procedure。

任务：

1. 定义 config schema。
2. 实现 parser。
3. 实现 `${param}` 参数引用。
4. 输出 resolved config。

验收：

- `configs/experiments/rabi_2d.yaml` 能解析。
- 错误 config 有清楚报错。

## P3 Instrument Capability

目标：用 mock adapter 跑完整流程。

任务：

1. `instruments/base.py`
2. `instruments/capabilities.py`
3. `instruments/registry.py`
4. `instruments/profiles.py`
5. mock adapters for tests。

验收：

- executor 通过 registry 调用 mock microwave/asg/daq。

## P4 Storage

目标：每次运行都有可复现的数据目录。

任务：

1. run directory。
2. metadata writer。
3. event logger。
4. dataset writer。
5. SQLite index，可延后到 P4.2。

验收：

- dry-run 生成完整 run 文件夹。
- events.jsonl 可逐行解析。

## P5 Pycontrol Adapters

目标：包装项目内 vendored `drivers/pycontrol`，并兼容已有外部 pycontrol 路径。

任务：

1. ASG adapter。
2. NI adapter。
3. LMX adapter。
4. AWG adapter。

验收：

- import 不因缺少硬件 SDK 崩溃。
- 默认 mock/dry-run 模式可跑；pycontrol adapter 是 hardware-only，不静默 fallback。
- hardware 模式保留真实错误。

当前状态：

- 已新增 `src/qulab/instruments/adapters/pycontrol.py`，包含 `pycontrol_asg`、`pycontrol_ni`、`pycontrol_lmx`、`pycontrol_awg`。
- 已新增安全 CLI：`PYTHONPATH=src python -m qulab.scripts.hardware_check --config ... --dry-run`。
- 已新增 `configs/setups/real_nv_setup.template.yaml`、`configs/experiments/hardware_odmr.template.yaml` 和双微波 mock 示例 `configs/experiments/dry_run_two_mw_scan.yaml`。
- 后续 worker 可在实验台上扩展 connect-only smoke 为更细的非危险硬件动作；任何输出、ASG/AWG 播放或 NI AO 写入仍必须显式授权。

## P6 Sync and Preflight

目标：运行前发现明显硬件同步问题。

任务：

1. sync plan。
2. trigger map。
3. sample window validator。
4. safety validator。

验收：

- 缺少 trigger target 时阻止运行。
- DAQ sample window 小于 ASG sequence duration 时警告或报错。

## P7 Plotting and MVP GUI

目标：订阅数据事件并实时显示，同时提供最小可用的操作者运行 UI 和 procedure tree editor。

任务：

1. line plot。
2. heatmap。
3. data reducer。
4. GUI/CLI 独立运行。
5. operator run console。
6. basic procedure tree editor。
7. start/stop/pause controls wired to executor。
8. preflight result panel。

验收：

- dry-run ODMR 显示 line plot。
- dry-run Rabi 2D 显示 heatmap。
- 操作者可以用 GUI 选择 dry-run 实验、修改参数、点击 Start 并看到实时事件。
- procedure tree editor 可以显示并编辑 setup、scan、average、run、cleanup。

当前状态：

- 已有 Tkinter Operator Console MVP，可通过 `PYTHONPATH=src python -m qulab.gui.operator_app` 启动。
- 已支持 dry-run ODMR/Rabi 的加载、参数编辑、preflight、后台 Start、事件日志、RunStore run path 和 Canvas line plot。
- 已新增 PySide6/PyQt6 Operator Console，可通过 `PYTHONPATH=src python -m qulab.gui.pyqt_operator_app` 启动；无 Qt 时 import-safe 并给出友好启动提示。
- PyQt/PySide 版本支持 workflow tree inspector、YAML 保存 round-trip、scan/average/call 编辑、enabled、add/duplicate/delete、resource/preflight tables、run log、run path、line plot 和 point table。
- 目前仍是 mock/dry-run only；Stop 不提供可靠取消；专业 heatmap、拖拽排序、完整 step library 和 run browser 待后续 worker 增强。
- 建议后续 plotting worker 在不改变 `qulab.gui.controller.OperatorController` 公共后端的前提下引入 pyqtgraph/matplotlib 或 Qt heatmap。

## P8 Full GUI

目标：把 MVP GUI 扩展为完整轻量实验面板。

任务：

1. main window。
2. setup editor。
3. instrument panels。
4. procedure editor。
5. run monitor。
6. data browser。
7. ASG sequence panel / editor bridge。
8. operator parameters submode。
9. direct control submode。

验收：

- GUI 保存的 config 可被 CLI 运行。
- run browser 可以打开历史实验。

### P8.1 ASG Sequence Panel / Editor Bridge

目标：把已有 standalone sequence editor 接入 Qulab ASG 子面板，同时保持 Qulab 不实现通用 pulse compiler。

任务：

1. 在 ASG 子面板中选择 sequence 文件。
2. 打开项目内 vendored standalone sequence editor：`tools/sequence_editor/sequence_editor.py`。如需临时使用其它 editor，可设置 `QULAB_SEQUENCE_EDITOR_PATH`。
3. 从 sequence 文件读取或刷新可扫描参数、通道映射、trigger 相关信息。
4. 支持将 workflow/operator 参数绑定到 sequence 参数，例如 `tau_s <- ${tau_s}`。
5. 生成 sequence snapshot/hash，写入 metadata 或 point snapshot。
6. 将估算 sequence duration、trigger channel、channel usage 提供给 preflight。
7. 保持 sequence 文件编辑和实验执行分离；打开 editor 不应自动连接或启动硬件。

验收：

- 用户能从 GUI 选择 Rabi/ODMR sequence 文件。
- 用户能从 GUI 打开 standalone sequence editor。
- 修改或选择 sequence 后，GUI 能刷新 sequence path、mtime/hash 和参数列表。
- dry-run metadata 中能记录 sequence 文件和 hash。
- workflow tree 中只保留 `asg.load_sequence`、`asg.set_sequence_param`、`asg.arm`、`asg.start` 等宏观步骤，不展开纳秒级 pulse。

当前状态：

- 已新增 import-safe `sequence_bridge`，可检查 path、exists、mtime、size、sha256、简单 parameter/channel 和 warnings。
- PyQt Operator Console 左侧 ASG sequence 区应只作为 preview；resource `sequence_file` 的选择、编辑和 Open Editor 入口应放在 `Operator Parameters` 或 `Builder Workflow` 设置区域。
- standalone sequence editor 依赖 PyQt5；wrapper 应在启动前检测缺失依赖并返回 friendly message，不能让外部 editor traceback 泄露给用户；可用 `QULAB_SEQUENCE_EDITOR_PYTHON` 指定带 PyQt5 的 Python。
- Qulab launcher 已负责把当前 `sequence_file` 载入 standalone editor 并设为 active file；主面板通过文件 watcher 和 editor stdout JSON 回写刷新 sequence preview。
- RunStore 已复制 resource-level sequence 和每个 workflow `asg.load_sequence` file reference 到 `artifacts/sequences/`，并在 `metadata.json.sequence_snapshots` 记录 source、artifact、hash、mtime、size、params/channels。
- Operator Parameters 已为每个 `asg.load_sequence` occurrence 暴露独立 `sequence_file` file picker；主面板 preview 支持同一 ASG resource 下多 sequence references。
- Preflight view 已暴露 sequence snapshot；duration 估算未知时显示 warning。

### P8.2 Operator Parameters Submode

目标：让实验现场调参不依赖逐层点开 workflow tree。

任务：

1. 在同一主窗口中增加 `Operator Parameters` / `Builder Workflow` / `Direct Control` submode 切换。
2. `Operator Parameters` 显示常用 scan、average、call args、sequence file、storage backend。
3. 支持从 procedure/config 自动提取常用参数。
4. 支持实验模板显式声明 `operator_parameters`，包含 label、unit、range、widget、source。
5. 修改参数表单后同步更新 workflow model 和 YAML。
6. 显示 validation error、单位和安全提示。

验收：

- Rabi 实验可以在一个表单中修改 `tau_start_s`、`tau_stop_s`、`tau_points`、`averages`、`mw_freq_hz`、`mw_power_dbm` 和 `sequence_file`。
- 保存后的 YAML 可由 CLI dry-run。
- Builder workflow tree 仍可用于高级流程编辑，但不是日常调参唯一入口。

当前状态：

- PyQt Operator Console 已提供 `Operator Parameters` / `Builder Workflow` / disabled `Direct Control` submode。
- Operator parameter model 可自动发现 scan、average、call args、ASG `sequence_file` 和 storage backend，并支持显式 `operator_parameters` 声明。
- Operator parameter 自动发现应跳过 legacy `asg.load_sequence args.sequence` 字符串；file-backed `args.sequence_file` / `args.path` / `args.sequence_path` occurrence 应作为独立 file picker 显示，并带 occurrence 编号和 workflow 位置。
- 主窗口应改为 `Control` / `Live Run` / `Data Viewer` 三个 page/tab，减少上下区域挤压；Data Viewer 仍复用现有 viewer 子面板。
- Builder Workflow 的 `ASG Sequence Settings` 只在选中 `asg.load_sequence` step 时显示。
- Sequence Preview 先提供 Qulab-native JSON channel/pulse 文本摘要；图形化预览需要后续抽离 standalone editor model/canvas 并迁移到同一 Qt6/PySide6 theme。
- Direct Control 仍留给 P8.3；当前 placeholder 不暴露任何硬件动作。

### P8.3 Direct Control Submode

目标：提供受安全门控的仪器手动控制，用于实验台调试、状态检查和低风险单步动作。

任务：

1. 在同一主窗口中增加 direct control 工作区。
2. 显示每个 resource 的 connect、health、snapshot 和 simulation/hardware 状态。
3. 按 safety class 暴露动作：`read_only`、`connect`、`configure_no_output`、`output`、`analog_output`、`unknown`。
4. 默认禁用 `output`、`analog_output` 和 `unknown` 动作。
5. ASG 支持查看通道状态、sequence 状态、arm/stop；通道常开和 start 需要显式授权。
6. NI 支持只读状态、counter/AI 配置预览；AO 写入需要显式授权。
7. MW output 和 AWG play 需要显式授权。
8. 所有手动动作都通过 adapter/bench workflow 路径执行并记录日志。

验收：

- 无硬件环境下 GUI import 和默认测试仍通过。
- Direct Control 默认不会打开微波、启动 ASG/AWG 或写 NI AO。
- `connect/read-only/configure-only` 类动作可以规划或模拟。
- 危险动作在 GUI 中有明确授权门槛和日志记录。

## P9 Parameterized Experiment and Sequence Bundle Scan Model

目标：在不推翻现有 workflow tree 的前提下，增加 ASG sequence bundle manifest、resolver、load、preflight、RunStore provenance，以及下一阶段的 Sequence Family / Sweep Generator authoring。P9.1/P9.2 继续由现有 workflow `scan` 节点执行；Phase E 通过 authoring plan 编译出这些 canonical 节点，不增加第二套 executor scan engine。

规划文档：

- `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`

核心原则：

- workflow tree 的 `scan` 仍是唯一执行语义；P9.1/P9.2 直接消费现有 point context。Phase E GUI/compiler 只负责生成 canonical scan，不绕过它。
- Python 只负责慢速配置、arm/start/read 和参数应用；纳秒/微秒时序仍由 ASG/NI/AWG 硬件完成。
- ASG pulse 不在主 workflow tree 中逐个展开，也不作为 Qulab core 的一等扫描对象；pulse detail 属于 sequence editor 或用户 generator。
- Qulab 扫描 concrete sequence bundle entry：`scan point -> resolve bundle entry -> asg.load_sequence(file) -> arm/start/read`。
- sequence bundle manifest 必须记录 coordinate、entry、sequence file、hash/provenance；可选记录 duration、trigger channel、output channel 等 metadata 用于 preflight。

阶段：

1. Phase A（已完成，P9.1）：新增 sequence bundle manifest model 和 `sequence_bundles` 可选 schema，仅 dry-run 解析和验证，不改变旧 config 行为。
2. Phase B（已完成，P9.1）：实现 sequence bundle manifest loader，解析 entry、coordinate、project-relative manifest path、manifest-relative sequence path、hash、三种离线 match 和 coverage report。
3. Phase C（已完成，P9.2）：实现 canonical `resource.load_sequence_from_bundle`，把当前 point coordinate 映射到 concrete sequence file，经现有 `load_sequence` 加载并发出 `SequenceSelected`。
4. Phase D（已完成，P9.2）：preflight 和 RunStore 集成，用 bundle metadata 检查 coverage、ASG trigger channel、DAQ sample window/route，并记录 manifest、逐点 selection 和去重 sequence artifact。
5. Phase E：Sequence Family + Sweep Generator。由结构化 `sequence_plan` 驱动 provider、参数扫描、bundle/manifest 自动生成、workflow 编译、GUI Sequence Sweep 子面板和完整 provenance；生成与 preflight 必须在硬件连接/输出前完成。
6. Phase F：后置的全局 Scan Authoring，统一处理 MW、NI、温控、磁场、sequence 等异构参数的任意嵌套、zip/table/adaptive scan 和 binding 图。Sequence 专用 scan authoring 已纳入 Phase E，不等待 Phase F。

已按顺序完成的两个 worker 小目标：

1. P9.1（Phase A + B）：`prompts/009_followup_p9_1_sequence_bundle_manifest_loader.md`。先完成完全离线的 manifest model、loader、path/hash、entry resolution 和 coverage 基础层。
2. P9.2（Phase C + D）：`prompts/009_followup_p9_2_sequence_bundle_runtime_preflight_runstore.md`。硬依赖 P9.1，再接通 workflow runtime、preflight、SequenceSelected event 和 RunStore provenance。

P9.1、P9.2与P9.3 Phase E已完成mock/dry-run实现，见 `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`。Bench10–12模板已就绪但未物理验证。Phase F保留为更广泛的全局scan authoring。

P9.1 公共入口为 `qulab.sequence_bundles`，P9.2 runtime bridge 为
`qulab.sequence_runtime`。`ParsedExperiment.sequence_bundles` 与
`ExperimentContext.sequence_bundles` 提供同一 registry，executor、preflight 和 RunStore
已经消费这些对象。Phase E Sequence Family / Sweep Generator 已实现；Phase F 全局 Scan Authoring 仍未实现。

Phase E 实现顺序：

1. P9.3A：provider contract、`sequence_plans` schema、sampling、materializer、`sequence_sweep` compiler，以及 headless Rabi example。Worker prompt：`prompts/009_followup_p9_3a_sequence_generation_foundation.md`。
2. P9.3B：通用 ASG template sweep provider，支持 pulse target、duration/start/end/gap transform、following/group shift 和 anchor constraint。Worker prompt：`prompts/009_followup_p9_3b_generic_asg_template_sweep.md`。
3. P9.3C：GUI `Sequence Sweep` submode，动态参数表单、target/link editor、代表点 preview、Prepare/build/preflight 状态。Worker prompt：`prompts/009_followup_p9_3c_sequence_sweep_gui.md`。
4. P9.3D：更多 curated family、旧 sequence 导入迁移和硬件 bench template。Worker prompt：`prompts/009_followup_p9_3d_curated_families_migration_bench.md`。

Phase E 核心验收：用户只修改 GUI/YAML 中的 Rabi `tau_s` 范围即可 Prepare；Qulab 自动生成 concrete files、manifest、bundle 声明和 canonical workflow，并把参数定义、plan/provider/template hash、逐点坐标和选中 sequence 全部记录到 run。

验收：

- 手写 Rabi workflow YAML 可扫描 `tau_s -> rabi_tau sequence bundle coordinate`，P9 核心路径不依赖 GUI 自动生成 scan 节点。
- 能按 point 自动选择并 load 对应 ASG sequence 文件，而无需实验中手工切换 sequence。
- 保存后的 YAML 仍可由 CLI parse/dry-run；旧 YAML 不受影响。
- run metadata 记录参数定义、binding、bundle manifest hash、selected entry id、sequence hash 和 point coordinates。
- 在一个面板中创建/修改 fixed/linspace/range/explicit scan 属于 Phase F 的单独验收，不阻塞 P9.1/P9.2。

## P10 Live Compute and Derived Data Framework

目标：提供实时计算/派生量框架，使用户可以在项目内编写计算模块，并在实验运行中把 raw `DataPoint` 转换为 derived quantities；Live View 可选择显示 raw/derived key，RunStore 可按配置保存 derived outputs 和模块 provenance。

规划文档：

- `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`

核心原则：

- Qulab core 只定义计算模块接口、加载规范、事件流、存储和 GUI 选择逻辑；不写死 ODMR/Rabi/contrast 等具体公式。
- 用户公式放在项目内 `analysis_modules/` 或 import-safe Python module 中。
- raw data 永远优先保存，derived data 作为单独 key/event/artifact 保存，不覆盖 raw data。
- Live compute 必须有开关、show/save 策略和 fail policy。
- 复杂或慢计算不能阻塞硬件采集；初期可做同步轻量 MVP，后续扩展异步队列。

阶段：

1. Phase A / P10.1（已完成）：`analysis.live` / `analysis.modules` schema、ComputeModule 协议、dependency graph 和 import-safe registry。
2. Phase B / P10.2（已完成）：同步 `LiveComputeEngine`、queued EventBus、`DerivedData` / `AnalysisStatus` 和 conditional RunStore storage。
3. Phase C / P10.3（已完成）：raw/derived Live Run catalog、plot/dimension selection、module status 和 P9 sequence context。
4. Phase D / P10.4（已完成）：完整 provenance、immutable recompute CLI/result groups 和 group-aware RunReader/DatasetModel。
5. Phase E / P10.5（已完成）：有界单 worker async queue、serialized thread-safe dispatch、metrics、五种 backpressure 和 drain 策略。
6. Phase F / P10.6（实现完成，Qt 手工验收依赖有 Qt 的实验电脑）：真实 line/overlay/heatmap/trace renderer、稳定 Raw/Derived checkbox、display pause/clear/auto-follow、共享 Data Viewer canvas 与 deterministic showcase。无 Qt 环境执行 headless/integration 测试并跳过 widget test；可见窗口和截图验收不得伪造。

GUI 交叉规划：`docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`。

依赖顺序：P10.1 -> P10.2；P10.3 同时依赖 P10.2 和 P9.3C，不能与 P9.3C 并发修改共享 GUI 文件；P10.4 依赖 P10.1/P10.2，GUI group integration可在P10.3后完成；P10.5依赖P10.1-P10.3。

验收：

- 用户可添加一个项目内计算模块，通过 YAML 加载并在 dry-run/live run 中生成 derived scalar。
- Live View 可以选择 raw 或 derived key 作图。
- RunStore 能保存 derived outputs，并在 metadata 中记录 module name/version/inputs/outputs/args。
- 模块失败时按 `warn|skip|fail` 策略处理，raw data 不丢失。
