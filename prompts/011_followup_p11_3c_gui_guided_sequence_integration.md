# Prompt 011-followup P11.3C-GUI: Guided Sequence Qt Integration Completion Worker

下面这份 prompt 可直接交给 GUI/sequence worker。P11.3C 的 Qt-free `SequenceAuthoringModel`、provider descriptors、generic transform engine 和 standalone editor protocol 已经存在，但当前 Qt `Sequence Sweep` 页面仍是旧的 plan table + JSON fields 紧凑编辑器。本任务必须完成真正的可视化接入，使 operator 不需要记住 `sequence_plans` YAML、参数字段或 constraint JSON。

本任务是 P11.3C 的 GUI completion，不创建 P11.3D 新架构，不重写 P9 sequence runtime，也不增加第二个 Sequence Sweep panel。

---

## /goal

将现有 Control 页唯一的 `Sequence Sweep / 序列扫描` submode 升级为完整 Guided Sequence Authoring UI，支持：

1. Curated Family；
2. Generic Template Sweep；
3. Standalone Editor；

并按照九个实验任务阶段引导用户完成：

```text
1 Resource & Mode
2 Source
3 Channel & Trigger Roles
4 Fixed Parameters
5 Sweep Parameters
6 Targets & Propagation
7 Preview & Compare
8 Validate & Prepare
9 Bundle / Workflow / Provenance
```

完成后，用户必须能够仅通过 Qt UI：

- 创建一个 curated Rabi plan；
- 设置 fixed timing 和 `tau_s` linspace/range/explicit sweep；
- 看 first/current/last sequence timing preview；
- 插入或确认 canonical `sequence_sweep` workflow macro；
- Validate/Prepare 并看到 point count、plan hash、bundle/manifest 和 compiled workflow；
- 导入 generic ASG template，选择 pulse target/property/propagation/constraint；
- 打开 standalone editor，接收 protocol/validation/save/hash，刷新 plan 并使旧 Prepare 失效；
- 在任何错误阶段知道具体是哪个 parameter/channel/pulse/constraint 有问题。

不能要求用户在正常路径中手写 JSON、manifest 或 generated workflow。

---

## 当前事实与缺口

开始前必须根据当前代码重新确认。当前已知：

- `src/qulab/gui/sequence_authoring.py` 已有：
  - `MODES`；
  - `AUTHORING_STEPS`；
  - `ordered_status()`；
  - provider-driven `parameter_fields()`；
  - mode migration preview/change；
  - generic operation catalog；
  - template inspection；
  - first/current/last previews；
  - validation；
  - macro insertion；
  - editor saved-artifact acceptance。
- `src/qulab/gui/sequence_sweep_model.py` 已有 parameter/target/constraint mutation、point estimate、prepared/stale state。
- `src/qulab/gui/sequence_bridge.py` 已有 versioned editor protocol parsing/running。
- `OperatorController.sequence_authoring()` 已提供 shared authoring model。
- 当前 `src/qulab/gui/pyqt_views.py::_build_sequence_sweep_panel()` 仍使用：
  - plan overview table；
  - parameter `Mode fields (JSON)`；
  - target table；
  - raw `Constraints JSON`；
  - text-only preview/compiled dump。
- 当前 Qt 页面没有使用 `ordered_status()`、`change_mode()`、`parameter_fields()`、`generic_operation_catalog()`、`previews()` 或 editor protocol result。
- 当前测试只证明 headless model，未证明 QWidget 中能完成 guided workflow。

Worker 最终 handoff 必须逐项说明这些缺口如何被关闭。

---

## 开始前必须阅读

1. `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
2. `docs/P11_AUTHORING_DIAGNOSTICS_HISTORY.md`
3. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
4. `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
5. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
6. `docs/CONFIG_SCHEMA.md`
7. `docs/HARDWARE_SYNC.md`
8. `docs/OPERATOR_UI.md`
9. `prompts/009_followup_p9_3a_sequence_generation_foundation.md`
10. `prompts/009_followup_p9_3b_generic_asg_template_sweep.md`
11. `prompts/009_followup_p9_3c_sequence_sweep_gui.md`
12. `prompts/011_followup_p11_3c_guided_sequence_authoring.md`
13. `src/qulab/gui/sequence_authoring.py`
14. `src/qulab/gui/sequence_sweep_model.py`
15. `src/qulab/gui/sequence_bridge.py`
16. `src/qulab/gui/sequence_editor_launcher.py`
17. `src/qulab/gui/controller.py`
18. `src/qulab/gui/pyqt_views.py`
19. `src/qulab/gui/qt_compat.py`
20. `src/qulab/sequence_generation/`
21. `src/qulab/sequence_generation/providers/asg_model.py`
22. `src/qulab/sequence_generation/providers/asg_transforms.py`
23. curated providers and generic templates
24. `tools/sequence_editor/sequence_editor.py`
25. existing sequence generation/authoring/Qt tests

开始前运行：

```bash
git status --short --branch
python -m pytest -q
```

不要修改 `drivers/pycontrol`。不要覆盖其他 worker 或用户改动。若 P11.3B GUI worker 正在修改 `pyqt_views.py`，先协调文件所有权或将本页面拆入独立模块，不能互相覆盖。

---

## 严格范围

### 必须实现

- existing Sequence Sweep tab 的 guided replacement；
- plan overview/create/duplicate/delete；
- nine-step navigation/status；
- three authoring modes；
- provider-driven dynamic parameter forms；
- fixed/linspace/range/explicit controls；
- sampling order and point estimate；
- generic template channel/pulse browser；
- target/property/propagation/constraint structured editors；
- real first/current/last timing preview；
- validation/issue navigation；
- standalone editor protocol integration；
- Prepare/materialization state；
- bundle/hash/workflow/provenance view；
- shared config synchronization；
- Qt interaction/integration/manual acceptance tests；
- docs/status updates。

### 不实现

- 不创建第二个 Sequence Sweep tab/window；
- 不把 pulse 变成 core workflow node；
- 不修改 executor scan semantics；
- 不手写 manifest 作为 GUI 正常路径；
- 不在 preview/validate 中连接硬件；
- 不在 field change 时 full-materialize bundle；
- 不用 key/method 名猜 provider parameter；
- 不重新实现 provider/generic transform；
- 不把 standalone Qt5 widget 直接嵌入 Qt6/PySide6；
- 不实现 Direct Control；
- 不自动确认物理线缆或 output safety。

---

## 推荐模块边界

避免继续扩大单体 `pyqt_views.py`。推荐：

```text
src/qulab/gui/sequence_authoring.py              # Qt-free domain model，按需扩展
src/qulab/gui/sequence_authoring_presenter.py    # Qt-free view state/commands
src/qulab/gui/sequence_authoring_view.py         # optional Qt widget
src/qulab/gui/sequence_timeline_view.py          # optional Qt timeline renderer
src/qulab/gui/sequence_sweep_model.py            # existing mutations/state
src/qulab/gui/controller.py                      # stable public facade
src/qulab/gui/pyqt_views.py                      # page assembly only
```

Qt-free presenter 推荐返回 immutable snapshots：

```python
@dataclass(frozen=True)
class GuidedSequenceViewState:
    plans: tuple[PlanSummary, ...]
    selected_plan: str | None
    mode: str | None
    steps: tuple[AuthoringStepStatus, ...]
    parameter_fields: tuple[SequenceParameterField, ...]
    point_count: int | None
    issues: tuple[SequenceIssueViewModel, ...]
    prepared_state: str
    plan_hash: str | None
```

Qt view 不直接操作 model 私有字段，不直接解析 YAML/provider JSON，不在 widget slots 中复制 sampling/transform 规则。

---

## 页面信息架构

保持 `Control -> Sequence Sweep` 为唯一入口。推荐布局：

```text
┌ Plan toolbar: plan selector | New | Duplicate | Delete | state | point count ┐
├ Steps ─────────────┬──────────── Active authoring step ──────────┬ Issues ──┤
│ 1 Resource & Mode  │                                            │ errors    │
│ 2 Source           │ forms / tables / timeline                  │ warnings  │
│ 3 Channel Roles    │                                            │ location  │
│ ...                │                                            │ hint      │
│ 9 Provenance       │                                            │           │
├────────────────────┴────────────────────────────────────────────┴───────────┤
│ Back | Next | Validate | Insert workflow macro | Prepare                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

要求：

- steps 使用 compact list/stepper，不使用九张 decorative cards；
- complete/current/error/disabled 状态清楚；
- click step 可跳转，缺前置条件的 step disabled 并有 tooltip；
- issues panel 始终可见或可折叠，不能只在 Prepare modal 出现；
- plan toolbar 始终显示 edited/stale/prepared/building/error；
- plan change 不丢 unsaved widget edits；应先 apply/validate 或提示；
- 1366x768 可用；1920x1080 不过度拉伸；Windows 125% scaling 不重叠；
- 不显示大段教程文字，用 labels、tooltips、field status 和 concise empty states。

---

## Plan 创建与选择

替换当前简单 Add dialog，创建向导至少选择：

- plan id；
- pulse sequencer resource；
- mode：Curated / Generic / Standalone；
- curated provider，或 template/base sequence；
- optional sampling defaults。

规则：

- resource 列表只包含明确 `pulse_sequencer` capability 的 resources；
- provider 来自 registry descriptors；
- curated provider 不显示 template required；
- generic/standalone 必须选择 project-resolvable source；
- plan id collision inline error；
- Cancel 不改变 config；
- Finish 创建 shared `sequence_plans` entry，并立即进入 step 1/2；
- mode-specific defaults 来自 provider/model，不在 dialog 硬编码 Rabi。

Plan overview 保留为 compact selector/table，可以显示 resource/mode/provider/axes/points/state/hash，但不能继续作为唯一编辑界面。

---

## Step 1: Resource and Mode

提供：

- resource combo；
- `Curated | Generic | Standalone` segmented selector；
- resource adapter/capability summary；
- plan state；
- mode change preview。

切换 mode 必须：

1. 调用 `preview_mode_change()`；
2. 展示 retained/removed paths 的 human-readable diff；
3. 用户确认后调用 `change_mode()`；
4. Cancel 不改变 plan；
5. change 后使 prepared hash/state stale；
6. 重建后续 step forms；
7. 不静默删除 targets/parameters/template。

---

## Step 2: Source

### Curated

- provider selector；
- label/version/description/source identity；
- provider supports_preview；
- provider load error inline。

### Generic

- template file picker；
- project-relative path display；
- exists/mtime/hash；
- Inspect/Refresh；
- Open Editor when protocol supports it；
- external file change -> template stale + prepared invalid。

### Standalone

- base/concrete sequence picker；
- editor runtime/status/capabilities；
- Open/Edit；
- dirty/cancel/save result；
- saved artifact path/hash；
- explicit choice to use saved artifact as plan template/source；
- protocol mismatch/dependency/process errors inline。

Resource-global `resources.<asg>.sequence_file` 不作为新 plan 的正常 source。每个 plan/template/editor artifact 独立；旧 resource field 只做兼容读取，不自动写入 Operator Parameters。

---

## Step 3: Channel and Trigger Roles

显示 provider/template 可确认的：

- channels；
- laser init/gate；
- MW gate；
- readout gate/window；
- DAQ trigger channel；
- optional period/marker roles；
- output usage summary。

要求：

- curated channel roles 来自 provider schema/options；
- generic channel list 来自 `inspect_template()`；
- role suggestion 明确标 suggestion，必须由 operator 确认后写入；
- 不从字符串名称偷偷确认物理连线；
- 与 config `sync.triggers` 对照；
- mismatch/missing role 进入 structured issue；
- channel mapping 使用 combo/table，不要求 JSON。

如当前 `SequenceAuthoringModel` 缺少角色 mutation API，补 Qt-free API 和 tests，不在 widget 中直接改 nested dict。

---

## Step 4/5: Fixed and Sweep Parameters

参数定义必须来自 `parameter_fields()` / `SequenceFamilySpec` 或 generic target parameter schema。

每个 parameter 至少显示：

- label/name；
- dtype；
- unit；
- description tooltip；
- min/max/choices；
- sweepable；
- current mode；
- current values；
- validation status。

### Fixed controls

- float/int -> numeric input；
- choice -> combo；
- bool -> checkbox；
- channel/path -> suitable selector；
- unit visible；
- invalid literal 不写入 model。

### Sweep controls

Mode selector：

```text
Fixed | Linspace | Range | Explicit
```

动态 fields：

- Fixed: value；
- Linspace: start, stop, points；
- Range: start, stop, step；
- Explicit: structured value list editor；
- unit/expose_as where supported。

要求：

- non-sweepable parameter 只能 Fixed；
- mode change 清理不属于新 mode 的旧 fields，使用 model API；
- list 解析使用 YAML/JSON structured parser，不用 Python `eval`；
- point count 每次有效编辑后更新，但不 materialize；
- `max_points` 超限即时 error；
- sampling order 可视化排序，至少 Up/Down buttons；
- first/last coordinates 显示；
- 每个 edit 使 plan stale、清除 old plan hash；
- Operator Parameters 刷新后看到同一 sequence plan values。

旧 `Mode fields (JSON)` 只能放在 Advanced raw view，不能是默认参数编辑方式。

---

## Step 6: Targets and Propagation

Curated mode 默认显示 provider dependency summary；若 provider 不暴露 generic pulse targets，不要求 operator 编辑底层 pulses。

Generic mode 必须提供真实结构化界面：

### Template browser

- searchable channel/pulse table；
- channel、pulse index/label、start、duration、end、fingerprint；
- table selection 与 timeline selection 双向同步；
- stale/ambiguous pulse clearly marked。

### Target editor

- alias；
- selected channel/pulse/fingerprint；
- property：start/duration/end/gap-after 等 engine 实际支持项；
- bound parameter；
- transform options；
- Add/Remove/Duplicate；
- no raw JSON on normal path。

### Propagation

- None；
- Shift following；
- Shift group；
- group membership editor；
- affected pulse preview/list。

### Constraints

- Anchor/reference/offset form；
- preserve relationship options only if engine supports；
- dependency list；
- cycle/conflict inline error；
- raw JSON only optional read-only/advanced fallback。

所有 operation choices 来自 `generic_operation_catalog()` 或更具体的 transform capability descriptor，不能在 Qt 中维护漂移列表。

---

## Step 7: Preview and Compare

必须实现实际可视 timeline，不以 JSON/text dump 替代。

至少支持：

- First / Current / Last segmented selector；
- current point index slider/spin box；
- coordinate summary；
- channel rows；
- pulse rectangles with start/duration/end；
- pulse labels/roles；
- trigger/readout/acquisition markers；
- selected pulse highlight；
- changed/shifted pulses distinguishable；
- two-point Overlay 或 Difference；
- duration/period summary；
- zoom/reset where needed；
- malformed/empty preview message。

Preview 数据来自 `SequenceAuthoringModel.previews()` / provider preview model。若 provider preview result 形态不统一，新增 Qt-free normalized preview DTO；Qt renderer 不读取 provider-private objects。

要求 fixed dimensions and responsive constraints，hover/selection 不改变布局。Renderer 可使用 Qt painting/pyqtgraph，但不生成 SVG illustration，不依赖 hardware。

---

## Step 8: Validate and Prepare

提供：

- Validate button；
- issues grouped by parameter/channel/target/constraint/timing/workflow；
- severity/code/message/location/hint；
- click issue -> jump to step + focus field/pulse；
- point count/max points；
- estimated/generated size when available；
- workflow macro link status；
- Insert/Update Macro command；
- Prepare button；
- progress/building/cancel-safe state；
- failure remains editable；
- success marks prepared/hash。

Prepare：

- 在 worker thread/process 中执行，不能阻塞 Qt；
- 通过 existing controller prepare path；
- 不 connect hardware；
- 重复点击被阻止；
- error/warning 回到 issues；
- edit during/after Prepare 有确定 policy，至少禁止编辑或让完成结果因 revision mismatch 丢弃；
- prepared revision 必须对应当前 plan/config；
- no persistent bundle on simple Validate/Preview；
- full materialization only on explicit Prepare。

---

## Step 9: Bundle, Workflow, Provenance

Prepare 成功后显示：

- plan id/hash；
- provider/version/source hash；
- template hash；
- point count；
- bundle id；
- manifest path/hash；
- cache hit；
- first/current/last entry/coordinate；
- generated artifact location；
- canonical compiled workflow expansion；
- expected RunStore provenance fields。

要求：

- read-only；
- copy value/path actions；
- long hashes elide + full tooltip；
- Open artifact folder only when desktop capability available；
- no manual manifest editing；
- stale plan hides/marks old provenance，不能让 operator 误以为仍 prepared。

---

## Standalone editor lifecycle

Qt 必须真正消费 `run_sequence_editor_protocol()`：

- launch outside UI thread；
- show launching/running/cancelled/failed/saved；
- capabilities control buttons；
- stdout JSON and stderr logs handled separately；
- protocol version mismatch friendly；
- dependency/runtime missing friendly；
- timeout/cancel；
- validation rows displayed；
- saved artifact hash rechecked；
- success calls `accept_editor_result()`；
- update file watcher；
- stale plan/preview rebuilt；
- editor cancel/dirty without save does not alter plan。

不得沿用旧 launcher stdout `dialog.get_params()` 的隐式写回方式作为 authoritative plan update。

---

## Controller API

补充稳定 facade，避免 Qt slots 直接访问 models：

```python
controller.get_guided_sequence_state(plan_id=None)
controller.create_guided_sequence_plan(...)
controller.preview_sequence_mode_change(...)
controller.change_sequence_mode(...)
controller.update_sequence_parameter(...)
controller.update_sequence_target(...)
controller.update_sequence_roles(...)
controller.get_sequence_previews(...)
controller.validate_sequence_plan(...)
controller.insert_sequence_macro(...)
controller.prepare_sequence_plan(...)
controller.accept_sequence_editor_result(...)
```

名称可按现有风格调整。要求：

- snapshots/copies；
- stable domain errors；
- no QWidget types；
- shared config identity；
- every edit invalidates parsed/prepared/live authoring state as required；
- model/controller tests cover all public commands。

---

## State synchronization

以下 views 必须保持同一 authoring config：

- Guided Sequence；
- Operator Parameters；
- Builder Workflow；
- raw YAML save；
- Prepare/preflight；
- Live Run sequence context；
- historical run provenance。

规则：

- sequence edit 后 refresh Operator Parameters and Builder summary；
- macro insert 后 Workflow Tree 立即可见；
- external config load 重建 guided UI；
- external template/editor save 重建 template/targets/preview；
- Save YAML 保存 authoring plan，不保存独立 widget state；
- Prepare compiled workflow 只读；
- no resource-global single sequence field generated；
- multiple plans/resources/subsequences remain distinct。

---

## Qt tests

Qt unavailable 时可 skip；Qt available 时必须真实创建 QApplication/widget 并触发 signals。至少：

1. existing Sequence Sweep tab uses guided widget；
2. nine steps visible and state updates；
3. create Curated plan through UI；
4. provider change dynamically rebuilds fields；
5. Rabi fields来自 descriptor；
6. fixed -> linspace/range/explicit changes visible fields and model；
7. non-sweepable parameter cannot select sweep；
8. point count updates；
9. sampling order controls update model；
10. mode change confirmation/cancel；
11. Generic template inspect populates channel/pulse list；
12. selecting pulse synchronizes timeline/table；
13. target/property/propagation/constraint edit writes canonical plan；
14. first/current/last preview canvas nonblank；
15. issue click jumps to responsible step/field；
16. editor protocol success/failure/timeout/cancel states；
17. editor save invalidates prepared state；
18. Insert Macro updates Workflow Tree；
19. Prepare runs off UI thread and success displays hash/bundle；
20. edit after Prepare marks stale；
21. save/reload preserves semantics；
22. no duplicate Sequence Sweep panel；
23. resource-global `sequence_file` not invented；
24. optional Qt import remains safe。

不要只做 import smoke 或检查 widget object 存在。必须断言 user interaction -> controller/model/config 的真实变化。

---

## Headless and integration tests

补齐 GUI 所需 presenter/controller contract：

- guided state snapshots；
- mode migration；
- role mutation；
- parameter mode/value validation；
- target/propagation/constraint mutation；
- normalized preview DTO；
- issue location -> step mapping；
- revision/prepared stale handling；
- editor result acceptance；
- no hardware access。

Integration acceptance：

### Curated Rabi

1. 从空/基础 config 用 guided controller 创建 Rabi plan；
2. 设置 `tau_s` 三点 sweep；
3. 设置 required fixed params；
4. preview first/current/last；
5. insert macro；
6. Validate/Prepare；
7. dry-run；
8. 验证 SequenceSelected、coords、bundle/manifest/hash 和 RunStore provenance。

### Generic Sweep

1. 选择 generic base template；
2. 选择 MW pulse；
3. bind duration parameter；
4. enable shift following/group；
5. add anchor constraint；
6. preview first/last difference；
7. Prepare/dry-run；
8. 验证 concrete sequences 和 manifest coverage。

### Editor

用 fake protocol process 测试 save/hash/reinspect/stale；真实 editor 手工验收不进入默认 CI。

---

## Manual acceptance

在 Windows 实验电脑完成：

| Scenario | Expected |
|---|---|
| Load existing curated Rabi | Nine-step UI populated, no JSON editing required |
| Change tau range | Point count and first/last preview update immediately |
| Prepare | UI remains responsive; bundle/hash/provenance shown |
| Edit after Prepare | State becomes stale and old hash no longer appears current |
| Load generic template | Channels/pulses and timeline populate |
| Select pulse target | Table and timeline selection match |
| Configure shift following | Affected pulses highlighted in preview |
| Invalid constraint | Inline issue focuses constraint/pulse |
| Open standalone editor | Running/status/capabilities visible |
| Save editor artifact | Hash verified, preview refreshed, plan stale |
| Multiple plans/ASGs | Each plan keeps independent source/parameters |
| Save/reload YAML | Guided UI reconstructs same semantics |

保存至少三张非源码 artifact 截图：Curated parameters、Generic target/timeline、Prepared provenance。不要提交大二进制截图到 Git。

---

## Documentation updates

至少更新：

- `docs/OPERATOR_UI.md`；
- `docs/P11_AUTHORING_DIAGNOSTICS_HISTORY.md`；
- `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`；
- `docs/IMPLEMENTATION_ORDER.md`；
- worker handoff/status。

文档必须明确区分：

- P11.3C headless model 已完成；
- P11.3C-GUI Qt integration 本任务完成；
- standalone editor 与 generic plan 的职责；
- preview/validate 不连接硬件；
- Prepare 才 materialize；
- physical cable verification 仍需 bench；
- multiple plans/subsequences 不依赖单一 resource sequence file。

---

## Quality gates

完成前至少运行：

```bash
python -m pytest -q tests/unit/test_sequence_authoring.py
python -m pytest -q tests/unit/test_sequence_sweep_gui_model.py
python -m pytest -q tests/unit/test_sequence_generation_foundation.py
python -m pytest -q tests/unit/test_asg_template_generation.py
python -m pytest -q tests/unit/test_pyqt_live_compute_import.py
python -m pytest -q tests/integration/test_generated_rabi_dry_run.py
python -m pytest -q
python -m compileall -q src tests
python -m pytest -q tests/unit/test_no_hardcoded_absolute_paths.py
```

按新增 tests 补真实路径。Windows PowerShell 启动使用：

```powershell
$env:PYTHONPATH="src"
python -m qulab.gui.pyqt_operator_app
```

不得在 prompt/docs/tests 写入开发者绝对路径。Generated bundle/cache 保持在已忽略的 `/.qulab/`，正式 run provenance 仍由 RunStore 保存。

---

## Definition of Done

只有同时满足以下条件才算完成：

1. 当前唯一 Sequence Sweep Qt tab 已改为 guided UI。
2. Nine-step status 真正来自 `ordered_status()`/presenter，而非静态 labels。
3. Curated/Generic/Standalone 三种 mode 均有实际 Qt workflow。
4. Provider 参数字段动态生成，无 Rabi GUI hardcode。
5. Fixed/linspace/range/explicit 不需要 JSON。
6. Generic pulse/target/property/propagation/constraint 可结构化编辑。
7. First/current/last timeline 是真实非空图形预览。
8. Issues 可定位并跳转到 field/channel/pulse/constraint。
9. Standalone editor protocol 在 Qt 中完整消费。
10. Prepare 不阻塞 UI，且只在显式操作时 materialize。
11. Prepared bundle/hash/workflow/provenance 可读显示。
12. 所有 edit 正确使 prepared state stale。
13. Workflow macro、Operator Parameters、Save YAML 和 Live context 同步。
14. 多 ASG/多 plan/subsequence 独立，不生成单一 resource-global sequence file。
15. QWidget interaction tests 证明端到端 wiring。
16. Curated + Generic dry-run integration 通过。
17. Windows manual acceptance 和截图完成。
18. 完整 tests、portability 和 import safety 通过。

以下结果不算完成：

- 仅新增 `SequenceAuthoringModel` tests；
- 旧 table 外面增加九个静态 tab/label；
- 仍要求编辑 `Mode fields JSON` 或 `Constraints JSON`；
- preview 仍是 JSON/text dump；
- Open Editor button 存在但不消费 protocol result；
- mode/parameter widgets 不写回 shared config；
- Prepare 在 UI thread 阻塞；
- 只提供 screenshot，没有 QWidget behavior tests；
- 新建第二个 Sequence Sweep 页面而保留旧页面为另一套 source of truth。

---

## Git 与交付

遵循 Conventional Commits，建议：

```text
feat(gui): add guided sequence authoring view
feat(gui): add sequence parameter and target forms
feat(gui): add sequence timeline preview
feat(gui): connect editor protocol and prepare states
test(gui): cover guided sequence interactions
docs(sequence): document guided Qt authoring
```

最终 handoff 必须包含：

1. 修改文件；
2. presenter/controller API；
3. 三种 mode 的功能矩阵；
4. Nine-step UI 状态规则；
5. parameter/target/constraint widgets；
6. timeline renderer/normalized preview contract；
7. editor protocol lifecycle；
8. Prepare/revision/stale policy；
9. automated test commands/results；
10. Windows manual acceptance/screenshots artifact；
11. commits；
12. known limits；
13. 明确确认没有修改 hardware driver、executor scan semantics 或 RunStore provenance authority。
