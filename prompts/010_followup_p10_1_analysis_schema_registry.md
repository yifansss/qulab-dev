# Prompt 010-followup P10.1: Analysis Schema + Compute Module Registry Worker

下面这份 prompt 可直接交给新的AI worker。目标是完成P10 Phase A：定义analysis YAML schema、ComputeModule协议、typed plan/spec/result模型、import-safe registry、module dependency/output collision preflight，以及project-local example contract。此worker不执行live compute、不写derived data、不修改GUI。

---

## /goal

让Qulab能够在无硬件、无GUI环境中可靠回答：

- 当前实验声明了哪些compute module实例？
- 每个module需要哪些inputs、产生哪些outputs？
- class/function是否可加载且符合contract？
- module依赖顺序是什么？
- output是否冲突或形成cycle？
- show/save/fail policy是否合法？
- provider/source/version/args如何记录provenance？

本阶段只完成声明、加载和preflight，不处理DataPoint。

---

## 必须先阅读

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md`
4. `docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`
5. `docs/CONFIG_SCHEMA.md`
6. `docs/DATA_MODEL.md`
7. `docs/IMPLEMENTATION_ORDER.md` P10
8. `workers/core_worker.md`
9. `workers/storage_worker.md`
10. `workers/qa_worker.md`
11. `src/qulab/config/parser.py`
12. `src/qulab/config/refs.py`
13. `src/qulab/core/events.py`
14. `src/qulab/storage/dataset.py`
15. current sequence provider registry/path helpers for reusable patterns

---

## 严格范围

### 必须实现

- `analysis.live` / `analysis.modules` schema；
- typed module config/spec/point/result models；
- class-based protocol；
- function adapter；
- dotted module和project-relative `.py`加载；
- source identity/hash/version；
- explicit registry；
- input/output declaration validation；
- output namespace/collision rules；
- module dependency DAG/topological order；
- fail/show/save/run_live/run_post policy validation；
- preflight issues merged intoexisting validation result；
- optional argument spec contract；
- example user module和README；
- unit/integration parse tests；
- docs。

### 明确不实现

- 不实现LiveComputeEngine；
- 不订阅EventBus；
- 不新增DerivedData event；
- 不写RunStore derived outputs；
- 不修改Live View；
- 不实现recompute CLI；
- 不实现async queue；
- 不写ODMR/Rabi/contrast等具体公式；
- 不import hardware drivers；
- 不执行任意YAML expression/eval。

---

## 推荐模块

```text
src/qulab/analysis/
  __init__.py
  models.py
  errors.py
  base.py
  registry.py
  config.py
  validation.py

analysis_modules/
  README.md
  examples/
    passthrough_scale.py
```

Example只用于contract/test，不宣称实验公式。

建议tests：

```text
tests/unit/test_analysis_models.py
tests/unit/test_analysis_config.py
tests/unit/test_analysis_registry.py
tests/unit/test_analysis_dependency_graph.py
tests/unit/test_analysis_validation.py
tests/integration/test_analysis_config_parse.py
```

---

## YAML Contract

必须支持：

```yaml
analysis:
  live:
    enabled: true
    fail_policy: warn
    save_outputs: true
    emit_events: true

  modules:
    - name: trace_summary
      module: analysis_modules.trace_window_mean
      class: TraceWindowMean
      enabled: true
      run_live: true
      run_post: true
      show: true
      save: true
      fail_policy: warn
      inputs: [pse_ai1_trace]
      outputs: [signal_mean, baseline_mean]
      namespace: null
      args:
        signal_window_s: [1.0e-6, 3.0e-6]

    - name: normalize
      module: analysis_modules.scalar_formula
      function: compute
      enabled: false
      run_live: true
      run_post: false
      show: false
      save: true
      inputs: [signal_mean]
      outputs: [normalized_signal]
      namespace: analysis
      args: {}
```

Global defaults：

- `enabled: false`时不加载/执行live modules，但schema仍可验证；
- global `fail_policy` default `warn`；
- global `save_outputs` default `true`；
- global `emit_events` default `true`。

Module defaults：

- `enabled: true`；
- `run_live: true`；
- `run_post: false`；
- `show: false`；
- `save`继承global；
- `fail_policy`继承global。

Rules：

- `name`稳定snake_case且instance唯一；
- `module`必填；
- `class`和`function`恰好一个；
- inputs/outputs必须是non-empty unique string list；
- output key不能与本module input同名；
- args必须YAML/JSON-safe；
- fail policy只允许`warn|skip|fail`；
- `show:true, save:false`合法并标记live-only；
- `run_live:false, run_post:false`只允许disabled，否则warning/error需明确；
- namespace若存在，effective output key为`<namespace>.<output>`；
- config/resolved_config保持YAML-safe，不嵌runtime对象。

旧config没有analysis时解析行为不变。

---

## Public Models

至少提供等价模型：

```python
@dataclass(frozen=True)
class ComputePoint:
    point_id: str
    coords: Mapping[str, Any]
    data: Mapping[str, Any]
    metadata: Mapping[str, Any]
    timestamp: str

@dataclass(frozen=True)
class ComputeResult:
    data: Mapping[str, Any]
    units: Mapping[str, str | None] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    quality: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ComputeModuleSpec:
    name: str
    version: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    argument_specs: tuple[ComputeArgumentSpec, ...] = ()

@dataclass(frozen=True)
class ComputeModulePlan:
    instance_name: str
    import_target: str
    object_name: str
    object_kind: str
    enabled: bool
    run_live: bool
    run_post: bool
    show: bool
    save: bool
    fail_policy: str
    inputs: tuple[str, ...]
    declared_outputs: tuple[str, ...]
    effective_outputs: tuple[str, ...]
    args: Mapping[str, Any]
    source_identity: AnalysisSourceIdentity
```

`to_dict()`必须JSON-safe。不得在plan中保存module/class实例。

---

## Module Protocol

Class contract：

```python
class ComputeModule(Protocol):
    name: str
    version: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]

    def setup(self, config: Mapping[str, Any], run_context: Mapping[str, Any]) -> None: ...
    def process_point(self, point: ComputePoint) -> ComputeResult | Mapping[str, Any] | None: ...
    def close(self) -> None: ...
```

Optional：

```python
def describe_arguments() -> tuple[ComputeArgumentSpec, ...]: ...
def validate_config(args) -> list[AnalysisValidationIssue]: ...
```

Function shortcut：

```python
def compute(point: ComputePoint, **args) -> ComputeResult | Mapping | None: ...
```

Registry用adapter包装function，使engine只面对一个统一runtime接口。

Module/result规则：

- process不得in-place修改point/data；
- output只允许declared keys，缺失可按point skip但extra key error；
- mapping shortcut必须含`data`，可选units/metadata/quality；
- result必须JSON/storage-safe或可通过现有`to_jsonable`；
- module不得连接hardware；
- expensive setup不在module import时执行；
- `close()`应幂等或被framework至多调用一次。

---

## Registry and Path Loading

支持：

1. dotted import：`analysis_modules.trace_window_mean`；
2. project-relative file：`analysis_modules/custom.py`；
3. explicit built-in module。

规则：

- 使用`project_root()`/`resolve_project_path()`；
- 不依赖cwd；
- 不永久污染`sys.path`；
- file module使用stable synthetic module name包含source hash；
- source identity记录path/import target/SHA-256/version；
- source file missing/import error/object missing/type mismatch给stable error code；
- module import stdout/stderr不泄漏GUI；可在diagnostics记录；
- 不自动import目录下所有文件；
- repeated load可cache descriptor，但source hash变化必须invalidate；
- Windows/macOS路径tested。

推荐API：

```python
registry.describe(plan) -> ComputeModuleSpec
registry.instantiate(plan) -> RuntimeComputeModule
load_analysis_plan(raw_analysis, *, project_base=None) -> AnalysisPlan
```

P10.1 tests可以instantiate但不得process live events。

---

## Dependency Graph

分析enabled modules的effective inputs/outputs：

- raw input：没有enabled module产生同名key；
- derived dependency：由另一个enabled module产生；
- output key全局唯一；
- module不能依赖自己的output；
- cycle报`analysis_dependency_cycle`；
- topological order稳定，相同独立层按config order；
- disabled module output不能满足enabled module input；
- unknown raw input通常warning，若config static data spec明确不可能则error；
- namespace在graph构建前应用。

输出`AnalysisExecutionPlan`：ordered module plans、declared raw inputs、all derived outputs、dependency edges。

不要把data arrival顺序当作dependency order。

---

## Raw/Derived Collision Preflight

从可静态发现的workflow `save_as`、plot/data declarations、resources read outputs（仅有可靠metadata时）收集raw key candidates。

Rules：

- derived effective output与known raw key冲突 -> error；
- 两module output冲突 -> error；
- namespace可解决冲突；
- runtime出现未预见raw collision仍由P10.2 fail closed for derived output，raw保留；
- 不通过key名字猜raw/derived。

---

## Validation Issue Codes

至少：

```text
analysis_config_invalid
analysis_module_name_duplicate
analysis_module_target_invalid
analysis_module_not_found
analysis_module_import_failed
analysis_object_not_found
analysis_contract_invalid
analysis_version_mismatch
analysis_inputs_invalid
analysis_outputs_invalid
analysis_output_collision
analysis_dependency_cycle
analysis_dependency_disabled
analysis_input_unknown
analysis_args_invalid
analysis_fail_policy_invalid
analysis_live_only_output
```

issues使用现有severity/code/message模式并合并到Prepare展示。Import traceback只进logs/cause，不作为operator message全文。

---

## Parser Integration

扩展`ParsedExperiment`或附加typed字段：

```python
analysis_plan: AnalysisExecutionPlan | None
```

`parse_experiment_config()`：

- old config -> `analysis_plan=None`或disabled empty plan；
- analysis config -> load/validate descriptors and graph；
- 不调用module `setup/process/close`；
- 不连接hardware；
- raw config/resolved config保持可序列化；
- validation issues与sync/sequence issues统一。

若P9.3A新增prepare pipeline，analysis validation应接入同一prepared result，不fork第二个Prepare系统。开始时检查实际P9.3A状态。

---

## Example Module

提供generic contract fixture，例如scale：input scalar乘configured scale。它不是实验公式。

要求：

- class形式；
- version/input/output declarations；
- argument spec；
- setup/process/close；
- no numpy required；
- no hardware imports；
- README说明module contract、show/save/fail semantics和testing。

---

## Tests

至少覆盖：

1. absent/null/disabled analysis backward compatibility。
2. global/module defaults inheritance。
3. duplicate name/class+function/invalid policies。
4. dotted module load。
5. project-relative file load independent ofcwd。
6. source hash/version identity。
7. missing/import/object/contract errors。
8. class/function adapter descriptors。
9. args spec/default/range/type validation。
10. output namespace mapping。
11. raw-derived collision。
12. module-module collision。
13. dependency topological order。
14. cycle/self-dependency/disabled dependency。
15. unknown raw input warning。
16. show true/save false live-only warning/status。
17. config/resolved config YAML serialization。
18. no Qt/hardware/vendor imports。
19. P9 sequence plan config + analysis config can Prepare together。
20. full suite。

---

## 文档更新

更新：

```text
docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md
docs/CONFIG_SCHEMA.md
docs/IMPLEMENTATION_ORDER.md
analysis_modules/README.md
```

只标记P10 Phase A完成，其余保持planned。

---

## 验收命令

```bash
python -m pytest tests/unit/test_analysis_models.py
python -m pytest tests/unit/test_analysis_config.py
python -m pytest tests/unit/test_analysis_registry.py
python -m pytest tests/unit/test_analysis_dependency_graph.py
python -m pytest tests/unit/test_analysis_validation.py
python -m pytest tests/integration/test_analysis_config_parse.py
python -m pytest
```

---

## 完成定义

- YAML可声明class/function modules；
- registry import-safe且source可追溯；
- dependency/collision/policy preflight明确；
- old/P9 configs不回归；
- 无live execution/storage/GUI side effect；
- full suite通过。

---

## 最终汇报

1. 修改文件和公共imports。
2. YAML defaults/effective outputs。
3. module/function contract。
4. registry/path/source hash语义。
5. dependency/collision issue codes。
6. P9 prepare integration。
7. tests结果。
8. 给P10.2的runtime plan handoff。

