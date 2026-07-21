# Prompt 010-followup P10.3: Live View Raw/Derived + Sequence Context GUI Worker

下面这份 prompt 可直接交给新的AI worker。目标是完成P10 Phase C，并做P9/P10 GUI汇合：在同一`Live Run`页面增加raw/derived data catalog、key/plot/dimension selectors、module status；同时显示P9 Sequence Family/Template Sweep/Generic Sweep当前point的bundle/entry/hash/coordinates。Control页仍由P9.3C Sequence Sweep负责authoring。

---

## /goal

实验运行时，operator可以：

- 在Raw和Derived列表中选择数据key；
- 选择scalar line、2D heatmap、point trace等合适视图；
- 勾选/隐藏derived结果而不改变storage；
- 看到module enabled/running/success/warning/error/latency；
- 看到当前Sequence plan/family、bundle entry、tau等坐标和sequence hash；
- 确认Template/Generic Sweep正常通过P9 bundle runtime逐点调用；
- 在run结束后将同一run交给Data Viewer。

Live View不包含公式实现，也不在运行中编辑prepared sequence plan。

---

## 开始条件与并发规则

必须同时完成：

1. P10.1 schema/registry。
2. P10.2 events/engine/storage。
3. P9.3C Sequence Sweep GUI和Controller handoff。

P10.3不得与P9.3C同时修改`controller.py`、`pyqt_views.py`或主窗口submode layout。开始前读取P9.3C最终代码和handoff，在其接口上集成，不恢复旧三submode布局，不创建第二个Sequence Sweep panel。

如果P9.3C尚未完成，只能完成headless LiveDataCatalog/plot selection model；必须停止GUI file integration并在handoff说明依赖，不能凭prompt虚构接口。

---

## 必须先阅读

1. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
2. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
3. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
4. `docs/OPERATOR_UI.md`
5. `docs/DATA_VIEWER_REQUIREMENTS.md`
6. `workers/gui_worker.md`
7. `workers/plotting_worker.md`
8. `workers/qa_worker.md`
9. P9.3C实现/handoff
10. P10.1/P10.2实现/handoff
11. `src/qulab/gui/controller.py`
12. `src/qulab/gui/pyqt_views.py`
13. `src/qulab/gui/plot_model.py`
14. `src/qulab/gui/models.py`
15. `src/qulab/gui/qt_compat.py`
16. `src/qulab/storage/run_reader.py`
17. `src/qulab/storage/dataset_model.py`
18. `src/qulab/storage/slicing.py`
19. current Data Viewer panel/model

---

## 严格范围

### 必须实现

- headless LiveDataCatalog；
- raw/derived key specs/status；
- live point buffer keyed by point/key；
- module status model；
- sequence context model；
- controller live state APIs；
- Live Run source selector；
- line/heatmap/trace plot selection；
- dimension/point/channel selectors；
- compatible scalar overlay或清楚single-primary MVP；
- AnalysisStatus panel；
- Sequence Context panel；
- P9 SequenceSelected integration；
- P10 DerivedData integration；
- saved/live-only badges；
- completed run -> Data Viewer handoff；
- Qt import/headless/integration tests；
- docs。

### 不实现

- 不实现compute formula/module engine；
- 不实现sequence generation/transform；
- 不重写P9.3C Sequence Sweep authoring；
- 不实现post-run recompute；
- 不实现async queue（只预留queue/lag字段）；
- 不修改raw run data；
- 不通过key名称猜plot kind或raw/derived；
- 不在Live Run中允许改变prepared timing；
- 不新增另一个main app/window。

---

## 推荐模块

```text
src/qulab/gui/live_data_catalog.py
src/qulab/gui/live_plot_model.py
src/qulab/gui/analysis_status_model.py
src/qulab/gui/sequence_context_model.py
src/qulab/gui/live_run_view.py        # 如现有pyqt_views适合拆分
src/qulab/gui/controller.py
src/qulab/gui/pyqt_views.py
```

Headless models不import Qt。Qt view不直接解析events之外的YAML/vendor JSON。

建议tests：

```text
tests/unit/test_live_data_catalog.py
tests/unit/test_live_plot_selection.py
tests/unit/test_analysis_status_model.py
tests/unit/test_live_sequence_context.py
tests/unit/test_live_run_controller.py
tests/unit/test_pyqt_live_compute_import.py
tests/integration/test_live_view_raw_derived_events.py
tests/integration/test_live_view_sequence_compute_run.py
```

---

## Live Data Catalog Contract

推荐：

```python
@dataclass(frozen=True)
class LiveDataKeySpec:
    key: str
    source_kind: str          # raw | derived
    data_kind: str            # scalar | vector | matrix | trace | unknown
    unit: str | None
    dims: tuple[str, ...]
    source_module: str | None
    saved: bool
    visible_default: bool
    status: str               # declared | waiting | active | error | unavailable

class LiveDataCatalog:
    def declare_from_config(...): ...
    def handle_event(event): ...
    def list_raw(): ...
    def list_derived(): ...
    def get(key): ...
```

Initialization来源：

- workflow `save_as`和可靠data specs；
- analysis declared effective outputs；
- module show/save policies；
- sequence/workflow coordinate definitions。

Event updates：

- raw DataPoint -> raw spec；
- DerivedData -> derived spec；
- AnalysisStatus -> module/output status；
- unknown event ignore。

Declared derived output在first result前显示`waiting`。Raw/derived collision理论上已preflight；runtime遇到时显示error且不覆盖raw。

`saved`来自event/module policy，不通过run folder是否已有文件猜测。live-only明确badge。

---

## Live Point Buffer

按`(point_id, key)`存current run display values：

- raw和derived可能不同时间到达；
- coords一致性检查；
- derived later update existing point；
- point table一行一个measurement point，不为derived另建行；
- bounded display history避免长run无限内存；storage仍保存全量；
- buffer eviction policy明确，默认保留recent N display points或plot所需grid；
- 不mutateevent data；
- async future out-of-order由point_id/coords处理。

提供line/heatmap/trace提取API，尽量复用`DatasetModel/SliceController`概念和数据类，但不要为了live每次重读run folder。

---

## Plot Selection Model

推荐：

```python
@dataclass
class LivePlotSelection:
    keys: tuple[str, ...]
    plot_type: str
    x_dim: str | None
    y_dim: str | None
    selectors: Mapping[str, Any]
    point_id: str | None
    channel: Any | None
```

Rules：

- scalar + one coord -> line；
- scalar + two coords -> heatmap；
- vector/trace -> selected point trace；
- >2 coords -> x/y + remaining selectors；
- compatible scalarkeys可overlay：dims兼容，units相同或都None；
- incompatible选择阻止或分panel，不能无提示画同一axis；
- initial selected keys来自`visible_default/show`；
- user hide/show只改GUI state，不改module save/show config during run；
- plot type来自data_kind/dims，不来自`counts`/`trace`名称；
- dynamic new key出现时catalog更新但不抢走user当前selection。

若现有plot backend只支持line，worker至少实现专业line + table/heatmap fallback，但P10.3 acceptance要求2D scalar有可读heatmap或明确可用table-grid；不能显示错误一维折线。

---

## Live Run UI Layout

保持Control/Live Run/Data Viewer pages。Live Run推荐：

```text
┌ Data Sources ─────┬──────── Live Plot ───────────────┬ Compute / Sequence ┐
│ Raw               │                                  │ Modules             │
│ [x] counts        │                                  │ trace_summary ok    │
│ [ ] trace         │                                  │ latency 2.1 ms      │
│ Derived           │                                  │                    │
│ [x] contrast      │                                  │ Sequence            │
│ [ ] fit (waiting) │                                  │ rabi_main/tau=...   │
├ Plot controls ────┴──────────────────────────────────┴────────────────────┤
│ point/event table + run log                                               │
└────────────────────────────────────────────────────────────────────────────┘
```

Controls：

- Raw/Derived分组checkbox/list；
- saved/live-only/waiting/error badges；
- plot type selector；
- x/y dimension combos；
- selector controls仅显示隐藏维度；
- point/channel selector；
- module status table；
- sequence context compact table；
- clear display（不删storage）和auto-follow toggle。

UI紧凑、可scan，不用nested cards或marketing composition。长key/path/hash elide+tooltip。

---

## Module Status Panel

每module显示：

- enabled/disabled；
- state；
- last point；
- last success time；
- last latency；
- warning/error summary；
- fail policy；
- queue depth/lag placeholder（P10.5）；
- live-only/saved outputs summary。

Status由AnalysisStatus events驱动。Error详情可进run log/tooltips，主table不展示完整traceback。

运行中不允许切换enabled/fail policy，因为prepared plan已冻结。可提供“Open Analysis Config”切回Control，在下一次Prepare生效。

---

## Sequence Context Panel

消费P9 `SequenceSelected`和prepared sequence generation summaries。

显示：

- plan ID；
- mode：Curated Family / Generic Template Sweep / Existing Bundle / Single File；
- provider/family/template label；
- bundle ID和entry ID；
- requested/resolved coordinates；
- short manifest/sequence SHA-256；
- duration/trigger/output metadata；
- selection status和last error。

Rules：

- per-point updates与point table同point_id；
- Generic/Template Sweep不调用另一套loader，实际信息来自P9 events/provenance；
- old single-file config显示sequence snapshot，不伪造bundle entry；
- panel read-only；
- `Open in Sequence Sweep`只切Control submode，running时不得mutatecurrent plan；
- selection failure通过ErrorRaised/preflight显示，不能继续显示上一个entry像当前成功。

---

## Controller Integration

扩展一个共享event handler，而不是view直接散落判断：

```python
controller.handle_live_event(event)
controller.get_live_data_catalog()
controller.get_live_plot_data(selection)
controller.get_analysis_statuses()
controller.get_current_sequence_context()
controller.reset_live_state()
```

开始run前reset；event callback可以先更新controller model，再enqueue Qt view notification。避免background run thread直接操作widgets。

`start_run()` subscription order由P10.2定义。P10.3不能改变raw-before-derived保障。

Run结束：

- 保留final live state；
- Data Viewer自动/可选打开run path；
- viewer catalog来自stored manifest，因此live-only key不出现；
- GUI清楚区分“live见过但未保存”。

---

## Control-Side Analysis Reservation

在Operator Parameters或一个compact Analysis section显示prepared module table：

```text
Enabled | Module | Run Live | Show | Save | Fail Policy | Validation
```

P10.3可实现基础boolean/policy编辑，写回`analysis.modules`并invalidate Prepare。Module-specific args若P10.1有argument specs，可生成number/bool/choice控件；否则在Builder/YAML编辑。

不要增加formula text editor或`eval`输入。

如果P9.3C已提供Control extension slot，使用它；否则最小接入Operator Parameters，不重排Sequence Sweep布局。

---

## Qt Threading

- experiment仍在background thread；
- event callback将event放thread-safe queue；
- main Qt timer/signals drain queue并更新models/widgets；
- no widget access fromexecutor/compute thread；
- P10.2同步compute latency发生在run thread；
- P10.5 async derived可从different thread emit，届时同一queue仍可用；
- high-frequency events batch UI refresh，避免每sample repaint；
- raw storage不依赖GUI queue。

---

## Tests

至少覆盖：

1. declared raw/derived catalog beforeevents。
2. waiting->active transition。
3. saved/live-only badges。
4. raw/derived same point merge。
5. out-of-order derived association。
6. catalog collision/error。
7. scalar line extraction。
8. 2D heatmap extraction。
9. trace point/channel selection。
10. hidden dimension selectors。
11. compatible/incompatible overlay。
12. userselection preserved whennew keyappears。
13. AnalysisStatus states/latency/error。
14. SequenceSelected family/generic/existing bundle context。
15. old single-file context。
16. failed selection clears/marks stale current context。
17. Controller event handling noQt。
18. P9 generated Rabi + P10 derived scalar integrated run。
19. live-only visible live but absentData Viewer catalog。
20. saved derived visible completed viewer。
21. Qt import safe/optional skip。
22. GUI event queue no cross-thread widget access。
23. old Live Run/Control/Data Viewer behavior不回归。
24. full suite。

---

## 文档更新

更新：

```text
docs/OPERATOR_UI.md
docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md
docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md
docs/DATA_VIEWER_REQUIREMENTS.md
docs/IMPLEMENTATION_ORDER.md
```

标记P10 Phase C完成。P10.4/5保持planned；不要把P9.3D hardware验证误标完成。

---

## 验收命令

```bash
python -m pytest tests/unit/test_live_data_catalog.py
python -m pytest tests/unit/test_live_plot_selection.py
python -m pytest tests/unit/test_analysis_status_model.py
python -m pytest tests/unit/test_live_sequence_context.py
python -m pytest tests/unit/test_live_run_controller.py
python -m pytest tests/unit/test_pyqt_live_compute_import.py
python -m pytest tests/integration/test_live_view_raw_derived_events.py
python -m pytest tests/integration/test_live_view_sequence_compute_run.py
python -m pytest
```

Qt可用时manual verification：

1. 加载generated Rabi/Generic Sweep + analysis config。
2. Prepare。
3. Start dry-run。
4. 查看tau/entry/hash逐点变化。
5. 在raw counts与derived key之间切换。
6. 验证line/heatmap/trace controls。
7. 查看module status。
8. run结束打开Data Viewer并核对saved/live-only差异。

报告Qt binding和观察结果。

---

## 完成定义

- P9 Sequence Sweep authoring与Live Run sequence context正确分工；
- raw/derived keys可选择并正确plot；
- module status可见；
- Template/Generic/Curated sequence正常逐点显示actual entry/hash；
- live-only不落盘，saved derived可在viewer打开；
- no formula/transform duplication；
- Qt/headless/full suite通过。

---

## 最终汇报

1. 修改文件和model/controller API。
2. 与P9.3C handoff如何合并。
3. Live Run布局和selectors。
4. raw/derived/module status语义。
5. sequence context四种mode展示。
6. integrated run结果。
7. Qt/manual verification。
8. tests。
9. 给P10.4/5的catalog/threading handoff。

