# Prompt 011-followup P11.1: Transactional Config Load and Diagnostics Worker

这份 prompt 可直接交给 config/GUI worker。目标是让 Operator Console 在 Load 阶段就准确判断 YAML、结构、workflow step、resource/action/reference 和 offline preflight 问题，给出可定位、可理解、可修正的反馈。不得再出现“文件看似加载成功，直到 Prepare/Start 才发现基础语法或步骤错误”。

## /goal

实现一个无硬件副作用、transactional 的 candidate-load pipeline：

- 读取候选文件；
- 收集尽可能完整的结构化 diagnostics；
- 有 error 时不替换上一个有效 active config；
- 在 GUI 中显示文件、line/column、config path、workflow node、错误原因和修正提示；
- 无 error 时激活 candidate，并保留 warning/info；
- Prepare/Start 复用同一 diagnostic contract，不维护第二套错误格式。

## 必须先阅读

- `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
- `docs/CONFIG_SCHEMA.md`
- `docs/OPERATOR_UI.md`
- `docs/HARDWARE_SYNC.md`
- `src/qulab/config/loader.py`
- `src/qulab/config/parser.py`
- `src/qulab/config/errors.py`
- `src/qulab/sequence_generation/preparation.py`
- `src/qulab/gui/controller.py`
- `src/qulab/gui/pyqt_views.py`
- `src/qulab/gui/workflow_model.py`
- `src/qulab/gui/yaml_editor.py`
- `src/qulab/sync/validators.py`
- current parser/preflight/GUI tests

先运行 `git status --short --branch` 与完整 tests。不要覆盖其他 worker 修改；不要修改 `drivers/pycontrol`。

## 当前 bug

当前 `OperatorController.load_config()` 只调用 YAML loader；full parse/preparation 在 Prepare 才执行。Qt `_load_config()` 在成功读取后还清空 `issue_table`。因此：

- 语义错误可能被当成成功 Load；
- modal message 只有异常字符串，没有稳定 code/path/line；
- load 一半失败时 active config 状态不明确；
- 用户无法从 issue 跳转到对应 workflow node；
- parser、sequence、sync、analysis 的 issue 形式不统一。

## 必须实现的模型

新增 Qt-free contract，推荐：

```python
@dataclass(frozen=True)
class ConfigDiagnostic:
    severity: str
    code: str
    message: str
    config_path: tuple[str | int, ...] = ()
    workflow_path: tuple[str | int, ...] | None = None
    source_file: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None
    related_paths: tuple[tuple[str | int, ...], ...] = ()

@dataclass(frozen=True)
class ConfigLoadResult:
    candidate_path: Path
    candidate_config: dict[str, Any] | None
    parsed: ParsedExperiment | None
    diagnostics: tuple[ConfigDiagnostic, ...]
    activated: bool
```

命名可按代码库调整，但字段语义和 headless 可测试性必须保留。

## Validation stages

### Decode

- missing/unreadable file；
- UTF-8/encoding error；
- empty YAML；
- syntax error；
- duplicate mapping key，不能允许 PyYAML 静默覆盖；
- top-level 不是 mapping；
- syntax diagnostic 必须包含 one-based line/column 和简短 source excerpt。

### Structure

- top-level section type；
- resource mapping；
- setup/procedure/cleanup list type；
- unknown step；
- 同一 step 同时声明多个 step kind；
- scan/average/measurement/run/wait/call 字段类型与必填项；
- 非法 values、空 scan、非正 count/duration/timeout；
- malformed args/save_as/enabled。

### References

- missing/unknown adapter；
- resource/action 不存在；
- action 与 capability 不匹配；
- unknown/missing arguments；
- `${...}` 引用不存在或超出 scope；
- sequence provider/template/bundle/target/parameter；
- analysis module/input/output/collision；
- sync resource/terminal references。

P11.3A 完成前，action argument validation 可使用当前 adapter 和 parser 已知信息，但必须把接口放在可由后续 ActionSpec registry 替换的位置，不在 GUI 里 introspect。

### Offline preflight

运行现有 sequence preparation、parser 和 sync validators，但：

- 不 connect；
- 不 arm/start/read/output；
- 不加载必须依赖硬件连接的 vendor runtime；
- 不 materialize 超大 bundle，遵循现有 preview/prepare 边界；
- 保留 warnings；
- 将已有 issue 转成统一 diagnostic，稳定保留原 code。

## Source map

使用 YAML compose node marks 构造 `(config_path -> line/column)` 映射，再独立 safe-load 数据。不要通过正则定位 YAML。对 list index、nested args、sequence plans 和 analysis modules 都要支持。

当 generated/compiled path 无直接 source node 时：

- 定位到最接近的 authoring parent；
- `related_paths` 指明生成来源；
- message 说明这是 compiled/offline preflight diagnostic。

## Transaction semantics

Controller 必须保持：

- `active config`: 最近一次成功激活的 experiment；
- `candidate result`: 最近一次 Load 尝试及 diagnostics。

要求：

1. candidate error 不覆盖 active config/path/parsed/sequence model；
2. 初次启动无 active config 时，error candidate 后 Start/Prepare disabled；
3. candidate warning 可以激活，但 issues 保留；
4. 激活后清理属于旧 config 的 selected nodes/live state，不能保留 stale GUI objects；
5. Load 不产生 run folder，不连接硬件；
6. 保存 invalid draft 必须是显式 Save Draft 行为，不能伪装为 active experiment save；
7. Prepare 使用 active config 并刷新/合并 diagnostics；
8. Start 对任何 error fail closed。

## Qt UI

修改现有页面，不新增第二个主程序：

- Load 后显示 `Loaded`、`Loaded with warnings` 或 `Load blocked`；
- issue table 增加 location/hint，支持 severity filter；
- error count 和 warning count 清楚可见；
- 双击 issue 选择相应 tree node/inspector field；
- YAML syntax issue 显示 line/column 和短 excerpt；
- tooltip 可显示完整 path/message；
- modal 只用于阻断性摘要，详细信息留在 diagnostics panel；
- 不再在 load 成功路径无条件清空 issue table；
- previous active config 被保留时明确显示其名称，不能让用户误以为 error candidate 已激活；
- Start/Prepare enabled state 与 active/candidate validation 一致。

不要在 UI 显示 traceback。完整 exception chain 可以写入开发日志。

## Error codes

至少提供稳定 codes：

```text
yaml_file_unreadable
yaml_encoding_error
yaml_empty
yaml_syntax_error
yaml_duplicate_key
config_top_level_type
config_section_type
workflow_step_type
workflow_step_ambiguous
workflow_step_unknown
workflow_field_missing
workflow_field_type
workflow_value_invalid
resource_missing_adapter
resource_adapter_unknown
action_resource_unknown
action_method_unknown
action_argument_missing
action_argument_unknown
parameter_reference_unresolved
```

已有 sequence/sync/analysis codes 不重命名，只转换格式。

## Tests

Headless tests 至少覆盖：

- malformed YAML line/column；
- duplicate key；
- empty/non-mapping YAML；
- invalid section/step/scan/average/wait；
- unknown resource/action/arg/ref；
- 多 diagnostics 收集，不只返回第一个可继续检查的问题；
- candidate error 保留 previous active config；
- first-load error leaves no active config；
- warning candidate activates；
- omitted optional setup/cleanup remains valid；
- Load never calls adapter connect/start/output；
- existing bench and dry-run templates produce expected diagnostics；
- source-map nested list locations；
- Prepare and Load share codes/contracts。

Qt tests 至少覆盖：

- error candidate 后 issue rows 非空；
- UI 未显示 misleading Loaded success；
- previous active experiment remains visible；
- selecting issue focuses tree node；
- valid load updates all panels；
- warning remains visible；
- Start disabled on no valid active config。

增加 regression test 覆盖当前 `_load_config()` 清空 issue table 的问题。

## Non-goals

- 不做完整 guided composer；
- 不自动修复实验含义；
- 不连接硬件验证物理线缆；
- 不把 optional setup/cleanup 改为必填；
- 不吞掉 unknown exception 并假装 validation warning。

## Definition of Done

- 所有 load 尝试产生结构化结果；
- 基础 workflow/step/reference 错误在 Load 阶段可见；
- diagnostics 有稳定 code/path，能定位时有 line/column；
- invalid candidate 不污染 active experiment；
- UI 不再清空或隐藏 load diagnostics；
- Prepare/Start fail closed 且复用同一合同；
- 无 hardware/vendor/display 的 tests 可运行；
- 完整 test suite 和 portability test 通过；
- docs 更新准确说明 Load、Validate、Prepare 的差别。

建议 commits：

```text
feat(config): add structured load diagnostics
fix(gui): preserve validation issues during config load
test(gui): cover transactional invalid config loading
docs(config): document load validation stages
```

最终 handoff 给出 API、codes、UI 行为、测试结果、已知不能定位的 generated paths，并确认 Load 未连接硬件。
