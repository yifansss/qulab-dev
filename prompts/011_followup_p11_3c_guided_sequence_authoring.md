# Prompt 011-followup P11.3C: Guided Sequence Authoring and Feedback Worker

这份 prompt 可直接交给 sequence/GUI worker。目标是把现有 Sequence Sweep、generic template transform 和 standalone sequence editor bridge 整理成一个按实验任务顺序组织、功能可发现、持续反馈、可预览、可验收的 authoring experience。

本任务不把 pulse 抽象成 Qulab core workflow node。主 workflow 仍只执行 sequence_sweep/load/arm/start/read 等宏观步骤；pulse 细节属于 provider/template/editor。

## Dependencies

依赖：

- 已完成 P9.3A-D sequence generation contracts；
- P11.1 diagnostics；
- P11.3A ActionSpec registry；
- P11.3B shared authoring document/composer integration。

开始前读取各 worker handoff，避免同时修改 `pyqt_views.py`、controller 或 sequence sweep model。

## /goal

提供一个 Sequence Authoring 子面板，支持三种明确模式：

1. **Curated Family**：Rabi/Ramsey/Hahn Echo 等 provider-declared parameters。
2. **Generic Template Sweep**：导入 base sequence，选择 channel/pulse target，扫描 duration/start/end/gap，配置 following/group shift/anchor constraints。
3. **Standalone Editor**：通过 versioned bridge 打开/编辑具体 sequence，返回 capabilities、validation、dirty/save/preview 状态。

用户应能按顺序完成 resource -> mode -> source -> channel roles -> fixed params -> sweep params -> targets/propagation -> preview -> validation -> Prepare，并知道每一步缺什么、为什么错、会生成多少点和如何进入主 workflow/data provenance。

## 必须先阅读

- `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
- `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
- `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
- `docs/CONFIG_SCHEMA.md`
- `docs/HARDWARE_SYNC.md`
- `docs/OPERATOR_UI.md`
- all P9.3 prompts/handoffs
- `src/qulab/sequence_generation/`
- provider models/registry/sampling/compiler/materializer
- ASG model/transforms/template inspector
- `src/qulab/gui/sequence_sweep_model.py`
- `src/qulab/gui/sequence_bridge.py`
- current Sequence Sweep Qt code
- `tools/sequence_editor/sequence_editor.py` and its vendored dependencies
- representative bench 10-12 and dry-run sequence configs

## Unified authoring state

三种模式必须写回同一 `sequence_plans` authoring model：

- Curated provider -> family/provider + parameter plans；
- Generic -> `asg_template` provider + template + targets/groups/constraints；
- Standalone editor -> base/template sequence artifact，必要时由 generic provider or single-file resource path 使用；
- compiled workflow/bundle 是 derived output，只读显示；
- 不允许 GUI 同时维护另一份不一致的 plan。

切换模式前显示 migration/diff preview；不能静默丢失 targets 或 parameters。

## Ordered task flow

UI 按以下顺序分区/stepper/tabs，当前步骤有状态：

1. Resource and Mode
2. Family / Template / Sequence Source
3. Channel and Trigger Roles
4. Fixed Parameters
5. Sweep Parameters
6. Pulse Targets and Propagation
7. Preview and Compare
8. Validation and Prepare
9. Generated Bundle / Workflow / Provenance

不要把所有功能平铺成一张无上下文表格。后续步骤可以提前查看，但缺少前置条件时应 disable 并说明缺失项。

## Curated Family mode

从 `SequenceFamilySpec` 自动生成：

- label/description/version/source identity；
- 参数 dtype/unit/default/min/max/choices/sweepable；
- fixed/linspace/range/explicit mode；
- point count 与 sampling order；
- channel roles and timing dependency summary；
- provider-specific validation issues；
- first/current/last preview。

不能在 GUI 硬编码 Rabi 参数名。Provider 新增参数后 UI 自动出现。Non-sweepable 参数不能切换到 sweep mode。

## Generic Template mode

导入/inspect base sequence 后显示：

- channels；
- pulse list with stable fingerprint, label, start, duration, end；
- trigger/readout/laser/MW role suggestions，但 suggestions 必须由 metadata/explicit mapping 确认；
- target selector；
- supported property operations：duration, start, end, gap；
- propagation：none, following shift, group shift；
- anchors/constraints and dependency summary；
- stale/ambiguous/missing target diagnostics。

功能目录按 task 分组：

```text
Basic Timing       duration | start | end | gap
Propagation        shift following | shift group
Constraints        anchor | preserve gap | preserve end/period where supported
Channels & Trigger map roles | inspect output usage
Preview            first | current | last | overlay/diff
Build              validate | estimate | prepare | inspect bundle
```

只显示 transform engine 实际支持的功能。Unsupported operation 不得生成 YAML 占位。

## Standalone editor bridge

保留外进程隔离。建立 versioned JSON protocol，至少：

```json
{
  "protocol_version": 1,
  "editor_version": "...",
  "capabilities": ["open", "edit_channels", "edit_pulses", "validate", "preview", "save"],
  "source": "...",
  "dirty": false,
  "validation": [],
  "summary": {"channels": [], "pulse_count": 0, "duration_s": null},
  "saved_artifact": {"path": "...", "sha256": "..."}
}
```

要求：

- project/package-relative default editor path；
- `QULAB_SEQUENCE_EDITOR_PATH/PYTHON` 可显式 override；
- 无开发者绝对路径；
- missing Python/Qt/dependency/protocol mismatch 为 friendly diagnostic；
- stdout protocol 与 logs 分离，不能让任意 stdout 破坏 JSON；
- timeout/cancel/process exit；
- editor save 后主面板校验文件、hash、re-inspect、invalidate prepared plan；
- editor 未保存时不能假装主 config 已更新；
- bridge capabilities 控制 GUI 可用按钮，不猜 editor 功能；
- editor validation 映射到 channel/pulse/field diagnostics。

如需修改 vendored standalone editor，保持其可单独启动；不得重新引入外部 `panel(basic)` 绝对路径。

## Preview

Preview 不连接 hardware，不 full-materialize every edit。

至少：

- channel timeline；
- pulse labels/roles；
- first/current/last coordinate；
- two-point overlay/difference；
- sequence duration/period；
- trigger position/window；
- acquisition window overlay when NI config available；
- changed pulse + automatically shifted pulses highlighted；
- constraint/dependency arrows or concise table；
- stale target visible。

Canvas/model 尽量从 standalone editor 抽取通用 data model；Qt5-specific widget 不能直接嵌入 Qt6/PySide6。共享纯 model，分别渲染。

## Feedback and validation

Inline issues 必须关联 plan parameter、channel role、pulse target、constraint 或 preview point。至少覆盖：

- provider missing/version/import；
- required/unknown parameter；
- dtype/unit/range/empty sweep；
- too many points/materialization estimate；
- template missing/parse/hash change；
- target missing/ambiguous/stale fingerprint；
- invalid start/duration/negative time/overlap；
- propagation conflict/constraint cycle；
- period overflow；
- trigger channel missing/mismatch；
- DAQ sample clock/start trigger route mismatch where existing validator knows；
- acquisition window outside trigger/readout；
- generated output invalid/empty；
- workflow missing sequence_sweep/load/arm/start/read linkage；
- prepared plan stale after edit。

Unknown physical cable state 标 warning/needs bench verification，不判为 passed。

## Workflow and parameter integration

- 创建 plan 后可一键插入/更新 canonical `sequence_sweep` macro at selected workflow location；
- generated expansion read-only；
- sequence coordinates 出现在 Operator Parameters、DataPoint.coords 和 RunStore provenance；
- parameter rename/update 同步 plan/workflow bindings or produces diagnostic；
- workflow composer completeness checks consume sequence plan requirements；
- sequence edit invalidates Prepare and old plan hash；
- generated files/cache 不手工加入 authoring YAML entry list。

## UX acceptance

- resource/provider/template selectors；
- parameter controls use numeric/choice/mode widgets；
- channel/pulse selection uses searchable table + timeline selection synchronization；
- first/current/last segmented control；
- validation summary always visible；
- Prepare button near point-count/hash/status；
- advanced targets/constraints available but curated family normal path remains simple；
- no nested cards/marketing layout；
- long path/hash elide + tooltip；
- 1366x768 usable，125% Windows scaling no overlap。

## Tests

Headless：

- provider descriptor -> dynamic fields；
- curated fixed/range/linspace/explicit plans；
- generic template inspect/target/property/propagation/constraints；
- stale fingerprints after external edit；
- first/current/last preview deterministic；
- editor protocol success/error/timeout/version mismatch；
- save reinspection/hash/prepare invalidation；
- point count/max limit；
- workflow macro insertion and parameter binding；
- trigger/acquisition diagnostics；
- no hardware/vendor import on describe/preview；
- project-relative path portability。

Qt：

- switch modes with migration warning；
- provider fields generated, not hardcoded；
- selecting pulse syncs table/timeline；
- operation choices reflect capabilities；
- inline diagnostic focuses field/pulse；
- representative preview nonblank；
- editor launch/process result state；
- external file watcher change -> stale/prepared invalid；
- Prepare success shows bundle/hash/workflow；
- layout screenshot/manual verification。

Integration：

- GUI model creates Rabi 3-point plan -> Prepare -> dry-run -> sequence selections/provenance；
- generic template duration sweep with following shift -> generated bundle -> dry-run；
- malformed template/editor output blocks Prepare；
- ASG-master NI config preview detects known timing/window mismatch；
- config save/reload preserves plan semantics。

## Non-goals

- 不把 pulse 加入 core workflow tree；
- 不建立第二套 scan executor；
- 不在 field change 时连接/启动 ASG；
- 不支持 transform engine 没有实现的任意波形编辑；
- 不隐藏 generated provenance；
- 不以手写 manifest 作为正常 GUI 工作流；
- 不自动确认物理连线。

## Definition of Done

- 三种 authoring mode 职责清楚且共享一个 plan source of truth；
- 功能按实验任务顺序组织；
- curated fields 来自 provider specs；
- generic operations 来自实际 transform capabilities；
- standalone editor 有 versioned capability/validation protocol；
- inline feedback 覆盖参数、pulse、constraint、timing、DAQ integration；
- first/current/last preview 可用；
- plan 可插入 workflow、Prepare、运行并完整记录 provenance；
- stale external edits fail closed；
- automated + Qt + dry-run tests 通过；
- docs 给出 Rabi 和 generic sweep 的实际操作流程。

建议 commits：

```text
feat(sequence): expose guided authoring capabilities
feat(gui): add ordered sequence authoring workflow
feat(gui): add sequence timing and dependency preview
feat(sequence): version standalone editor bridge protocol
test(sequence): cover guided authoring and editor feedback
docs(sequence): document guided sequence workflows
```

最终 handoff 给出三模式功能表、bridge protocol、validation codes、preview screenshots artifact、dry-run provenance、tests 和已知 editor/transform 限制。
