# Prompt 009-followup P9.3C: Sequence Sweep GUI Submode Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是在现有PyQt/PySide Operator Console的`Control`页面加入`Sequence Sweep` submode，直接编辑P9.3A `sequence_plans`，调用P9.3B template inspection/preview，执行Prepare materialization并显示统一preflight。GUI不得保存私有状态或重新实现sampling/transform。

---

## /goal

让实验现场的Rabi sequence scan从一个集成页面完成：

1. 选择curated family或generic template provider。
2. 编辑fixed/linspace/range/explicit参数和单位。
3. generic模式选择channel/pulse/property/propagation/anchor。
4. 预览first/current/last代表点。
5. 查看point count、plan hash、cache/build和preflight。
6. 点击Prepare自动生成bundle与canonical workflow。
7. 保存后YAML可由CLI重复Prepare/run。

不要求用户打开Builder或手写manifest、bundle block、nested scan或load action。

---

## 硬依赖

P9.3A和P9.3B必须完成且tests通过。开始前读取实际公共API：

- plan/spec/provider registry；
- sampling/estimate；
- preparation/materialization result；
- generic ASG `inspect_template()`；
- target selector/fingerprint；
- preview data；
- validation issue模型。

GUI必须消费这些接口，不得复制业务逻辑到Qt classes。

---

## 必须先阅读

1. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
2. `docs/OPERATOR_UI.md`
3. `docs/CONFIG_SCHEMA.md`
4. `docs/DATA_MODEL.md`
5. `workers/gui_worker.md`
6. `workers/qa_worker.md`
7. P9.3A/P9.3B实现和handoff
8. `src/qulab/gui/controller.py`
9. `src/qulab/gui/pyqt_operator_app.py`
10. `src/qulab/gui/pyqt_views.py`
11. `src/qulab/gui/qt_compat.py`
12. `src/qulab/gui/operator_parameters.py`
13. `src/qulab/gui/workflow_model.py`
14. `src/qulab/gui/sequence_bridge.py`
15. `src/qulab/gui/sequence_editor_launcher.py`
16. 现有Qt/model/controller tests

---

## 严格范围

### 必须实现

- headless `SequenceSweepEditorModel`；
- Controller plan CRUD/preview/prepare APIs；
- fourth submode switch；
- family/provider/template selector；
- dynamic parameter table/form；
- generic target/property/propagation/anchor editor；
- representative-point preview；
- plan summary、point count、hash/cache/build状态；
- unified validation/preflight table；
- Builder macro/compiled preview；
- Operator Parameters synchronization；
- standalone editor bridge/template invalidation；
- YAML round-trip；
- import-safe/headless/Qt tests；
- docs。

### 不实现

- 不实现provider、sampling、transform或manifest writer；
- 不直接调用ASG/NI/MW driver；
- 不增加hardware output按钮；
- 不把standalone PyQt5 editor widget嵌入Qt6主窗口；
- 不实现全局异构Phase F scan editor；
- 不实现Ramsey/Hahn production family；
- 不实现完整graphical pulse editor；
- 不在field change时materialize完整bundle。

---

## 推荐文件

```text
src/qulab/gui/sequence_sweep_model.py
src/qulab/gui/sequence_sweep_view.py
src/qulab/gui/sequence_preview_widget.py   # only if reusable and needed
src/qulab/gui/controller.py
src/qulab/gui/pyqt_views.py
src/qulab/gui/pyqt_operator_app.py
```

Model必须无Qt依赖；View只持有display/editor state，authoring truth在Controller config。

建议tests：

```text
tests/unit/test_sequence_sweep_gui_model.py
tests/unit/test_sequence_sweep_controller.py
tests/unit/test_sequence_sweep_yaml_roundtrip.py
tests/unit/test_sequence_sweep_preview_model.py
tests/unit/test_pyqt_sequence_sweep_import.py
tests/integration/test_sequence_sweep_gui_prepare.py
tests/integration/test_sequence_sweep_gui_dry_run.py
```

---

## Main Window Integration

Control page submode：

```text
[ Operator Parameters ] [ Sequence Sweep ] [ Builder Workflow ] [ Direct Control ]
```

规则：

- 使用同一主窗口，不新增第二个app/window；
- toolbar Load/Save/Prepare/Start/Stop不变；
- 实验/setup选择、resource preview、preflight区域复用；
- switching不丢失未保存但已写入Controller model的编辑；
- Sequence Sweep只在当前config存在或可创建sequence plan时显示可编辑内容；
- 无sequence resource时显示empty state和validation，不创建虚假`asg` resource；
- Direct Control安全策略不变。

不要用大量decorative cards。采用紧凑table/form/splitter布局，适合桌面实验操作。

---

## Headless GUI Model Contract

推荐对象：

```python
@dataclass(frozen=True)
class SequencePlanViewModel:
    id: str
    resource: str
    provider: str
    provider_version: str | None
    template: str | None
    parameters: tuple[SequenceParameterRow, ...]
    targets: tuple[SequenceTargetRow, ...]
    constraints: tuple[SequenceConstraintRow, ...]
    point_count: int
    plan_hash: str | None
    state: str
    issues: tuple[SequenceIssueViewModel, ...]

class SequenceSweepEditorModel:
    def load(config, registry) -> ...
    def list_plans() -> ...
    def create_plan(...) -> ...
    def update_parameter(...) -> ...
    def update_target(...) -> ...
    def update_constraint(...) -> ...
    def remove_plan(...) -> ...
    def to_config_patch() -> ...
```

所有update通过schema-aware model并立即写回Controller持有的raw config。不要等到Save时从widget text反向拼YAML。

状态建议：

```text
unconfigured
edited
validating
valid
previewing
materializing
prepared
stale
error
```

任何plan/template/parameter/target变化后：

- invalidate prepared result；
- state -> edited/stale；
- Start禁用直到再次Prepare；
- 旧bundle/cache可保留但不能被当前plan静默使用。

---

## Controller API

在`OperatorController`提供headless APIs，命名可按实际风格调整：

```python
list_sequence_plans() -> list[SequencePlanViewModel]
create_sequence_plan(plan_id, resource, provider, template=None) -> None
delete_sequence_plan(plan_id) -> None
update_sequence_plan_parameter(plan_id, name, patch) -> None
update_sequence_plan_target(plan_id, alias, patch) -> None
update_sequence_plan_constraints(plan_id, constraints) -> None
inspect_sequence_template(plan_id) -> TemplateInspection
preview_sequence_plan(plan_id, coordinates) -> SequencePreview
estimate_sequence_plan(plan_id) -> PlanEstimate
prepare() -> PreflightViewModel
```

要求：

- Controller不import Qt；
- config mutation后`parsed/prepared` cache失效；
- Prepare使用P9.3A preparation API；
- Start使用相同frozen preparation result；
- Save保存authoring config，不保存GUI-only state；
- errors转换为已有PreflightIssueViewModel或兼容统一issue model；
- long materialization可由background worker调用，但Controller API本身可同步测试。

---

## Family / Template Section

控件：

- plan selector和add/delete/duplicate；
- resource combo，仅显示pulse sequencer-capable resources；
- provider/family combo；
- provider version只读或受choices限制；
- template file picker（provider需要时）；
- Open Editor icon/button；
- Refresh template；
- family description和output format compact summary。

Provider list来自registry descriptors，不在GUI hard-code只有Rabi。Import失败的provider仍显示config值和错误，不能导致整个panel崩溃。

Open Editor复用现有launcher。Editor save/exit后：

- refresh template hash/inspection；
- validate targets/fingerprints；
- mark plan stale；
- clear previous preview；
- require Prepare。

---

## Parameter Editor

动态读取`SequenceFamilySpec.parameters`。每行至少：

```text
Label | Mode | Value/Start | Stop | Points/Step/Values | Unit | Status
```

控件语义：

- mode combo: fixed/linspace/range/explicit；
- fixed显示value；
- linspace显示start/stop/points；
- range显示start/stop/step；
- explicit使用可验证list editor/table，不用eval；
- numeric输入遵循dtype/range；
- enum使用combo；bool使用checkbox；
- unit只读显示family canonical unit；
- nonsweepable参数禁用非fixed mode；
- issue显示在行内和统一issue table；
- point count实时使用A的estimate，不自己计算另一套。

多个swept参数提供loop order editor（up/down icons），对应`sampling.order`。MVP只显示Cartesian；不得把zip/table伪装成可用。

---

## Generic Targets and Timing Links

仅当provider支持template target editing时显示advanced section。

Targets table：

```text
Alias | Channel | Pulse | Base start | Base duration | Fingerprint status
```

Channel/pulse choices来自B的inspection API。选择后由B生成selector/fingerprint，GUI不自己hash/解析JSON。

Transform rows：

```text
Parameter | Target | Property | Propagation | Scope/Group | Status
```

Property choices来自provider capability。Propagation choices：

- none；
- shift_after same_channel；
- shift_after all_channels；
- shift_group named group；
- constraints。

Constraints table：

```text
Target anchor | Reference anchor | Offset | Unit | Status
```

只产生结构化schema，不提供expression text field。Cycle/conflict由B validator返回并映射到具体row。

Curated family默认隐藏advanced section，只显示read-only dependency summary和“Switch to generic template”显式迁移动作（若支持）。

---

## Preview

Preview只调用provider preview：

- default first/current/last tabs或segmented control；
- 对每个sweep axis提供current value selector；
- timing图显示channel rows、pulse blocks、aliases、trigger markers；
- 可选first/current/last overlay，颜色区分但保持可读；
- 显示total duration和warnings；
- preview失败不连接硬件、不materialize全bundle；
- preview结果与B的generate engine一致。

可以使用Qt painting或项目已有plot库。不得解析vendor JSON再次重建另一份preview timing。

Preview widget有稳定minimum size和layout，不因pulse label改变导致panel跳动。长label elide并提供tooltip。

---

## Prepare / Build UX

显示：

- estimated point count；
- provider/template/plan short hash；
- expected cache key；
- build state和progress `n/total`；
- cache hit/miss；
- generated manifest path/hash；
- P9.1 coverage；
- P9.2 trigger/window issues；
- compiled workflow summary。

Prepare流程必须在background thread执行以免冻结GUI；Qt UI更新通过signals/queued callbacks。Headless Controller tests可以同步。

禁止：

- field change时自动生成101个文件；
- generation期间连接hardware；
- generation失败后启用Start；
- silently reuse old prepared bundle；
- 把provider traceback原样塞满UI。日志可保留详细trace，issue显示清楚summary。

Cancel若A支持，应停止后续point generation并清理temp staging；不承诺取消vendor hardware，因为此阶段无hardware。

---

## Builder and Operator Parameters Synchronization

Builder Workflow：

- 显示`sequence_sweep <plan_id>` macro node；
- inspector显示plan/resource/axes/point count；
- 提供read-only“Compiled Preview”显示nested scans和load action；
- 用户不直接编辑compiled preview；
- 删除/复制macro时更新authoring config并保持plan引用校验。

Operator Parameters：

- 自动发现`sequence_plans.<id>.parameters.<name>`；
- 常用fixed/sweep ranges可快速显示；
- 简单值修改同步到Sequence Sweep；
- target/property/propagation只在Sequence Sweep编辑；
- 同一source不得重复显示多个冲突控件；
- sequence plan parameter和旧workflow scan参数要区分label/source。

---

## YAML Round-Trip

保存：

- `sequence_plans`；
- `sequence_sweep` macro；
- targets/groups/constraints；
- parameter modes/values/order；
- no Qt objects、absolute cache paths或compiled bundle internals。

Reload后所有controls、order、fingerprints、constraints恢复。Prepare生成的resolved config/run artifacts由A/RunStore负责，不写回authoring YAML除非用户显式export。

---

## Qt Compatibility and Layout

- 使用现有`qt_compat`，优先PySide6/fallback PyQt6；
- 无Qt时module import安全；
- widget tests无binding/display时clean skip；
- 不import PyQt5 standalone editor classes；
- 按钮使用现有icon库/lucide若已启用，否则Qt standard icons；
- icon-only按钮有tooltip；
- cards不嵌套；
- compact headings，适合高密度实验参数；
- splitter尺寸可调整；
- error/warning/status颜色遵循现有theme；
- 文本不溢出，长path elide+tooltip。

---

## Test Matrix

至少覆盖：

1. model load/create/update/delete/duplicate plan。
2. parameter mode切换清理不适用字段。
3. provider spec动态生成rows。
4. nonsweepable/enum/bool/unit handling。
5. loop order更新point estimate。
6. target selection调用B API并保存fingerprint。
7. template变化使target/plan stale。
8. constraints结构化round-trip。
9. config mutation使prepared result失效。
10. Prepare成功后Start enabled state。
11. generation/preflight失败后Start disabled。
12. Controller Prepare不连接resources。
13. first/current/last preview coordinates正确。
14. preview不materializefull bundle。
15. Operator Parameters与Sequence Sweep双向同步。
16. Builder macro和compiled preview正确。
17. Save/reload YAML保持authoring state。
18. generic 2D config从GUI model Prepare/dry-run成功。
19. curated Rabi range从GUI model修改后entry/coords更新。
20. Qt import safe/optional tests skip cleanly。
21. old GUI configs/submodes不回归。
22. full suite通过。

---

## 文档更新

更新`docs/OPERATOR_UI.md`当前实现状态、启动方式和known limits；更新Phase E plan标记E4完成。不要把Direct Control或global Phase F误标为完成。

---

## 验收命令

```bash
python -m pytest tests/unit/test_sequence_sweep_gui_model.py
python -m pytest tests/unit/test_sequence_sweep_controller.py
python -m pytest tests/unit/test_sequence_sweep_yaml_roundtrip.py
python -m pytest tests/unit/test_sequence_sweep_preview_model.py
python -m pytest tests/unit/test_pyqt_sequence_sweep_import.py
python -m pytest tests/integration/test_sequence_sweep_gui_prepare.py
python -m pytest tests/integration/test_sequence_sweep_gui_dry_run.py
python -m pytest
```

若Qt可用，worker必须启动GUI并实际检查：切换submode、修改Rabi range、generic target选择、preview、Prepare、Save/reload。报告Qt binding和观察结果。

---

## 完成定义

- Rabi range从一个panel修改并Prepare；
- generic pulse target/link可由UI编辑；
- 不需要手写generated plumbing；
- GUI与CLI共享同一authoring YAML；
- Preview/Prepare使用A/B接口，无业务逻辑复制；
- hardware在Prepare中未连接；
- Qt缺失不破坏tests/import；
- full suite通过。

---

## 最终汇报

1. 修改文件。
2. Controller/model公共接口。
3. 最终UI布局和交互。
4. Rabi与generic操作路径。
5. Prepare/background/cache/preflight状态。
6. YAML round-trip和compiled preview。
7. Qt/manual verification。
8. tests结果。
9. 给P9.3D的handoff和remaining limits。

