# Prompt 011-followup P11.3B: Guided Workflow Composer Worker

这份 prompt 可直接交给 GUI worker。目标是把当前 free-form Workflow Tree Builder 升级为 schema-driven composer：用户从当前 resources 实际可用的功能中选择 action，GUI 自动给出必填参数、单位、范围、引用、返回和安全信息，并持续判断流程是否完整。

## Dependencies

硬依赖 P11.1 transactional diagnostics 和 P11.3A action schema registry。不得在缺少这两项时用硬编码 method tables 代替。

## /goal

让用户无需记住 YAML 语法或 adapter 方法即可完成代表性实验：

- 配置/选择 resources；
- 从 capability-filtered palette 添加 action；
- 用 schema form 填写参数；
- 添加 scan/average/measurement/run/wait/cleanup；
- 将参数绑定到 in-scope scan/experiment/sequence values；
- 明确保存 data-producing action 的结果；
- 持续看到 field、node 和 whole-workflow diagnostics；
- 从 recipe 创建可编辑的 Rabi/ODMR/NI/ASG skeleton；
- 保存为当前 canonical YAML，并由 CLI 使用同一 parser 执行。

## 必须先阅读

- `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
- `docs/OPERATOR_UI.md`
- `docs/CONFIG_SCHEMA.md`
- `docs/HARDWARE_SYNC.md`
- `docs/ADAPTER_REQUIREMENTS.md`
- P11.1/P11.3A handoff
- workflow model/controller/Qt views
- operator parameters
- sequence sweep model/view
- sync/preflight validators
- all bench templates as real recipes/use cases

## Shared document model

Guided composer、Operator Parameters、Sequence Sweep、raw YAML save 必须编辑同一个 authoring config/document。禁止第二套独立 GUI graph。

推荐 Qt-free presenter/model：

```python
WorkflowComposerModel
  list_palette(context_path)
  insert_structural_step(...)
  insert_action(resource, action_spec, values, parent, index)
  move_step(...)
  wrap_steps(kind, ...)
  validate_incremental(...)
  validate_complete(...)
  apply_recipe(...)
  undo()/redo()
```

所有 mutation 返回新 config/snapshot 或使用清楚的 command history。选择/展开状态属于 view，不写入 YAML。

## Action palette

Palette 根据当前 config resources + AdapterSpec 生成：

- group by resource；
- subgroup by lifecycle/task：Configure, Sequence, Arm/Start, Acquire/Read, Stop/Cleanup；
- searchable by label/method/capability；
- 显示 safety icon、return kind、allowed section；
- unavailable action 说明缺哪个 resource/capability，不应静默消失；
- structural blocks 独立分组；
- sequence_sweep macro 使用现有 P9 authoring，不展开 generated internals。

## Schema-generated inspector

选择 action 后：

- required args 排前；
- optional args 可展开；
- number -> numeric editor with unit/range；
- choice -> combo；
- bool -> checkbox；
- path -> file picker with project-relative storage；
- terminal/channel -> adapter/config-provided choices when known, otherwise validated text；
- reference-capable arg -> Literal / Reference segmented mode；
- reference picker 只列当前 scope 中有效值；
- mapping/list 使用结构化 editor，不能要求用户手写 Python repr；
- description/safety/phase 用 tooltip/compact status；
- return data 支持 `save_as`，data-producing action 未保存时给明确 warning；
- field diagnostic inline，whole-node diagnostic 在 inspector summary。

Advanced unknown kwargs 只能在 ActionSpec 明确允许时出现，并标 `advanced/unknown safety`。

## Structural authoring

至少支持完整 add/edit/duplicate/delete/reorder：

- setup/procedure/cleanup sections；
- scan linspace/range/explicit；
- average；
- measurement；
- run with timeout；
- wait；
- cleanup nested block；
- action/call；
- sequence_sweep macro read/edit handoff to Sequence Sweep panel。

支持把 selected steps wrap into scan/average/measurement/run；支持 move before/after/into compatible containers。拖拽可做，但必须有 non-drag buttons/menus 以保证可靠性。

## References and scans

- scan name 成为 body scope coordinate；
- nested scopes 正确显示外层 references；
- unknown/forward/out-of-scope ref diagnostic；
- rename scan 时提供 references update preview，不静默留下 broken refs；
- scan coordinate 与 action arg unit compatibility；
- sequence plan coordinates 显示为现有 P9 source of truth；
- 不实现第二套 scan executor；composer 只生成 canonical nodes。

## Completeness validator

使用 ActionSpec state requirements/provisions + existing sync/preflight，不用 method-name guessing。至少检查：

- resource 被调用但未声明；
- required configure before arm/start/read；
- sequence load/compile before ASG arm/start when adapter contract requires；
- DAQ configure/arm before external-trigger acquisition；
- master starts only after receivers armed；
- read occurs after acquisition start/trigger path；
- started/output resources have stop/output_off cleanup；
- measurement has at least one data-producing saved result，或用户显式确认无数据；
- duplicate save_as/data collision；
- run timeout absent/too short relative to known acquisition estimate；
- unsafe output action without authorization/template gate；
- sync plan and workflow order disagree；
- empty scan/body/measurement；
- sequence_sweep coordinate/bundle preparation issues。

确定错误为 error；实验可行但不推荐为 warning；不要把未知硬件事实判成确定通过。

## Recipes

Recipes 只生成普通 authoring config，可立即编辑。至少：

- mock dry-run scalar scan；
- NI manual slow AO -> AI read；
- NI-master AO/AI；
- ASG TTL scope smoke；
- ASG-master NI PSE trace；
- generated Rabi；
- low-power ODMR。

Recipe 根据已选 resources/adapters remap resource names；缺 capability 时先提示并不生成半残 workflow。危险 recipe 默认 template-only、output disabled、physical verification false。

## UX

保留 Control page submodes。Builder 推荐：

```text
Palette | Workflow Tree | Schema Inspector + Diagnostics
```

- 紧凑桌面布局；
- toolbar 用 icons/tooltips；
- breadcrumb 显示 node path/scope；
- undo/redo；
- unsaved/invalid/validated/prepared state 清楚；
- edit 后 prepared state 失效；
- diagnostics click -> node/field；
- preview YAML diff，可选 raw YAML view；
- 不用大段教学文字，不用 nested decorative cards；
- 不隐藏 advanced Builder，但 Operator Parameters 仍服务日常调参。

## Tests

Headless：

- palette filtered by resource/capability；
- schema form value conversion；
- required/default/unit/range/ref；
- insert/move/wrap/delete/undo/redo；
- scope/rename refs；
- completeness lifecycle scenarios；
- unsafe action gates；
- recipes parse and offline-preflight；
- generated YAML CLI roundtrip；
- edit invalidates Prepare；
- no hardware calls。

Qt：

- select palette action -> correct fields；
- required fields visibly marked；
- add action creates correct tree node；
- reference picker scope；
- diagnostics focus node/field；
- reorder/wrap and undo；
- recipe selection；
- save/reload retains semantics；
- 1280x800/1366x768 no overlap；
- Qt optional import remains safe。

Integration acceptance：用 GUI model（不是手写最终 YAML）构造 mock Rabi-like 和 ASG-master NI trace config，Prepare/dry-run，验证 events/data/config。

## Non-goals

- 不做 pulse-level core workflow；
- 不执行 hardware action from palette；
- 不替代 Direct Control；
- 不把 recipes 变成新 executor type；
- 不自动修复可能改变实验意义的 ordering；
- 不在此阶段做 adaptive/global scan engine。

## Definition of Done

- 用户不记 method/arg 名也能插入当前 resource 的 action；
- form 来自 ActionSpec，不是 GUI hardcode；
- structural workflow 编辑完整；
- references/units/returns/safety 有反馈；
- completeness validator 能指出缺失 configure/arm/start/read/cleanup/data；
- representative recipes 生成 canonical valid YAML；
- invalid edits 不会被误标 prepared；
- tests 覆盖 model + Qt + dry-run；
- docs 提供简短操作流程和 schema extension 方法。

建议 commits：

```text
feat(gui): add schema-driven workflow action palette
feat(gui): add guided workflow forms and editing
feat(config): validate workflow lifecycle completeness
feat(gui): add experiment recipe skeletons
test(gui): cover guided workflow composition
docs(gui): document workflow composer
```

最终 handoff 给出 supported structural actions、recipes、completeness rules、screenshots artifact、tests、known schema gaps，并确认所有输出仍是 canonical YAML。
