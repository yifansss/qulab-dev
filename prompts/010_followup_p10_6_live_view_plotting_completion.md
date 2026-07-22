# Prompt 010-followup P10.6: Live View Raw/Derived Plotting Completion Worker

下面这份 prompt 可直接交给新的 GUI/plotting worker。目标不是重新设计 P10 Live Compute，也不是重写已经存在的 P10.3 headless 模型，而是补齐当前 Operator Console `Live Run` 页的实际绘图、选择、刷新和可用性，使 Raw 与 Derived 数据在真实长时间实验中可以按需勾选并立即观察。

---

## /goal

完成 P10.6：将已经存在的 Live Data Catalog、Live Point Buffer、Live Plot Selection 和 Analysis Status/Sequence Context 模型接入真正可用的 Qt Live View。

完成后，operator 必须能够：

- 在运行开始前看到声明过的 Raw 与 Derived keys；
- 通过 checkbox 独立选择要显示的 Raw/Derived 量；
- 在运行中看到选中量实时更新，而未选中量不占用绘图区域；
- 对一维 scalar scan 显示 line；
- 对二维 scalar scan 显示真正的 heatmap，而不是仅显示 point table；
- 对 vector/trace/matrix 显示选定 point 和 channel 的 trace；
- 对兼容 scalar keys 做 overlay，并有图例；
- 对不兼容、尚未产生、出错或不可绘制的数据看到明确状态，而不是空白或异常退出；
- 暂停/恢复显示、清空显示缓存、自动跟随最新 point，且这些操作不影响 acquisition 和 RunStore；
- run 完成后保留最后画面，并可把同一 run 打开到 Data Viewer。

P10.6 的验收标准是“界面真实可操作且真实绘图”，不能只提交 headless model、table、下拉框、mock screenshot 或文档声明。

---

## 当前事实与缺口

开始前必须用当前代码重新确认，不能只相信旧 handoff。当前已知基线如下：

- `src/qulab/gui/live_data_catalog.py` 已有 `LiveDataCatalog` 与 `LivePointBuffer`；
- `src/qulab/gui/live_plot_model.py` 已有 line/heatmap/trace selection 和数据提取合同；
- `src/qulab/gui/controller.py` 已有 live state、event ingestion 和 `get_live_plot_data()`；
- `src/qulab/gui/pyqt_views.py` 的 Live Run source table 目前没有 checkbox；
- `line/heatmap/trace/table` 控件目前没有完整驱动真实 renderer；
- Live Run 中央区仍主要使用单一手写 `LinePlotWidget`；
- `_drain_events()` 仍直接把 event 交给旧 line preview；
- heatmap 当前至多是 point table MVP，不是实际二维色图；
- `src/qulab/viewer/pyqt_viewer_app.py` 已有 pyqtgraph、Matplotlib、native Qt 的 line/heatmap renderer fallback，可抽取共享组件，禁止复制三套相似实现；
- 现有测试主要验证 headless extraction 和 import safety，没有证明 GUI checkbox、plot mode、事件刷新和非空绘图真正工作。

Worker 必须在最终报告中列出自己确认到的实际基线；若代码已经变化，以当前代码为准，但不得降低本 prompt 的验收要求。

---

## 开始前必须阅读

1. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
2. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
3. `docs/OPERATOR_UI.md`
4. `docs/DATA_VIEWER_REQUIREMENTS.md`
5. `docs/DATA_MODEL.md`
6. `docs/IMPLEMENTATION_ORDER.md`
7. `prompts/010_followup_p10_3_live_view_gui_sequence_integration.md`
8. `prompts/010_followup_p10_2_live_compute_engine_storage.md`
9. `prompts/010_followup_p10_5_async_compute_backpressure.md`
10. `workers/gui_worker.md`
11. `workers/plotting_worker.md`
12. `workers/qa_worker.md`
13. `src/qulab/gui/pyqt_views.py`
14. `src/qulab/gui/controller.py`
15. `src/qulab/gui/live_data_catalog.py`
16. `src/qulab/gui/live_plot_model.py`
17. `src/qulab/gui/analysis_status_model.py`
18. `src/qulab/gui/sequence_context_model.py`
19. `src/qulab/gui/qt_compat.py`
20. `src/qulab/viewer/pyqt_viewer_app.py`
21. `src/qulab/storage/slicing.py`
22. `src/qulab/core/events.py` 或当前实际 event 定义文件
23. 现有 live compute、dataset slicing、viewer 和 Qt tests

开始时运行：

```bash
git status --short --branch
python -m pytest -q
```

如果工作树有其他 worker 或用户的改动，不回退、不覆盖、不整理与本任务无关的文件。`drivers/pycontrol` 是独立驱动来源，不属于本任务，不得修改或纳入主仓库。

---

## 严格范围

### 必须实现

- Raw/Derived 分组的 checkable source selector；
- selection state 与 catalog refresh 解耦，刷新不能丢失用户选择；
- line、heatmap、trace、table 四种实际 view；
- compatible scalar overlay；
- dimension、hidden selector、point、channel 控件；
- waiting/active/error/unavailable 与 saved/live-only 可视状态；
- bounded、throttled live repaint；
- display pause、clear display、auto-follow；
- run lifecycle、empty state、final state；
- Qt 主线程安全；
- headless、Qt widget、controller integration tests；
- 一个无需硬件的 deterministic Live View showcase；
- 相应 docs 与 handoff/status 更新。

### 不实现

- 不编写具体实验公式或 fit 算法；
- 不改变 analysis module API 和 DerivedData 基本语义，除非发现明确 bug，且必须保持兼容；
- 不改变 Raw 数据持久化策略；
- 不修改 sequence generation、bundle、ASG 或 NI driver；
- 不在 Live Run 中编辑 prepared sequence；
- 不重写整个 Operator Console；
- 不新增第二个主窗口或第二套 Live View；
- 不从 key 名称猜测 `counts`、`trace` 或 raw/derived 类型；
- 不让 display pause 停止事件接收、分析计算或数据存储；
- 不为实现 GUI 而轮询/反复重读正在写入的 run folder。

---

## 建议实现边界

优先将可复用绘图部件从 Data Viewer 抽成共享模块，例如：

```text
src/qulab/gui/plot_canvas.py              # Qt renderer adapter，或项目中更合适的位置
src/qulab/gui/live_run_view.py            # 如拆分能明显降低 pyqt_views 复杂度
src/qulab/gui/live_plot_presenter.py       # 可选，Qt-free presentation state
src/qulab/gui/pyqt_views.py                # 页面组装与 signal wiring
src/qulab/gui/live_plot_model.py           # 仅扩展必要的数据合同
src/qulab/gui/live_data_catalog.py         # 仅修正明确的类型/axis/buffer缺口
src/qulab/viewer/pyqt_viewer_app.py        # 改为复用共享 canvas
```

不要让 headless model import Qt。不要让 canvas 读取 YAML、RunStore 或 event。推荐的数据流为：

```text
EventBus callback
    -> OperatorController.handle_live_event(event)
    -> bounded live models/buffer
    -> GUI queue/coalescer
    -> main-thread presenter refresh
    -> shared plot canvas + table
```

如果保留现有文件结构更符合代码库，也可以不强制拆文件，但 Data Viewer 与 Live View 不得继续维护彼此漂移的 renderer 逻辑。

---

## Source Selector 合同

Live Run 左侧使用紧凑、可扫描的 source tree/table。至少包含：

```text
Show | Key | Source | Kind | Unit | State | Storage
```

要求：

1. Raw 与 Derived 必须有清楚分组或可筛选的 source 列，不能混成无法辨认的一列。
2. `Show` 必须是真 checkbox，不用 selection highlight 代替。
3. declared raw/derived 在首个 event 前就显示；derived 初始状态通常为 `waiting`。
4. `saved` 与 `live-only` 明确展示；勾选只影响显示，不修改 save policy。
5. `active`、`waiting`、`error`、`unavailable` 有简洁状态标识和 tooltip。
6. catalog 新增 key 时保留已有 checkbox、plot type、dims、selectors；新 key 不得抢走当前选择。
7. `visible_default/show` 只在首次初始化时应用一次。用户取消勾选后，后续 event 不得自动重新勾选。
8. 使用稳定 identity，至少为 `(source_kind, key)`；如现有 schema 保证 raw/derived key 全局不冲突，也要保留 collision error 行为。
9. 支持按 source/key 搜索或过滤；当 keys 较多时仍能快速找到目标。
10. 长 key、module、unit 使用 elide 与 tooltip，不让列宽无限膨胀。

对于 `waiting` key，可以允许预先勾选并显示 waiting empty state；不能因尚无首个值而崩溃或静默取消。

---

## Plot Workspace 与选择规则

### 自动模式

增加 `Auto` plot mode，并允许显式选择 `Line / Heatmap / Trace / Table`：

- scalar + 0 或 1 个 scan dim -> scalar monitor/line；
- scalar + 至少 2 个 scan dims -> heatmap；
- vector/trace -> trace；
- matrix with channel/time semantics -> selected channel trace；
- unknown/object/string/table-like -> table；
- 显式 mode 与数据不兼容时显示解释，不抛到 event loop。

不能根据 key 名称猜类型。必须依据 catalog spec、event data shape、dims 与 units。

### 多 key 勾选

- 相同 x dimension、相同或兼容 unit 的 scalar keys 可以 overlay；
- overlay 每条曲线颜色稳定，有图例，Raw/Derived 可同时显示；
- units 不兼容或 dims 不兼容时不能偷偷画在同一 y axis；
- 推荐把不兼容选择按 `line/heatmap/trace/table + dims/unit` 分成多个 plot tabs 或平铺 panes；
- 如本阶段只实现一个 active plot pane，必须阻止不兼容组合、保留 checkbox 状态，并在 plot status 中准确说明哪些 key 未显示及原因；不能静默只画第一项；
- heatmap 一次至少支持一个 active key。多个 heatmap 可用 tabs，不允许覆盖在同一 image；
- trace keys 可以用 tabs；只有 shape、time axis 与 unit 兼容时才允许 overlay。

Plot panes/tabs 必须有稳定尺寸，切换 key 或出现 legend 时不能让布局明显跳动。不要做嵌套装饰 cards。

### 一维 line

- 使用真实 selected key 数据，不使用旧 `PlotSeries` 的“首个数值字段”猜测；
- x 轴来自用户选择的 scan dimension；没有 scan dim 时允许使用 point order/index；
- event 乱序时按 x 或明确 acquisition order 展示，并在合同/tests 中固定；
- 缺失 derived point 使用 gap/NaN，不错误连接成已测值；
- axis title 显示 dim/key 与 unit；
- 支持 autoscale，至少提供 reset view；
- overlay legend 可辨认 raw 与 derived。

### 二维 heatmap

- 必须显示真实色图和 color scale/colorbar；point table 只能作为辅助视图；
- x/y dimension 可交换；
- 未采集 grid cell 为 NaN/empty color；不能默认显示为 0；
- 非规则但可枚举坐标按 coordinate arrays 排序/映射；
- 重复 point 的更新策略明确，默认使用该 point 最新值；
- >2D 数据显示剩余 dimension selectors；selector 改变后立即重切片；
- axis label 使用实际 coordinate 和 unit，不只显示 index；
- 单行/单列/incomplete grid 也要可见且不除零；
- color range 初始 autoscale；后续可以保持视图稳定，但必须有 reset/autoscale 操作。

### trace/vector/matrix

- vector 显示一条 trace；
- matrix 默认按 `channel x time_s` 解释，提供 channel selector；
- point selector 支持 latest、auto-follow 和选择历史 point；
- 有显式 time coordinate 时使用真实 time values；没有时必须标为 sample index，不能虚构 `time_s`；
- 当前 NI/PSE 常见 payload 可能是单通道二维数组（例如 `[[sample0, ...]]`），必须识别为 matrix 并默认显示 channel 0；
- 空 trace、ragged list、非数值样本必须显示 unsupported/error 状态，不得使 GUI 崩溃；
- channel 数在运行中变化时安全刷新 selector，并保留仍有效的选择。

### table 与诊断

Table 至少显示：

```text
point_id | coordinates | key | source | value/shape | state
```

大数组只显示 shape、dtype 和短 preview，不把全部 samples 填进单元格。Table 是诊断/不可绘制数据视图，不得替代要求中的 line/heatmap/trace。

---

## 数据合同必须补齐的边界情况

Worker 必须先写 tests 暴露缺口，再做最小兼容扩展：

1. Raw `DataPoint` 与 later `DerivedData` 使用相同 `point_id/coords` 合并到同一 point。
2. derived 缺点不会造成 line/heatmap shape 错位。
3. 重复 point update 使用最新值，且不会重复无限增加 grid cell。
4. bounded buffer eviction 不影响 RunStore；UI 清空也不影响 RunStore。
5. vector、NumPy array、matrix、tuple 等受支持的数值 payload 分类一致。
6. bool/string/object 不能误当数值 scalar 绘图。
7. explicit axis metadata 如果当前 event/schema 已提供，必须被保留并用于 trace；若 schema 尚未提供，不在此任务私自创造硬件特定字段，可采用 sample index 并在文档说明。
8. units 缺失时为 `None`/空，不猜单位。
9. heatmap coordinate order 必须 deterministic；数值坐标优先自然升序。
10. malformed data 只使对应 source/pane 进入 error，不中断 run、其他 plots 或 storage。

如现有 `LivePointBuffer.trace()` 永远返回 `time_s=np.arange(...)`，必须修正 label/axis semantics，至少区分 `time_s` 与 `sample_index`。

---

## Renderer 要求

复用 Data Viewer 已有 backend preference：

1. 首选 `pyqtgraph`，用于高频 line/trace 和 heatmap；
2. pyqtgraph 不可用时使用 Matplotlib Qt canvas；
3. 二者都不可用时使用 native Qt fallback；
4. optional backend import 失败不能阻止 `qulab.gui` headless import；
5. 三种 backend 至少都支持非空 line 和非空 heatmap；
6. renderer API 至少能表达 message、one/multiple lines、heatmap、clear/reset；
7. Data Viewer 改为复用同一 renderer 时，不得破坏已有 slicing/viewer tests。

建议共享接口：

```python
class ScientificPlotCanvas:
    def set_message(self, message: str) -> None: ...
    def set_lines(self, series: Sequence[LineSeriesView]) -> None: ...
    def set_heatmap(self, view: HeatmapView) -> None: ...
    def clear(self) -> None: ...
    def reset_view(self) -> None: ...
```

不要要求所有 backend 像素完全一致，但语义、axis labels、missing values 和错误状态必须一致。

---

## 刷新、性能与线程安全

实验可能持续数小时并产生大量 events。必须满足：

- worker thread 只写 controller/model 与 GUI event queue，不直接访问 QWidget；
- QWidget 更新仅在 Qt main thread；
- event ingestion 与 repaint 分离；
- repaint 采用定时 coalescing/throttle，目标 5-15 FPS，可配置但不必每个 event 重画；
- 单次 timer tick 有处理预算，持续 burst 不得让 Stop、tab 切换和窗口拖动完全失去响应；
- table 行数与 display buffer 有上限；
- `Pause display` 停止 repaint/auto-follow，但继续 ingest、compute、store；恢复后一次性刷新到最新 state；
- `Clear display` 清除 live display buffer/plot，并明确不删除 run 文件；
- `Auto-follow latest` 只影响 point/channel view selection；用户手动选择旧 point 后可自动关闭或暂停 follow；
- run end 时立即执行最终 refresh，保留最终画面和状态；
- 新 run 开始时 reset display data，但可以按稳定 key 恢复用户 checkbox preference；不存在的 key 不制造 phantom row。

避免在每个 event 上清空并重建整个 source table、dimension combos 和 status table。使用 diff/update 或仅在 catalog/status 变化时刷新结构。

---

## Live Run UI 最低布局

保持现有 `Control / Live Run / Data Viewer` 主职责，不把 Sequence authoring 移入 Live Run。

推荐紧凑布局：

```text
┌ Sources ──────────┬──────────── Plot workspace ────────────┬ Context ───────┐
│ Filter             │ [Auto|Line|Heatmap|Trace|Table]        │ Analysis        │
│ Raw                │ x [tau]  y [mw_freq]  selectors [...] │ module/status   │
│ [x] counts         │                                        │                 │
│ [ ] ai_trace       │            actual plots               │ Sequence        │
│ Derived            │                                        │ plan/entry/hash │
│ [x] contrast       │                                        │                 │
│ [ ] fit (waiting)  │                                        │                 │
├────────────────────┴────────────────────────────────────────┴─────────────────┤
│ Pause display | Auto-follow | Clear | Reset view | point/channel | status     │
│ compact event/value table                                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ Run log                                                                        │
└────────────────────────────────────────────────────────────────────────────────┘
```

要求：

- 常用 workflow 不需要不断横向滚动；
- 控件只在相关 mode 出现/启用；
- buttons 使用现有 icon 库时优先用 icon，并有 tooltip；
- binary state 使用 checkbox/toggle；
- 不在页面加入大段“如何使用”文字；状态与错误使用短标签和 tooltip；
- 不使用 oversized heading、marketing card 或装饰性背景；
- 1280x800 和 1920x1080 下文本不重叠；
- 1366x768 下主要 plot 仍有可用面积；
- Windows 缩放 125% 时关键 controls 不被裁掉。

---

## Controller / View API

GUI 不得直接拿 controller 内部锁或修改 model 私有字段。补充稳定 API，例如：

```python
controller.list_live_data_specs()
controller.get_live_selection()
controller.set_live_selection(...)
controller.get_live_plot_data(...)
controller.list_live_points()
controller.clear_live_display()
```

具体名称可按现有风格调整，但必须：

- 返回 snapshot/copy，不把 mutable internal state 暴露给 QWidget；
- 在 live event 并发进入时线程安全；
- selection validation error 是可展示的 domain error，不是 GUI crash；
- controller/headless API 可独立测试，不依赖 QApplication；
- view 不重复实现 `LivePlotModel` 的 compatibility rules。

---

## Deterministic Showcase

增加一个无需硬件、可重复的 Live View showcase。优先使用现有 experiment config + mock resources + example analysis module；必要时增加小型 example script，但不能绕过 controller/event path 直接操作 canvas。

一次 showcase 必须覆盖：

- 一维 raw scalar；
- 一维 derived scalar，与 raw 可兼容 overlay；
- 二维 raw 或 derived scalar heatmap，包含至少一个暂缺 cell 的中间状态；
- vector trace；
- 单通道 matrix trace；
- declared-but-waiting derived key；
- saved 与 live-only key；
- AnalysisStatus 与 Sequence Context 不退化。

提供清晰启动命令。路径必须 project-relative / package-relative，不允许写开发者机器绝对路径。

Windows PowerShell 示例使用：

```powershell
$env:PYTHONPATH="src"
python -m qulab.gui.pyqt_operator_app
```

不要写 POSIX 风格的 `PYTHONPATH=src command` 作为 Windows 命令。

---

## 必须新增或扩展的测试

### Headless unit tests

至少覆盖：

1. raw + delayed derived point merge；
2. selection persistence across catalog updates；
3. visible defaults only applied once；
4. compatible raw/derived scalar overlay；
5. incompatible dims/units 的明确 validation；
6. incomplete 2D grid -> NaN cells；
7. deterministic coordinate ordering；
8. vector trace + matrix channel extraction；
9. sample index 与 explicit time axis label；
10. waiting/error/unknown keys；
11. malformed payload isolation；
12. bounded buffer、clear display 与 storage independence；
13. duplicate point update policy；
14. empty/single-point/single-row heatmap。

### Qt widget tests

Qt unavailable 时可以 skip，但有 Qt 时必须实际创建 `QApplication` 和 Live Run widget，至少覆盖：

1. Raw/Derived rows 和 checkbox 存在；
2. 点击 checkbox 后 controller selection 改变；
3. catalog refresh 后 checkbox 保持；
4. line event 后 canvas 进入 line mode 且 series 非空；
5. 2D events 后 canvas 进入 heatmap mode 且 matrix 非空；
6. trace point/channel selector 改变后显示对应 trace；
7. derived event arriving later 使 waiting -> active 并更新 plot；
8. Pause display 时 model 继续 ingest，resume 后追到最新；
9. Clear display 不删除 run path/RunStore data；
10. incompatible selection 显示可读状态且 event loop 不抛异常；
11. run completion 后 final refresh 并能 open Data Viewer；
12. 所有 QWidget 更新发生于 main thread。

测试必须验证 rendered model/canvas state，不只断言控件可以 import。对于 native Qt fallback，增加 widget grab 或 paint target 的非白像素 smoke assertion，证明 line 与 heatmap 不是空白；避免脆弱的整图像素快照。

### Integration tests

至少覆盖：

- mock run 同时发出 DataPoint、DerivedData、AnalysisStatus、SequenceSelected/当前等价事件；
- selected raw + derived 在运行中持续更新；
- run folder 中 raw 和 configured saved derived 仍可由 RunReader/Data Viewer 读取；
- live-only derived 可显示但不写入 dataset；
- display pause/clear 不改变最终持久化数据；
- burst event 输入经过 coalescing 后不会为每个 event 执行一次完整结构重建。

不要把硬件接入作为自动测试前提。

---

## 手工验收矩阵

Worker 必须在有 Qt 的环境完成并记录：

| 场景 | 操作 | 预期 |
|---|---|---|
| waiting derived | run 前勾选 derived | 显示 waiting，不报错 |
| raw line | 勾选一维 raw | 折线逐点更新，轴名正确 |
| raw + derived | 勾选兼容两项 | 两条线和 legend 同时出现 |
| 2D heatmap | 选择 x/y | 色图逐 cell 更新，未测 cell 为空 |
| trace | 选择 vector key/latest point | 显示最新 trace |
| matrix trace | 切换 channel | 曲线切换到指定 channel |
| old point | 关闭 auto-follow，选历史 point | 新 event 不抢走选择 |
| pause | 点击 Pause display | 存储继续，画面暂停 |
| resume | 恢复显示 | 一次刷新到最新数据 |
| clear | 点击 Clear display | plot/table 清空，run 文件保留 |
| malformed key | 注入 unsupported payload | 该 key 显示错误，其它 plot 继续 |
| completed run | run 结束 | 最终图保留，Data Viewer 可打开同一 run |

至少保存一张 line + derived overlay 和一张中途 incomplete heatmap 的 Qt 截图到测试/worker handoff 指定的非源码 artifact 目录；不要提交大型二进制截图到 git，除非项目规范明确要求。

---

## 文档更新

至少更新：

- `docs/OPERATOR_UI.md`
- `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
- `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
- `docs/IMPLEMENTATION_ORDER.md`
- worker handoff/status 文件（按仓库当前规范）

文档必须准确区分：

- P10.3 已完成的 catalog/model/controller/sequence-context 基础；
- P10.6 新完成的真实 renderer、checkbox wiring、live refresh 和 Qt acceptance；
- 尚未实现的功能，不得用“已接入”模糊带过。

同时写清：

- Raw/Derived checkbox 只控制显示；
- storage policy 来自 config/module policy；
- pause/clear display 不影响 acquisition/storage；
- trace 在没有显式时间轴时使用 sample index；
- optional plotting backend 的 fallback 顺序；
- 实验台操作和 showcase 启动方式。

---

## 质量门槛

完成前至少运行：

```bash
python -m pytest -q
python -m pytest -q tests/unit/test_live_data_catalog.py tests/unit/test_live_plot_selection.py
python -m pytest -q tests/unit/test_pyqt_live_compute_import.py
python -m compileall -q src tests
python -m qulab.gui.pyqt_operator_app --help
```

按 worker 实际新增测试补充精确路径。在 Qt 环境使用 offscreen platform 运行 widget tests；在 Windows 实验电脑至少完成一次正常可见窗口的手工 showcase。

再执行 portability 检查：

```bash
python -m pytest -q tests/unit/test_no_hardcoded_absolute_paths.py
```

如当前测试文件名不同，使用仓库实际等价测试。检查源码、configs、tests、docs 中不得新增 `/Users/...`、`C:\\Users\\...` 或开发者环境路径。允许测试 fixture 中使用 `tmp_path`。

---

## Definition of Done

只有同时满足以下条件才可标记完成：

1. Raw/Derived 都以 checkbox 选择，且 selection 在 refresh 中稳定。
2. 一维 scalar 使用 selected key 的真实 line renderer。
3. 二维 scalar 使用真实 heatmap renderer，不是 table 代替。
4. vector 与 matrix/channel 可以选择 point/channel 并显示 trace。
5. 至少一种 Raw + Derived compatible overlay 实际工作。
6. 不兼容选择、waiting、missing、malformed data 都有明确状态且不崩溃。
7. GUI refresh 被 throttled/coalesced，长 run 不按 event 无限重建全部 widgets。
8. Pause、resume、clear、auto-follow 行为符合合同且不影响 storage。
9. Qt main-thread 边界有实现和测试。
10. Data Viewer 与 Live View 复用 renderer 或明确共享底层 API，没有新增重复漂移实现。
11. deterministic showcase 覆盖 line、derived、heatmap、trace、matrix 和 waiting。
12. headless、Qt、integration、portability tests 通过。
13. docs 不再把 headless selection model 描述为完整 GUI plotting。
14. 未修改 `drivers/pycontrol`、硬件 timing 或 sequence semantics。

任何以下结果都不算完成：

- 只新增 dropdown/checkbox 但没有 signal wiring；
- checkbox 改变了 table，却没有改变真实绘图数据；
- heatmap 仍只显示 point table；
- trace 仍由 key 名称猜测或只显示 Python repr；
- 每个 event 都重建完整 source/status UI；
- Qt tests 只有 import smoke；
- 只提供截图，没有自动化行为断言；
- 通过修改 save policy 来实现 hide/show；
- 为了 Live View 修改或绕过 RunStore。

---

## Git 与交付

遵循仓库 Conventional Commits，建议拆为少量可回滚提交：

```text
feat(gui): add shared live scientific plot canvas
feat(gui): connect raw and derived live plot selection
test(gui): cover live view plotting interactions
docs(gui): document live view plotting completion
```

模块放在括号内，subject 简短描述结果。测试期的小修可以先提交到 worker branch，最终合并前允许通过 rebase/squash 整理，但不得改写已经共享且他人依赖的远端历史。不要提交运行数据、截图、cache、环境文件或 `drivers/pycontrol.zip`。

最终 handoff 必须给出：

1. 实际修改文件；
2. 新增/变化的公共 API；
3. Raw/Derived selection 和各 plot type 的行为；
4. renderer backend/fallback；
5. 自动测试命令与结果；
6. 手工验收矩阵结果和截图 artifact 路径；
7. 性能/刷新策略；
8. 已知限制；
9. commits；
10. 明确确认未修改硬件 driver、sequence semantics 和 storage policy。
